// Race start bar shared by the Course legs, phone and MFD pages.
//
// Reads /api/race_start (Race Officer start time, postponement, course status)
// every 5 seconds and counts down locally every second. The server supplies
// seconds_to_start, so this never parses a date string: older MFD browsers
// handle ISO dates inconsistently. Deliberately ES5 with XMLHttpRequest for the
// same reason.
//
// Usage: MojitoRaceStart.attach("raceStartBar", {theme: "dark"});
//
// With {frame: "someId"} the bar colours are put on that element instead and it
// is never hidden: the MFD uses this so the bar can carry other readings beside
// the start status. The frame keeps its own classes for layout.
var MojitoRaceStart = (function() {
  var el = null;
  var frame = null;
  var frameBaseClass = "";
  var info = null;
  var fetchedAt = 0;

  var CSS =
    ".rsb{display:none;margin:6px 0 10px 0;padding:8px 12px;border-radius:10px;font-weight:800;line-height:1.3;}" +
    ".rsbMain{font-size:1.25em;font-weight:800;}" +
    ".rsbSub{font-size:0.85em;font-weight:700;opacity:0.85;}" +
    ".rsb-light{background:#eef2ff;color:#1e1b4b;border:1px solid #c7d2fe;}" +
    ".rsb-light.rsb-urgent{background:#fef3c7;color:#78350f;border-color:#fcd34d;}" +
    ".rsb-light.rsb-postponed{background:#fee2e2;color:#7f1d1d;border-color:#fca5a5;}" +
    ".rsb-light.rsb-racing{background:#dcfce7;color:#14532d;border-color:#86efac;}" +
    ".rsb-light.rsb-pending{background:#f1f5f9;color:#334155;border-color:#cbd5e1;}" +
    ".rsb-dark{background:#1e293b;color:#f8fafc;border:1px solid #475569;}" +
    ".rsb-dark.rsb-urgent{background:#713f12;color:#fef9c3;border-color:#facc15;}" +
    ".rsb-dark.rsb-postponed{background:#7f1d1d;color:#fee2e2;border-color:#f87171;}" +
    ".rsb-dark.rsb-racing{background:#14532d;color:#dcfce7;border-color:#4ade80;}" +
    ".rsb-dark.rsb-pending{background:#1e293b;color:#cbd5e1;border-color:#475569;}";

  function addCss() {
    var style = document.createElement("style");
    style.type = "text/css";
    if (style.styleSheet) style.styleSheet.cssText = CSS;
    else style.appendChild(document.createTextNode(CSS));
    document.getElementsByTagName("head")[0].appendChild(style);
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function clock(totalSeconds) {
    var s = Math.floor(Math.abs(totalSeconds));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(sec) : m + ":" + pad(sec);
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function render() {
    if (!el) return;
    if (!info || !info.live || !info.race) {
      if (frame) {
        frame.className = frameBaseClass + " " + theme;
        el.innerHTML = "";
      } else {
        el.style.display = "none";
      }
      return;
    }
    var race = info.race;
    var state = "";
    var main = "";
    var subs = [];

    if (race.race_finished) {
      main = "Race finished";
    } else if (race.postponed) {
      state = "rsb-postponed";
      main = (race.postponement_flag || "AP") + " — start postponed";
      if (info.postponement_ends_clock) subs.push("AP down at " + info.postponement_ends_clock);
    } else if (info.seconds_to_start == null) {
      state = "rsb-pending";
      main = "No start time set";
    } else {
      var s = info.seconds_to_start - (new Date().getTime() - fetchedAt) / 1000;
      if (s > 0) {
        state = s <= 60 ? "rsb-urgent" : "";
        main = "Start in " + clock(s);
        subs.push("First start " + info.start_clock);
      } else {
        state = "rsb-racing";
        main = "Racing +" + clock(s);
        subs.push("Started " + info.start_clock);
      }
    }

    var title = race.race_name || "Current race";
    if (race.course_set) {
      if (race.course_label) title += " · Course " + (race.course_no != null ? race.course_no + " " : "") + race.course_label;
    } else {
      subs.unshift("Course not set yet");
      if (!state) state = "rsb-pending";
    }
    if (race.shortened) subs.unshift("Course shortened" + (race.shortened_label ? " at " + race.shortened_label : ""));

    var html = '<div class="rsbSub">' + esc(title) + '</div>' +
      '<div class="rsbMain">' + esc(main) + '</div>' +
      (subs.length ? '<div class="rsbSub">' + esc(subs.join(" · ")) + '</div>' : "");
    if (frame) {
      frame.className = frameBaseClass + " " + theme + (state ? " " + state : "");
      el.innerHTML = html;
      return;
    }
    el.className = "rsb " + theme + (state ? " " + state : "");
    el.innerHTML = html;
    el.style.display = "block";
  }

  function load() {
    var x = new XMLHttpRequest();
    x.open("GET", "/api/race_start?_=" + new Date().getTime(), true);
    x.onreadystatechange = function() {
      if (x.readyState !== 4) return;
      try {
        var data = JSON.parse(x.responseText || "{}");
        if (x.status >= 200 && x.status < 300 && data.ok) {
          info = data;
          fetchedAt = new Date().getTime();
        } else {
          info = null;
        }
      } catch (e) {
        info = null;
      }
      render();
    };
    x.send(null);
  }

  var theme = "rsb-light";

  function attach(elementId, options) {
    el = document.getElementById(elementId);
    if (!el) return;
    theme = options && options.theme === "dark" ? "rsb-dark" : "rsb-light";
    frame = options && options.frame ? document.getElementById(options.frame) : null;
    if (frame) frameBaseClass = frame.className;
    addCss();
    load();
    setInterval(load, 5000);
    setInterval(render, 1000);
  }

  return { attach: attach };
})();
