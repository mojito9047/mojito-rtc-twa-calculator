// Main app page (templates/index.html), a tab for each section: Wind & Course
// (with the course chart), Course legs, Edit marks, Expedition marks import,
// Race Officer import and Settings. showView() switches tabs.
//
// Loaded after static/legs.js (leg calculations) and static/race_start.js
// (start bar). Functions are global so the page's onclick/onchange
// attributes can call them.

let marks = [];
let sailChart = { twas: [], rows: [] };
let polarData = { rows: [] };
let liveTws = null;
let sailChartLoaded = false;
let polarLoaded = false;
let courseRoundings = {};
let saveCourseTimer = null;
let loadingCourse = false;
let currentLegIndex = 0;
let currentLegTimer = null;
let showAll = false;
let markById = {};

// Leg calculations are in static/legs.js (MojitoLegs), shared with the phone
// and MFD pages. These are the names the rest of this page uses.
const norm360 = MojitoLegs.norm360;
const angleDiff = MojitoLegs.angleDiff;
const bearingAndDistance = MojitoLegs.bearingAndDistance;
function parsePosition(value) { return MojitoLegs.parsePosition(value); }
function normaliseMarks(rawMarks) { return MojitoLegs.normaliseMarks(rawMarks); }
function rebuildMarkIndex() { markById = MojitoLegs.markIndex(marks); }
function parseCourse(text) { return MojitoLegs.parseCourse(text, markById); }
function side(courseBearing, twd) {
  const t = MojitoLegs.tack(courseBearing, twd);
  return t === "S" ? "Starboard" : t === "P" ? "Port" : "—";
}
function sailFor(twa, tws) {
  return sailChartLoaded ? MojitoLegs.sailFor(sailChart, twa, tws) : "—";
}
function targetSpeedInfoFor(twa, tws) {
  return polarLoaded ? MojitoLegs.targetSpeedInfo(polarData.rows, twa, tws) : null;
}


function sideAbbrev(courseBearing,twd){
  const s = side(courseBearing, twd);
  if (s === "Port") return "P";
  if (s === "Starboard") return "S";
  return "—";
}

function twaSideClass(courseBearing, twd) {
  const s = side(courseBearing, twd);
  if (s === "Port") return "twaPort";
  if (s === "Starboard") return "twaStarboard";
  return "twaNeutral";
}
function pointOfSail(twa){if(twa<35)return"Too close / head to wind"; if(twa<60)return"Close hauled"; if(twa<90)return"Close reach"; if(twa<120)return"Beam reach"; if(twa<150)return"Broad reach"; return"Run";}
function getLeg(from,to,twd){const bd=bearingAndDistance(from,to); const twa=angleDiff(bd.bearing,twd); return {from,to,...bd,twa,side:side(bd.bearing,twd),pos:pointOfSail(twa)};}
function allLegs(twd){const legs=[]; for(const from of marks)for(const to of marks)if(from.id!==to.id)legs.push(getLeg(from,to,twd)); return legs.sort((a,b)=>a.from.id.localeCompare(b.from.id)||a.to.id.localeCompare(b.to.id));}
function routeLegs(twd){const route=parseCourse(document.getElementById("course").value); const legs=[]; for(let i=0;i<route.length-1;i++)legs.push(getLeg(markById[route[i]],markById[route[i+1]],twd)); return legs;}


function targetSpeedFor(twa, tws) {
  const info = targetSpeedInfoFor(twa, tws);
  return info ? info.cmg : null;
}

function formatTargetBsp(info) {
  if (!info) return "—";
  if (info.mode === "upwind" || info.mode === "downwind") return `${info.bsp.toFixed(2)} kt @ ${info.polarTwa.toFixed(0)}°`;
  return `${info.bsp.toFixed(2)} kt`;
}

function formatLegTime(distanceNm, speedKt) {
  if (!speedKt || speedKt <= 0) return "—";
  const totalMinutes = distanceNm / speedKt * 60;
  if (totalMinutes < 60) return `${totalMinutes.toFixed(1)} min`;
  const h = Math.floor(totalMinutes / 60);
  const m = Math.round(totalMinutes % 60);
  return `${h}h ${String(m).padStart(2, "0")}m`;
}


function render(){
  const twd=norm360(Number(document.getElementById("twd").value||0));
  const tws=Number(document.getElementById("tws").value||0);
  const windSummary = document.getElementById("courseLegsWindSummary");
  if (windSummary) {
    windSummary.innerHTML = `<span class="windChip">TWD ${twd.toFixed(0)}°T</span><span class="windChip">TWS ${tws.toFixed(1)} kt</span>` +
      (windMode === "manual" ? `<span class="windChip manualChip">Manual wind</span>` : "");
  }
  document.getElementById("tableTitle").textContent=showAll ? "Range, bearing, TWA and sail chart" : "Course legs";
  document.getElementById("routeTableWrap").style.display = showAll ? "none" : "block";
  document.getElementById("matrixWrap").style.display = showAll ? "block" : "none";

  if (showAll) {
    renderMatrix(twd, tws);
    return;
  }

  const legs=routeLegs(twd);
  updateCurrentLegStatus(legs);
  const tbody=document.getElementById("legs");
  tbody.innerHTML="";
  if(!legs.length){
    tbody.innerHTML=`<tr><td colspan="10" style="text-align:center;color:#64748b;padding:24px;">No course set. Enter at least two valid marks, or wait for the race officer to set the course.</td></tr>`;
    return;
  }
  for(let i = 0; i < legs.length; i++){
    const leg = legs[i];
    const tr=document.createElement("tr");
    if (i === currentLegIndex) tr.className = "currentLegRow";
    const targetInfo = targetSpeedInfoFor(leg.twa, tws);
    const targetSpeed = targetInfo ? targetInfo.cmg : null;
    const roundKey = currentRouteKey(i, leg.from.id, leg.to.id);
    const rounding = courseRoundings[roundKey] || "";
    tr.innerHTML=`<td><strong>${leg.from.id} → ${leg.to.id}</strong><br><span class="small">${leg.from.name} to ${leg.to.name}</span></td>
      <td>${roundingBadge(rounding)}</td>
      <td>${leg.distanceNm.toFixed(2)} nm</td><td>${leg.bearing.toFixed(0)}°T</td><td class="big ${twaSideClass(leg.bearing, twd)}">${leg.twa.toFixed(0)}°</td><td><span class="sailTag">${sailFor(leg.twa, tws)}</span></td><td>${formatTargetBsp(targetInfo)}</td><td>${formatLegTime(leg.distanceNm, targetSpeed)}</td><td>${leg.side}</td><td>${leg.pos}</td>`;
    tbody.appendChild(tr);
  }
}

function renderMatrix(twd, tws){
  const head=document.getElementById("matrixHead");
  const body=document.getElementById("matrixBody");

  head.innerHTML = `<tr><th>From \\ To</th>${marks.map(m => `<th>${m.id}<br><span class="small">${m.name}</span></th>`).join("")}</tr>`;
  body.innerHTML = "";

  for (const from of marks) {
    const tr = document.createElement("tr");
    let row = `<td>${from.id}<br><span class="small">${from.name}</span></td>`;

    for (const to of marks) {
      if (from.id === to.id) {
        row += `<td class="na">—</td>`;
      } else {
        const leg = getLeg(from, to, twd);
        row += `
          <td>
            <div class="cell">
              <div class="range">${leg.distanceNm.toFixed(2)} nm</div>
              <div class="bearing">${leg.bearing.toFixed(0)}°T</div>
              <div class="twa ${twaSideClass(leg.bearing, twd)}">TWA ${leg.twa.toFixed(0)}° ${sideAbbrev(leg.bearing, twd)}</div>
              <div class="sail">${sailFor(leg.twa, tws)}</div>
              <div class="target">${(() => { const info = targetSpeedInfoFor(leg.twa, tws); return info ? formatTargetBsp(info) + " / " + formatLegTime(leg.distanceNm, info.cmg) : "—"; })()}</div>
            </div>
          </td>`;
      }
    }

    tr.innerHTML = row;
    body.appendChild(tr);
  }
}
function toggleAllLegs(){showAll=!showAll; document.getElementById("allLegsButton").textContent=showAll?"Show course only":"Show all legs"; render();}

// Publish the same wind values used by the main Course legs page. /api/twd
// falls back to this value if the instruments' TWD is unavailable, which keeps
// the MFD page from dropping to TWD 0°.
let displayWindPublishBusy = false;

async function publishDisplayWind() {
  if (displayWindPublishBusy) return;

  const twdEl = document.getElementById("twd");
  const twsEl = document.getElementById("tws");
  if (!twdEl || !twsEl) return;

  const twdValue = Number(twdEl.value);
  const twsValue = Number(twsEl.value);
  if (!Number.isFinite(twdValue)) return;

  displayWindPublishBusy = true;
  try {
    await fetch("/api/display_wind", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        twd: norm360(twdValue),
        tws: Number.isFinite(twsValue) ? Math.max(0, twsValue) : null,
        source: "course_legs_page"
      })
    });
  } catch(e) {
    // Ignore; the operator display should not be interrupted by a publish error.
  } finally {
    displayWindPublishBusy = false;
  }
}

const SOURCE_LABELS = {expedition: "Expedition", h5000: "H5000", nmea0183: "NMEA 0183",
                       manual: "manual", display_fallback: "the last TWD shown"};

// -- Wind ----------------------------------------------------------------------
// The wind comes from /api/wind: the instruments, or the TWD/TWS typed here
// when the instrument source (Settings → Instruments) is Manual wind. Manual
// values are saved straight away and used by every display.
let windMode = "instruments";
let manualWindSaveTimer = null;
let manualWindEditing = false;      // an edit not saved yet: do not overwrite the boxes

function setWindMode(mode) {
  windMode = mode === "manual" ? "manual" : "instruments";
  const manual = windMode === "manual";
  document.getElementById("twd").disabled = !manual;
  document.getElementById("tws").disabled = !manual;
  const label = document.getElementById("windMode");
  label.textContent = manual ? "Wind: Manual" : "Wind: Instruments";
  label.classList.toggle("manual", manual);
  document.getElementById("windModeHelp").hidden = !manual;   // how to get back to the instruments
}

async function loadWind() {
  const status = document.getElementById("status");
  try {
    const r = await fetch("/api/wind", { cache:"no-store" });
    const w = await r.json();
    setWindMode(w.manual ? "manual" : "instruments");
    const twdEl = document.getElementById("twd");
    const twsEl = document.getElementById("tws");
    const typing = manualWindEditing || document.activeElement === twdEl || document.activeElement === twsEl;
    if (!w.manual || !typing) {
      const twd = w.manual ? w.manual_wind.twd : w.twd;
      const tws = w.manual ? w.manual_wind.tws : w.tws;
      if (typeof twd === "number") twdEl.value = norm360(twd).toFixed(0);
      if (typeof tws === "number") twsEl.value = Math.max(0, tws).toFixed(1);
    }
    if (w.manual) {
      status.textContent = w.ok ? "Manual wind, used by every display. Type a new TWD or TWS to change it."
                                : "Manual wind: enter TWD and TWS.";
      status.className = w.ok ? "status" : "status bad";
    } else if (w.ok) {
      status.textContent = `From ${SOURCE_LABELS[w.source] || w.source}` +
        (w.warning ? ` (instrument TWD unavailable: ${w.warning})` : "");
      status.className = w.source === "display_fallback" ? "status bad" : "status good";
    } else {
      status.textContent = `Instrument wind unavailable: ${w.error}`;
      status.className = "status bad";
    }
    render();
    publishDisplayWind();
  } catch (e) {
    status.textContent = `Could not read the wind: ${e.message}`;
    status.className = "status bad";
  }
}

function manualWindEdited() {
  if (windMode !== "manual") return;
  manualWindEditing = true;
  render();
  if (manualWindSaveTimer) clearTimeout(manualWindSaveTimer);
  manualWindSaveTimer = setTimeout(saveManualWind, 500);
}

async function saveManualWind() {
  const status = document.getElementById("status");
  const twdText = document.getElementById("twd").value;
  const twsText = document.getElementById("tws").value;
  const body = {};
  if (twdText !== "" && Number.isFinite(Number(twdText))) body.twd = norm360(Number(twdText));
  if (twsText !== "" && Number.isFinite(Number(twsText))) body.tws = Number(twsText);
  try {
    const r = await fetch("/api/wind", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Could not save");
    const saved = data.manual_wind;
    status.textContent = `Manual wind saved: ${saved.twd === null ? "—" : saved.twd.toFixed(0) + "°T"}, ` +
                         `${saved.tws === null ? "—" : saved.tws.toFixed(1) + " kt"}. Used by every display.`;
    status.className = "status good";
  } catch (e) {
    status.textContent = `Manual wind not saved: ${e.message}`;
    status.className = "status bad";
  } finally {
    manualWindEditing = false;
  }
}

function showView(name) {
  document.getElementById("calculatorView").classList.toggle("active", name === "calculator");
  document.getElementById("resultsView").classList.toggle("active", name === "results");
  document.getElementById("marksView").classList.toggle("active", name === "marks");
  document.getElementById("importView").classList.toggle("active", name === "import");
  document.getElementById("raceOfficerView").classList.toggle("active", name === "raceOfficer");
  document.getElementById("settingsView").classList.toggle("active", name === "settings");
  document.getElementById("tabCalculator").classList.toggle("active", name === "calculator");
  document.getElementById("tabResults").classList.toggle("active", name === "results");
  document.getElementById("tabMarks").classList.toggle("active", name === "marks");
  document.getElementById("tabImport").classList.toggle("active", name === "import");
  document.getElementById("tabRaceOfficer").classList.toggle("active", name === "raceOfficer");
  document.getElementById("tabSettings").classList.toggle("active", name === "settings");
  if (name === "results") render();
  if (name === "calculator") setTimeout(renderCourseChart, 80);   // the chart is on this page
  if (name === "marks") renderMarksEditor();
  if (name === "import") loadExpeditionGroups();
  if (name === "raceOfficer") { loadRaceOfficerBase(); loadRaceOfficerPollStatus(); }
  if (name === "settings") { if (!settingsDirty) loadSettings(); checkFileStatus(); }
}


// Course chart rendering. Uses Leaflet when available and SVG fallback otherwise.
let courseChartMap = null;
let courseChartLayers = [];

function courseChartRouteIds() {
  return parseCourse(document.getElementById("course").value);
}

// Leg and mark colours: the signal-flag red and green of index.css.
const CHART_PORT = "#c8102e";
const CHART_STARBOARD = "#00843d";
const CHART_OTHER = "#1c1a15";

function chartRoundingColour(rounding) {
  if (rounding === "P") return CHART_PORT;
  if (rounding === "S") return CHART_STARBOARD;
  return CHART_OTHER;
}

function chartRoundingWords(rounding) {
  return {P: "leave to port", S: "leave to starboard", V: "via, not rounded", F: "run to the finish"}[rounding]
    || "rounding not set";
}

// What the chart draws, worked out once for the map and the plain drawing.
// Marks carry their mark ID only, once each however often they are rounded;
// legs carry their numbers in circles, so the two cannot be mistaken for each
// other. Legs sailed more than once the same way share a circle ("4, 8").
function courseChartModel(routeIds, routeMarks) {
  const legs = [];
  for (let i = 0; i < routeMarks.length - 1; i++) {
    const rounding = (courseRoundings[currentRouteKey(i, routeIds[i], routeIds[i + 1])] || "").toUpperCase();
    legs.push({number: i + 1, from: routeMarks[i], to: routeMarks[i + 1], rounding, colour: chartRoundingColour(rounding)});
  }

  const stops = new Map();
  routeMarks.forEach((mark, i) => {
    if (!stops.has(mark.id)) stops.set(mark.id, {mark, visits: [], roles: []});
    const stop = stops.get(mark.id);
    if (i === 0) {
      stop.roles.push("Start");
    } else {
      stop.visits.push({leg: i, rounding: legs[i - 1].rounding});
    }
    if (i === routeMarks.length - 1 && i > 0) stop.roles.push("Finish");
  });
  for (const stop of stops.values()) {
    // A mark always left the same way takes that colour; otherwise dark.
    const sides = new Set(stop.visits.map(v => v.rounding));
    stop.colour = sides.size === 1 ? chartRoundingColour([...sides][0]) : CHART_OTHER;
  }

  const groups = new Map();
  for (const leg of legs) {
    const key = `${leg.from.id}>${leg.to.id}`;
    if (!groups.has(key)) groups.set(key, {from: leg.from, to: leg.to, colour: leg.colour, numbers: []});
    groups.get(key).numbers.push(leg.number);
  }
  return {legs, stops: [...stops.values()], legGroups: [...groups.values()]};
}

// A point part way along a leg: leg numbers sit 40% along, arrows 70%, so on
// a leg sailed both ways (A to B, then B to A) none of them overlap.
function chartAlong(from, to, fraction) {
  return [from[0] + (to[0] - from[0]) * fraction, from[1] + (to[1] - from[1]) * fraction];
}

// Screen offset (pixels) to the right of a leg's direction of travel, for its
// number: legs between the same marks, or nearly in line, sailed in opposite
// directions then have their numbers on opposite sides.
const CHART_LEG_NO_OFFSET = 14;
function chartRightOffset(bearingDeg) {
  const a = (bearingDeg + 90) * Math.PI / 180;
  return [Math.round(Math.sin(a) * CHART_LEG_NO_OFFSET), Math.round(-Math.cos(a) * CHART_LEG_NO_OFFSET)];
}

function chartMarkPopup(mark, stop) {
  let html = `<strong>${mark.id}</strong> ${mark.name}<br>${MojitoLegs.formatPosition(mark.latDec, false)} ${MojitoLegs.formatPosition(mark.lonDec, true)}`;
  if (!stop) return html + "<br>Not on the course";
  if (stop.roles.includes("Start")) html += "<br>Start";
  for (const visit of stop.visits) html += `<br>End of leg ${visit.leg}: ${chartRoundingWords(visit.rounding)}`;
  return html;
}

function chartBearingDeg(from, to) {
  const lat1 = from[0] * Math.PI / 180;
  const lat2 = to[0] * Math.PI / 180;
  const dLon = (to[1] - from[1]) * Math.PI / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
}

function clearCourseChartLayers() {
  if (!courseChartMap) return;
  for (const layer of courseChartLayers) {
    try { courseChartMap.removeLayer(layer); } catch(e) {}
  }
  courseChartLayers = [];
}

function removeCourseChartMap() {
  if (!courseChartMap) return;
  courseChartMap.remove();
  courseChartMap = null;
  courseChartLayers = [];
}

function addCourseChartLayer(layer) {
  courseChartLayers.push(layer);
  layer.addTo(courseChartMap);
}

function renderCourseChart() {
  const el = document.getElementById("courseChartMap");
  const status = document.getElementById("courseChartStatus");
  if (!el) return;

  // Skip while the Wind & Course tab is hidden: Leaflet would fit the course
  // into a zero-size box. showView("calculator") renders again once it is visible.
  if (!el.offsetWidth) return;

  const routeIds = courseChartRouteIds();
  const routeMarks = routeIds.map(id => markById[id]).filter(Boolean);
  const routePoints = routeMarks.map(m => [m.latDec, m.lonDec]);

  if (routePoints.length < 2 && !marks.length) {
    removeCourseChartMap();
    el.innerHTML =`<div class="courseChartFallback" style="display:grid;place-items:center;color:#64748b;font-weight:800;">No marks with positions yet: add them on Edit marks, or import them.</div>`;
    if (status) {
      status.textContent = "No chart to display: there are no marks with positions.";
      status.className = "status bad";
    }
    return;
  }

  // The chart is framed on the course; with no course yet, on every mark, so
  // the whole area is in view while the course is announced and built.
  const framePoints = routePoints.length >= 2 ? routePoints : marks.map(m => [m.latDec, m.lonDec]);

  if (window.L) {
    renderCourseChartLeaflet(el, routeIds, routeMarks, routePoints, framePoints, status);
  } else {
    renderCourseChartSvg(el, routeIds, routeMarks, framePoints, status);
  }
}

// What the status line under the chart says with no course yet.
function noCourseChartStatus(status, prefix) {
  if (!status) return;
  status.textContent = `${prefix}No course yet: showing all ${marks.length} marks. Add marks above to build the course.`;
  status.className = "status";
}

function renderCourseChartLeaflet(el, routeIds, routeMarks, routePoints, framePoints, status) {
  if (!courseChartMap) {
    el.innerHTML = "";  // clear any earlier "no course" message or SVG chart
    courseChartMap = L.map(el, { scrollWheelZoom:true });
    // Tiles come through this app (server/tiles.py), which keeps a copy of each
    // one shown, so areas viewed with the internet are there without it.
    L.tileLayer("/tiles/osm/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(courseChartMap);
    L.tileLayer("/tiles/seamark/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenSeaMap contributors"
    }).addTo(courseChartMap);
  }

  courseChartMap.invalidateSize();
  clearCourseChartLayers();
  const model = courseChartModel(routeIds, routeMarks);
  const stopById = new Map(model.stops.map(s => [s.mark.id, s]));
  const at = m => [m.latDec, m.lonDec];
  const divIcon = html => L.divIcon({className: "", html, iconSize: null});

  // Marks not on the course: a small grey dot and their ID.
  for (const m of marks) {
    if (stopById.has(m.id)) continue;
    addCourseChartLayer(L.marker(at(m), {icon: divIcon(`<div class="chartMark offCourse"><span class="chartDot"></span><span class="chartMarkId">${m.id}</span></div>`),
                                         zIndexOffset: 100}).bindPopup(chartMarkPopup(m, null)));
  }

  // The legs, coloured by the rounding at their end.
  for (const leg of model.legs) {
    addCourseChartLayer(L.polyline([at(leg.from), at(leg.to)], {
      color: leg.colour,
      weight: 5,
      opacity: 0.9,
      dashArray: leg.rounding === "F" ? "10 8" : null
    }));
  }

  // Each way along a leg: an arrow, and the leg number(s) in a circle.
  for (const group of model.legGroups) {
    const bearing = chartBearingDeg(at(group.from), at(group.to));
    addCourseChartLayer(L.marker(chartAlong(at(group.from), at(group.to), 0.7), {
      icon: L.divIcon({className: "", html: `<div class="legArrowIcon" style="color:${group.colour}; transform:rotate(${bearing}deg);">▲</div>`,
                       iconSize: [24, 24], iconAnchor: [12, 12]}),
      interactive: false, zIndexOffset: 400}));
    const [dx, dy] = chartRightOffset(bearing);
    addCourseChartLayer(L.marker(chartAlong(at(group.from), at(group.to), 0.4), {
      icon: divIcon(`<span class="chartLegNo" style="border-color:${group.colour}; transform:translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px));">${group.numbers.join(", ")}</span>`),
      interactive: false, zIndexOffset: 450}));
  }

  // Marks on the course: a dot in their rounding colour, their ID, and Start/Finish.
  for (const stop of model.stops) {
    const roles = stop.roles.length ? ` <small>${stop.roles.join(" · ")}</small>` : "";
    addCourseChartLayer(L.marker(at(stop.mark), {
      icon: divIcon(`<div class="chartMark"><span class="chartDot" style="background:${stop.colour};"></span><span class="chartMarkLabel">${stop.mark.id}${roles}</span></div>`),
      zIndexOffset: 500}).bindPopup(chartMarkPopup(stop.mark, stop)));
  }

  if (framePoints.length > 1) {
    courseChartMap.fitBounds(L.latLngBounds(framePoints), {padding:[35,35]});
  } else {
    courseChartMap.setView(framePoints[0], 14);          // one mark: fitBounds would zoom right in
  }

  if (routePoints.length < 2) {
    noCourseChartStatus(status, "");
  } else if (status) {
    status.textContent = `Showing ${routePoints.length} route points and ${routePoints.length - 1} legs.`;
    status.className = "status good";
  }
}

function renderCourseChartSvg(el, routeIds, routeMarks, framePoints, status) {
  const width = Math.max(700, el.clientWidth || 700);
  const height = Math.max(420, el.clientHeight || 420);
  const model = courseChartModel(routeIds, routeMarks);
  const onCourse = new Set(model.stops.map(s => s.mark.id));

  const lats = framePoints.map(p => p[0]);
  const lons = framePoints.map(p => p[1]);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const pad = 45;
  const lonSpan = Math.max(0.0001, maxLon - minLon);
  const latSpan = Math.max(0.0001, maxLat - minLat);

  function x(lon) { return pad + ((lon - minLon) / lonSpan) * (width - pad * 2); }
  function y(lat) { return height - pad - ((lat - minLat) / latSpan) * (height - pad * 2); }

  const px = m => [x(m.lonDec), y(m.latDec)];
  const along = (a, b, f) => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];

  let svg = `<svg class="courseChartFallback" viewBox="0 0 ${width} ${height}" role="img" aria-label="Course chart">`;
  svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="#f8fafc"/>`;

  // The same as the map: grey marks off the course, legs coloured by rounding,
  // leg numbers in circles, and each course mark once with its ID.
  for (const m of marks) {
    if (onCourse.has(m.id)) continue;
    const [mx, my] = px(m);
    svg += `<circle cx="${mx}" cy="${my}" r="3" fill="#7d776a"/>`;
    svg += `<text x="${mx + 6}" y="${my + 4}" font-size="11" fill="#7d776a" font-weight="600">${m.id}</text>`;
  }
  for (const leg of model.legs) {
    const [x1, y1] = px(leg.from), [x2, y2] = px(leg.to);
    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${leg.colour}" stroke-width="5" stroke-linecap="round"${leg.rounding === "F" ? ' stroke-dasharray="10 8"' : ""}/>`;
  }
  for (const group of model.legGroups) {
    const a = px(group.from), b = px(group.to);
    const [ax, ay] = along(a, b, 0.7);
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
    svg += `<path d="M-8,-6 L8,0 L-8,6 z" transform="translate(${ax} ${ay}) rotate(${angle})" fill="${group.colour}"/>`;
    // To the right of the direction of travel, as on the map.
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const [cx, cy] = along(a, b, 0.4);
    const nx = cx - (b[1] - a[1]) / len * CHART_LEG_NO_OFFSET;
    const ny = cy + (b[0] - a[0]) / len * CHART_LEG_NO_OFFSET;
    const label = group.numbers.join(", ");
    const w = Math.max(20, 8 + label.length * 7);
    svg += `<rect x="${nx - w / 2}" y="${ny - 10}" width="${w}" height="20" rx="10" fill="white" stroke="${group.colour}" stroke-width="2"/>`;
    svg += `<text x="${nx}" y="${ny + 4}" text-anchor="middle" font-size="11" fill="#1c1a15" font-weight="700">${label}</text>`;
  }
  for (const stop of model.stops) {
    const [sx, sy] = px(stop.mark);
    svg += `<circle cx="${sx}" cy="${sy}" r="7" fill="${stop.colour}" stroke="white" stroke-width="2"/>`;
    svg += `<text x="${sx + 12}" y="${sy + 5}" font-size="14" fill="#1c1a15" font-weight="800">${stop.mark.id}</text>`;
    if (stop.roles.length) {
      svg += `<text x="${sx + 12 + stop.mark.id.length * 10}" y="${sy + 5}" font-size="10" fill="#4a463c" font-weight="700">${stop.roles.join(" · ").toUpperCase()}</text>`;
    }
  }

  svg += `</svg>`;
  el.innerHTML = svg;

  if (routeMarks.length < 2) {
    noCourseChartStatus(status, "Map library unavailable. ");
  } else if (status) {
    status.textContent = `Leaflet unavailable; showing SVG fallback with ${routeMarks.length} route points.`;
    status.className = "status good";
  }
}


async function uploadSelectedFile(type) {
  const input = type === "sailchart" ? document.getElementById("sailchartBrowse") : (type === "polar" ? document.getElementById("polarBrowse") : document.getElementById("marksBrowse"));
  const status = document.getElementById("settingsStatus");

  if (!input.files || !input.files.length) {
    status.textContent = "Choose a file first.";
    status.className = "status bad";
    return;
  }

  const form = new FormData();
  form.append("type", type);
  form.append("file", input.files[0]);

  try {
    const r = await fetch("/api/upload_file", { method:"POST", body: form });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Upload failed");

    // The upload saved this one file setting; other unsaved edits stay as they are.
    document.getElementById("sailchartFile").value = data.settings.sailchart_file || "";
    document.getElementById("expeditionMarksFile").value = data.settings.expedition_marks_file || "";
    document.getElementById("polarFile").value = data.settings.polar_file || "J122.txt";

    status.textContent = `Selected file copied into app folder as ${data.filename}.`;
    status.className = "status good";

    await loadSailChart();
    await loadPolar();
    await loadExpeditionGroups();
    await checkFileStatus();
  } catch (e) {
    status.textContent = `Could not use selected file: ${e.message}`;
    status.className = "status bad";
  }
}


// The Race Officer address is edited on the Settings page only; the Race
// Officer import page shows it.
async function loadRaceOfficerBase() {
  const shown = document.getElementById("raceOfficerBaseShown");
  try {
    const r = await fetch("/api/race_officer/base?_=" + Date.now(), { cache:"no-store" });
    const data = await r.json();
    if (shown && r.ok && data.ok) shown.textContent = data.base || "not set";
  } catch(e) {
    if (shown) shown.textContent = "unknown";
  }
}

async function previewRaceOfficerCurrent() {
  const status = document.getElementById("raceOfficerStatus");
  status.textContent = "Reading current Race Officer course…";
  status.className = "status";

  try {
    const r = await fetch("/api/race_officer/current_preview?_=" + Date.now(), { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Preview failed");
    const base = data.base;

    const raceName = (data.race && data.race.race_name) || "current race";
    if (data.course_set === false) {
      status.textContent = `Connected to ${base}. ${raceName}: the race officer has not set a course yet, so nothing will be imported.`;
      status.className = "status";
    } else {
      status.textContent = `Connected to ${base}. ${raceName}: course ${data.course_name}; ${data.marks_count} marks; route ${data.course}.`;
      status.className = "status good";
    }
  } catch(e) {
    status.textContent = `Could not read Race Officer current course: ${e.message}`;
    status.className = "status bad";
  }
}

async function importRaceOfficerCurrent() {
  const status = document.getElementById("raceOfficerStatus");
  status.textContent = "Importing current Race Officer course…";
  status.className = "status";

  try {
    const r = await fetch("/api/race_officer/import_current", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({}),
      cache:"no-store"
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Import failed");
    const base = data.base;

    await loadMarks();
    await loadCourse();
    await loadCurrentLeg();
    render();
    await refreshCourseStateSignature();
    renderCourseChart();

    status.textContent = `Imported from ${base}: ${data.course_name}; ${data.marks_count} marks; course ${data.course}.`;
    status.className = "status good";
  } catch(e) {
    status.textContent = `Could not import Race Officer current course: ${e.message}`;
    status.className = "status bad";
  }
}


// Race Officer polling controls. The server poller is primary; this page also
// runs a backup poll while it is open so the operator gets immediate feedback.
let raceOfficerPollClientTimer = null;

async function loadRaceOfficerPollStatus() {
  const statusEl = document.getElementById("raceOfficerPollStatus");
  try {
    const r = await fetch("/api/race_officer/poll_status?_=" + Date.now(), { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not read polling status");

    const enabled = document.getElementById("raceOfficerPollEnabled");
    const interval = document.getElementById("raceOfficerPollInterval");
    if (enabled) enabled.checked = !!data.enabled;
    if (interval) interval.value = data.interval_seconds || 10;

    const state = data.state || {};
    if (statusEl) {
      const mode = `Auto-import ${data.enabled ? "enabled" : "disabled"}`;
      const raceName = (state.race && state.race.race_name) || "current race";
      let msg;
      if (state.error) msg = `${mode}; last error: ${state.error}`;
      else if (state.course_pending) msg = `${mode}; ${raceName}: waiting for the race officer to set a course. Showing: ${state.course || "no course imported"}`;
      else msg = `${mode}; last course: ${state.course || "not checked yet"}`;
      statusEl.textContent = msg;
    }

    if (data.enabled) startRaceOfficerClientPollTimer(data.interval_seconds || 10);
    else stopRaceOfficerClientPollTimer();
  } catch(e) {
    if (statusEl) statusEl.textContent = `Could not read polling status: ${e.message}`;
  }
}

let raceOfficerAutoPollBusy = false;

function startRaceOfficerClientPollTimer(intervalSeconds) {
  stopRaceOfficerClientPollTimer();
  raceOfficerPollClientTimer = setInterval(function() {
    raceOfficerAutoPollTick();
  }, Math.max(5, intervalSeconds || 10) * 1000);
}

function stopRaceOfficerClientPollTimer() {
  if (raceOfficerPollClientTimer) clearInterval(raceOfficerPollClientTimer);
  raceOfficerPollClientTimer = null;
}

async function raceOfficerAutoPollTick() {
  const enabledBox = document.getElementById("raceOfficerPollEnabled");
  if (!enabledBox || !enabledBox.checked || raceOfficerAutoPollBusy) return;

  raceOfficerAutoPollBusy = true;
  try {
    await pollRaceOfficerOnce(true);
  } finally {
    raceOfficerAutoPollBusy = false;
  }
}

async function setRaceOfficerPolling() {
  const status = document.getElementById("raceOfficerStatus");
  try {
    const enabled = document.getElementById("raceOfficerPollEnabled").checked;
    const interval = Number(document.getElementById("raceOfficerPollInterval").value || 10);

    status.textContent = enabled ? "Enabling Race Officer course polling…" : "Disabling Race Officer course polling…";
    status.className = "status";

    const r = await fetch("/api/race_officer/poll_config", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ enabled, interval_seconds: interval })
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not update polling mode");

    status.textContent = enabled
      ? `Auto-import enabled. Checking every ${data.interval_seconds} seconds.`
      : "Auto-import disabled.";
    status.className = "status good";

    await loadRaceOfficerPollStatus();
    if (enabled) await pollRaceOfficerOnce(true);
  } catch(e) {
    status.textContent = `Could not update polling mode: ${e.message}`;
    status.className = "status bad";
  }
}

async function pollRaceOfficerOnce(silent) {
  const status = document.getElementById("raceOfficerStatus");
  if (!silent) {
    status.textContent = "Checking Race Officer course now…";
    status.className = "status";
  }

  try {
    const r = await fetch("/api/race_officer/poll_once", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({}),
      cache:"no-store"
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Check failed");

    if (data.changed) {
      await loadMarks();
      await loadCourse();
      await loadCurrentLeg();
      render();
      renderCourseChart();
      await refreshCourseStateSignature();
    }

    const pollStatus = document.getElementById("raceOfficerPollStatus");
    if (data.course_set === false) {
      const raceName = (data.race && data.race.race_name) || "current race";
      if (pollStatus) pollStatus.textContent = `Auto-import active; last checked ${new Date().toLocaleTimeString()}; ${raceName}: waiting for the race officer to set a course.`;
      if (!silent) {
        status.textContent = `${raceName}: the race officer has not set a course yet. The current course here is unchanged.`;
        status.className = "status";
        await loadRaceOfficerPollStatus();
      }
      return;
    }
    if (pollStatus) {
      pollStatus.textContent = data.changed
        ? `Auto-imported Race Officer course: ${data.course}.`
        : `Auto-import active; last checked ${new Date().toLocaleTimeString()}; course ${data.course}.`;
    }

    if (!silent || data.changed) {
      status.textContent = data.changed
        ? `Race Officer course changed and was imported: ${data.course}.`
        : `No Race Officer course change detected: ${data.course}.`;
      status.className = "status good";
    }

    if (!silent) await loadRaceOfficerPollStatus();
  } catch(e) {
    const pollStatus = document.getElementById("raceOfficerPollStatus");
    if (pollStatus) pollStatus.textContent = `Auto-import check failed: ${e.message}`;
    if (!silent) {
      status.textContent = `Could not check Race Officer course: ${e.message}`;
      status.className = "status bad";
    }
  }
}


// Watches local app state so the Course legs page updates after a Race Officer
// auto-import. The Race Officer poller writes runtime/marks.json and
// runtime/course.json on the server; browser pages need to notice that and
// reload their local variables.
let courseStateSignature = "";
let courseStateWatchBusy = false;

function buildCourseStateSignatureFromLocal() {
  const ids = parseCourse(document.getElementById("course").value);
  return JSON.stringify({
    course: (document.getElementById("course").value || "").trim(),
    ids: ids,
    roundings: courseRoundings || {},
    marks: marks.map(m => ({
      id: m.id,
      lat: m.lat,
      lon: m.lon,
      name: m.name
    })),
    currentLeg: currentLegIndex
  });
}

async function refreshCourseStateSignature() {
  courseStateSignature = buildCourseStateSignatureFromLocal();
}

async function reloadCourseStateFromServer(reason) {
  await loadMarks();
  await loadCourse();
  await loadCurrentLeg();
  render();
  renderCourseChart();
  refreshCourseStateSignature();

  const status = document.getElementById("status");
  if (status && reason) {
    status.textContent = reason;
    status.className = "status good";
  }
}

async function checkForSavedCourseStateChange() {
  if (courseStateWatchBusy) return;
  courseStateWatchBusy = true;

  try {
    const [marksResp, courseResp, currentResp] = await Promise.all([
      fetch("/api/marks?_=" + Date.now(), { cache:"no-store" }),
      fetch("/api/course?_=" + Date.now(), { cache:"no-store" }),
      fetch("/api/current_leg?_=" + Date.now(), { cache:"no-store" })
    ]);

    const marksData = await marksResp.json();
    const courseData = await courseResp.json();
    const currentData = await currentResp.json();

    if (!marksResp.ok || !marksData.ok) throw new Error(marksData.error || "Could not read marks");
    if (!courseResp.ok || !courseData.ok) throw new Error(courseData.error || "Could not read course");
    if (!currentResp.ok || !currentData.ok) throw new Error(currentData.error || "Could not read current leg");

    const remoteSignature = JSON.stringify({
      course: (courseData.course || "").trim(),
      ids: String(courseData.course || "").trim().toUpperCase().split(/[\s\-]+/).filter(Boolean),
      roundings: courseData.roundings || {},
      marks: (marksData.marks || []).map(m => ({
        id: m.id,
        lat: m.lat,
        lon: m.lon,
        name: m.name
      })),
      currentLeg: Number(currentData.current_leg || 0)
    });

    if (!courseStateSignature) {
      courseStateSignature = remoteSignature;
    } else if (remoteSignature !== courseStateSignature) {
      await reloadCourseStateFromServer("Course updated from saved app state.");
    }
  } catch(e) {
    // Do not disturb the main race display for a transient network/read error.
    const raceStatus = document.getElementById("raceOfficerPollStatus");
    if (raceStatus) raceStatus.textContent = `Course state watch: ${e.message}`;
  } finally {
    courseStateWatchBusy = false;
  }
}

function startCourseStateWatcher() {
  refreshCourseStateSignature();
  setInterval(checkForSavedCourseStateChange, 3000);
}


async function loadSettings() {
  const status = document.getElementById("settingsStatus");
  try {
    const r = await fetch("/api/settings", { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not load settings");
    document.getElementById("sailchartFile").value = data.settings.sailchart_file || "";
    document.getElementById("expeditionMarksFile").value = data.settings.expedition_marks_file || "";
    document.getElementById("polarFile").value = data.settings.polar_file || "J122.txt";
    document.getElementById("raceOfficerApiBase").value = data.settings.race_officer_api_base || "";
    document.getElementById("instrumentSource").value = data.settings.instrument_source || "expedition";
    document.getElementById("h5000Host").value = data.settings.h5000_host || "";
    document.getElementById("h5000Port").value = data.settings.h5000_port || 2053;
    document.getElementById("nmeaHost").value = data.settings.nmea_host || "";
    document.getElementById("nmeaPort").value = data.settings.nmea_port || 10110;
    showInstrumentSourceFields();
    setSettingsDirty(false);
    loadInstrumentStatus();
    loadRaceOfficerSettingsStatus();
    if (status) { status.textContent = "Settings loaded."; status.className = "status good"; }
  } catch (e) {
    if (status) { status.textContent = `Could not load settings: ${e.message}`; status.className = "status bad"; }
  }
}

async function saveSettings() {
  const status = document.getElementById("settingsStatus");
  try {
    const payload = {
      sailchart_file: document.getElementById("sailchartFile").value.trim(),
      expedition_marks_file: document.getElementById("expeditionMarksFile").value.trim(),
      polar_file: document.getElementById("polarFile").value.trim(),
      race_officer_api_base: document.getElementById("raceOfficerApiBase").value.trim().replace(/\/+$/, ""),
      instrument_source: document.getElementById("instrumentSource").value,
      h5000_host: document.getElementById("h5000Host").value.trim(),
      h5000_port: Number(document.getElementById("h5000Port").value),
      nmea_host: document.getElementById("nmeaHost").value.trim(),
      nmea_port: Number(document.getElementById("nmeaPort").value)
    };
    const r = await fetch("/api/settings", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not save settings");

    status.textContent = `Settings saved at ${new Date().toLocaleTimeString()}.`;
    status.className = "status good";
    setSettingsDirty(false);
    loadRaceOfficerBase();
    loadWind();
    setTimeout(loadInstrumentStatus, 1500);   // give a new source a moment to connect
    loadRaceOfficerSettingsStatus();
    await loadSailChart();
    await loadPolar();
    await loadExpeditionGroups();
    await checkFileStatus();
  } catch (e) {
    status.textContent = `Could not save settings: ${e.message}`;
    status.className = "status bad";
  }
}

// -- Instrument source ------------------------------------------------------

// Only the address fields for the selected network source are shown.
function showInstrumentSourceFields() {
  const source = document.getElementById("instrumentSource").value;
  document.getElementById("h5000Fields").style.display = source === "h5000" ? "flex" : "none";
  document.getElementById("nmeaFields").style.display = source === "nmea0183" ? "flex" : "none";
}

// The running source (as saved, not as edited) and whether data is arriving.
async function loadInstrumentStatus() {
  const el = document.getElementById("instrumentStatus");
  if (!el) return;
  try {
    const r = await fetch("/api/instruments", { cache:"no-store" });
    const s = await r.json();
    const where = s.host ? ` at ${s.host}:${s.port}` : "";
    const ages = s.channel_ages || {};
    const fresh = Object.keys(ages).filter(k => ages[k] <= 5);
    if (s.connected) {
      el.textContent = `${s.label}${where}: connected` + (s.host ? `; receiving ${fresh.length ? fresh.join(", ") : "no data yet"}` : "");
      el.className = "status good";
    } else {
      el.textContent = `${s.label}${where}: not connected` + (s.error ? ` (${s.error})` : "");
      el.className = "status bad";
    }
  } catch (e) {
    el.textContent = `Could not read instrument status: ${e.message}`;
    el.className = "status bad";
  }
}

// Unsaved changes: any edit to a [data-setting] field marks the page until it
// is saved or the changes are discarded (which reloads the saved settings).
let settingsDirty = false;

function setSettingsDirty(dirty) {
  settingsDirty = dirty;
  const note = document.getElementById("settingsDirty");
  if (note) note.hidden = !dirty;
}

document.querySelectorAll("#settingsView [data-setting]").forEach(el => {
  el.addEventListener("input", () => setSettingsDirty(true));
  el.addEventListener("change", () => setSettingsDirty(true));
});

// Whether the saved Race Officer address is answering (from the poller's last check).
async function loadRaceOfficerSettingsStatus() {
  const el = document.getElementById("raceOfficerSettingsStatus");
  if (!el) return;
  try {
    const r = await fetch("/api/race_officer/poll_status?_=" + Date.now(), { cache:"no-store" });
    const data = await r.json();
    const state = data.state || {};
    const age = state.last_check ? Math.round(Date.now() / 1000 - state.last_check) : null;
    const when = age === null ? "" : ` ${age} s ago`;
    if (!data.enabled) {
      el.textContent = "Auto-import is off; the address is used when you preview or import on the Race Officer import page.";
      el.className = "status";
    } else if (state.error) {
      el.textContent = `Auto-import on; last check${when} failed: ${state.error}`;
      el.className = "status bad";
    } else if (state.last_check) {
      const race = (state.race && state.race.race_name) ? `: ${state.race.race_name}` : "";
      el.textContent = `Auto-import on; last check${when} OK${race}.`;
      el.className = "status good";
    } else {
      el.textContent = "Auto-import on; not checked yet.";
      el.className = "status";
    }
  } catch (e) {
    el.textContent = `Could not read Race Officer status: ${e.message}`;
    el.className = "status bad";
  }
}

// Keep the statuses fresh while the Settings page is open.
setInterval(() => {
  const view = document.getElementById("settingsView");
  if (view && view.classList.contains("active")) {
    loadInstrumentStatus();
    loadRaceOfficerSettingsStatus();
  }
}, 2000);

async function checkFileStatus() {
  const target = document.getElementById("fileStatus");
  if (!target) return;
  try {
    const r = await fetch("/api/file_status", { cache:"no-store" });
    const data = await r.json();
    target.innerHTML = `
      <div>Sail chart: <span class="mono">${data.sailchart_file}</span> — <strong>${data.sailchart_exists ? "found" : "not found"}</strong></div>
      <div>Expedition marks: <span class="mono">${data.expedition_marks_file}</span> — <strong>${data.expedition_marks_exists ? "found" : "not found"}</strong></div>
      <div>Polar: <span class="mono">${data.polar_file}</span> — <strong>${data.polar_exists ? "found" : "not found"}</strong></div>
    `;
  } catch (e) {
    target.textContent = `Could not check files: ${e.message}`;
  }
}

async function loadExpeditionGroups() {
  const status = document.getElementById("importStatus");
  const tbody = document.getElementById("expeditionGroups");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" class="small">Loading…</td></tr>`;
  try {
    const r = await fetch("/api/expedition_marks/groups", { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not read marks.xml");

    tbody.innerHTML = "";
    for (const g of data.groups) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${g.name}</strong></td>
        <td>${g.count}</td>
        <td><button onclick="importExpeditionGroup('${String(g.name).replace(/'/g, "\\'")}')">Import</button></td>
      `;
      tbody.appendChild(tr);
    }
    status.textContent = `Found ${data.groups.length} groups in marks.xml.`;
    status.className = "status good";
  } catch (e) {
    tbody.innerHTML = "";
    status.textContent = `Could not read Expedition marks: ${e.message}`;
    status.className = "status bad";
  }
}

async function importExpeditionGroup(group) {
  const status = document.getElementById("importStatus");
  const replace = document.getElementById("replaceMarksOnImport").checked;
  try {
    const r = await fetch("/api/expedition_marks/import", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({group, replace})
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Import failed");

    marks = normaliseMarks(data.marks);
    rebuildMarkIndex();
    initialiseMarks();
    renderMarksEditor();
    render();
    status.textContent = `Imported ${data.imported_count} marks from group "${group}" into marks.json.`;
    status.className = "status good";
  } catch (e) {
    status.textContent = `Could not import group "${group}": ${e.message}`;
    status.className = "status bad";
  }
}

async function loadMarks() {
  const status = document.getElementById("marksEditStatus");
  try {
    const r = await fetch("/api/marks", { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not load marks.json");
    marks = normaliseMarks(data.marks);
    rebuildMarkIndex();
    initialiseMarks();
    renderMarksEditor();
    render();
    renderCourseChart();
    if (status) { status.textContent = "Marks loaded."; status.className = "status good"; }
  } catch (e) {
    if (status) { status.textContent = `Marks unavailable: ${e.message}`; status.className = "status bad"; }
  }
}

function renderMarksEditor() {
  const tbody = document.getElementById("marksEditor");
  if (!tbody) return;
  tbody.innerHTML = "";
  for (const m of marks) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input value="${m.id}" data-field="id" style="width:70px;text-transform:uppercase;"></td>
      <td><input value="${m.name}" data-field="name" style="min-width:230px;"></td>
      <td><input value="${MojitoLegs.formatPosition(m.latDec, false)}" data-field="lat" class="mono" style="min-width:150px;"></td>
      <td><input value="${MojitoLegs.formatPosition(m.lonDec, true)}" data-field="lon" class="mono" style="min-width:150px;"></td>
      <td><button class="secondary danger" onclick="this.closest('tr').remove()">Delete</button></td>
    `;
    tbody.appendChild(tr);
  }
}

function addMarkRow() {
  const tbody = document.getElementById("marksEditor");
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input value="" data-field="id" style="width:70px;text-transform:uppercase;" placeholder="X"></td>
    <td><input value="" data-field="name" style="min-width:230px;" placeholder="Mark name"></td>
    <td><input value="" data-field="lat" class="mono" style="min-width:150px;" placeholder="50 39.330N"></td>
    <td><input value="" data-field="lon" class="mono" style="min-width:150px;" placeholder="01 55.170W"></td>
    <td><button class="secondary danger" onclick="this.closest('tr').remove()">Delete</button></td>
  `;
  tbody.appendChild(tr);
}

async function saveMarks() {
  const status = document.getElementById("marksEditStatus");
  const rows = [...document.querySelectorAll("#marksEditor tr")];
  const edited = rows.map(row => {
    const get = field => row.querySelector(`[data-field="${field}"]`).value.trim();
    return { id:get("id").toUpperCase(), name:get("name"), lat:get("lat"), lon:get("lon") };
  }).filter(m => m.id);

  try {
    // Every position must read, and is saved as degrees and decimal minutes.
    const unreadable = [];
    for (const m of edited) {
      const lat = parsePosition(m.lat), lon = parsePosition(m.lon);
      if (!Number.isFinite(lat) || Math.abs(lat) > 90) unreadable.push(`${m.id} latitude "${m.lat}"`);
      if (!Number.isFinite(lon) || Math.abs(lon) > 180) unreadable.push(`${m.id} longitude "${m.lon}"`);
      m.lat = MojitoLegs.formatPosition(lat, false);
      m.lon = MojitoLegs.formatPosition(lon, true);
    }
    if (unreadable.length) throw new Error(`cannot read ${unreadable.join(", ")}. Use e.g. 50 39.330N and 01 55.170W.`);
    const r = await fetch("/api/marks", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({marks: edited})
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not save marks.json");
    marks = normaliseMarks(data.marks);
    rebuildMarkIndex();
    initialiseMarks();
    renderMarksEditor();
    render();
    status.textContent = "Marks saved.";
    status.className = "status good";
  } catch (e) {
    status.textContent = `Could not save marks: ${e.message}`;
    status.className = "status bad";
  }
}

async function loadPolar(){
  const status=document.getElementById("status");
  try {
    const r = await fetch("/api/polar", { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not load polar file");
    polarData = { rows: data.rows };
    polarLoaded = true;
    render();
    renderCourseChart();
  } catch (e) {
    polarLoaded = false;
    if (status) {
      status.textContent = `Polar unavailable: ${e.message}`;
      status.className = "status bad";
    }
  }
}

async function loadSailChart(){
  const status=document.getElementById("status");
  try {
    const r = await fetch("/api/sailchart", { cache:"no-store" });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not load sail chart file");
    sailChart = { twas: data.twas, rows: data.rows };
    sailChartLoaded = true;
    render();
  } catch (e) {
    sailChartLoaded = false;
    status.textContent = `Sail chart unavailable: ${e.message}`;
    status.className = "status bad";
  }
}


async function loadCurrentLeg() {
  try {
    const r = await fetch("/api/current_leg", { cache:"no-store" });
    const data = await r.json();
    if (r.ok && data.ok) {
      currentLegIndex = Math.max(0, Number(data.current_leg || 0));
      render();
    }
  } catch(e) {
    console.warn("Could not load current leg", e);
  }
}

async function saveCurrentLeg() {
  try {
    await fetch("/api/current_leg", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({current_leg: currentLegIndex})
    });
  } catch(e) {
    console.warn("Could not save current leg", e);
  }
}

function moveCurrentLeg(delta) {
  const legs = routeLegs();
  if (!legs.length) return;
  currentLegIndex = Math.max(0, Math.min(legs.length - 1, currentLegIndex + delta));
  saveCurrentLeg();
  render();
}

function updateCurrentLegStatus(legs) {
  const status = document.getElementById("currentLegStatus");
  if (!status) return;
  if (!legs.length) {
    status.textContent = "Leg —";
    return;
  }
  currentLegIndex = Math.max(0, Math.min(legs.length - 1, currentLegIndex));
  const leg = legs[currentLegIndex];
  status.textContent = `Current: ${currentLegIndex + 1}/${legs.length} ${leg.from.id} → ${leg.to.id}`;
}

function currentRouteKey(index, fromId, toId) {
  return `${index}:${fromId}-${toId}`;
}

function scheduleSaveCourse() {
  if (loadingCourse) return;
  if (saveCourseTimer) window.clearTimeout(saveCourseTimer);
  saveCourseTimer = window.setTimeout(saveCourseNow, 250);
}

async function saveCourseNow() {
  try {
    const payload = {
      course: document.getElementById("course").value.trim(),
      roundings: courseRoundings
    };
    const r = await fetch("/api/course", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Could not save course");
  } catch (e) {
    console.warn("Could not save course", e);
  }
}

async function loadCourse() {
  loadingCourse = true;
  try {
    const r = await fetch("/api/course", { cache:"no-store" });
    const data = await r.json();
    if (r.ok && data.ok) {
      document.getElementById("course").value = data.course || "";
      courseRoundings = data.roundings || {};
    }
  } catch (e) {
    console.warn("Could not load course", e);
  } finally {
    loadingCourse = false;
    render();
  }
}

function setRounding(key, value) {
  courseRoundings[key] = value;
  scheduleSaveCourse();
  render();
  renderCourseChart();
}

function roundingLabel(value) {
  if (value === "P") return "Port";
  if (value === "S") return "Starboard";
  if (value === "V") return "Via waypoint";
  if (value === "F") return "Finish";
  return "Unspecified";
}

// V = via a waypoint (not rounded) and F = run to the finish; both come from
// a Race Officer import (see FINISH_MARK_ID in server/race_officer.py).
function roundingBadge(value) {
  if (value === "P") return `<span class="roundBadge roundBadgePort">Port</span>`;
  if (value === "S") return `<span class="roundBadge roundBadgeStarboard">Starboard</span>`;
  if (value === "V") return `<span class="roundBadge roundBadgeNone">Via</span>`;
  if (value === "F") return `<span class="roundBadge roundBadgeNone">Finish</span>`;
  return `<span class="roundBadge roundBadgeNone">—</span>`;
}

function appendMarkToCourse(markId, rounding = "") {
  const input = document.getElementById("course");
  const existingRoute = parseCourse(input.value);
  const current = input.value.trim();
  input.value = current ? `${current} ${markId}` : markId;

  // Rounding applies to the mark just added, i.e. the destination mark of the new leg.
  // The first mark is a start/reference point, so it has no inbound leg to round.
  if (existingRoute.length >= 1) {
    const legIndex = existingRoute.length - 1;
    const fromId = existingRoute[existingRoute.length - 1];
    const toId = markId;
    const key = currentRouteKey(legIndex, fromId, toId);
    courseRoundings[key] = rounding;
  }

  scheduleSaveCourse();
  render();
  renderCourseChart();
}

function clearCourse() {
  document.getElementById("course").value = "";
  courseRoundings = {};
  scheduleSaveCourse();
  render();
  renderCourseChart();
}

function undoLastCourseMark() {
  const input = document.getElementById("course");
  const parts = parseCourse(input.value);
  parts.pop();
  input.value = parts.join(" ");
  const keep = {};
  for (const key of Object.keys(courseRoundings)) {
    const idx = Number(key.split(":")[0]);
    if (idx < parts.length - 1) keep[key] = courseRoundings[key];
  }
  courseRoundings = keep;
  scheduleSaveCourse();
  render();
  renderCourseChart();
}

function initialiseMarks(){
  rebuildMarkIndex();

  const markButtons = marks.map(m=>`
    <span class="markAddGroup" title="${m.name}">
      <span class="markAddLabel">${m.id}</span>
      <button type="button" class="addPort" onclick="appendMarkToCourse('${m.id}', 'P')">P</button>
      <button type="button" class="addStarboard" onclick="appendMarkToCourse('${m.id}', 'S')">S</button>
    </span>
  `).join("");

  const markPills = document.getElementById("markPills");
  if (markPills) markPills.innerHTML = markButtons;


}
document.getElementById("course").addEventListener("input", () => { scheduleSaveCourse(); render(); renderCourseChart(); });
document.getElementById("twd").addEventListener("input", manualWindEdited);
document.getElementById("tws").addEventListener("input", manualWindEdited);
loadSettings(); loadMarks(); loadCourse(); loadCurrentLeg(); loadSailChart(); loadPolar(); loadWind(); showView('results');
setTimeout(startCourseStateWatcher, 1000);
setTimeout(publishDisplayWind, 1500);
setInterval(publishDisplayWind, 1000);
renderCourseChart();
currentLegTimer = window.setInterval(loadCurrentLeg, 2000);
setInterval(() => loadWind(), 1000);

// Start bar under the Course legs heading (static/race_start.js), styled as an
// instrument panel in index.css.
MojitoRaceStart.attach("raceStartBar", {theme: "dark"});
