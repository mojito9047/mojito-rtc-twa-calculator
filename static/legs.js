// Leg calculations shared by the Course legs, phone and MFD pages.
//
// Positions, route, bearing and range, TWA and tack, sail choice from the sail
// chart, and target speed from the polar (with upwind/downwind VMG targets).
// Until v63 each page had its own copy of this code, and the copies drifted.
//
// Everything takes its data as arguments; nothing reads page globals or the
// DOM. Written in ES5 because the MFD's embedded browser is old (see
// tests/test_js.py, LegacyBrowserTests). Display formatting stays in the pages.
var MojitoLegs = (function() {

  function toRad(d) { return d * Math.PI / 180; }
  function toDeg(r) { return r * 180 / Math.PI; }
  function norm360(d) { return ((d % 360) + 360) % 360; }

  // "52.878", "-4.405", "52.878N", "52° 52.700'N", "01 55.17 W" -> decimal degrees, or NaN.
  function parsePosition(value) {
    var raw = String(value == null ? "" : value).replace(/^\s+|\s+$/g, "");
    if (!raw) return NaN;

    // Decimal degrees, optionally with N/S/E/W suffix.
    var m = raw.match(/^(-?\d+(?:\.\d+)?)\s*([NSEW])?$/i);
    if (m) {
      var v = Number(m[1]);
      var hemi = (m[2] || "").toUpperCase();
      if (hemi === "S" || hemi === "W") v = -Math.abs(v);
      return v;
    }

    // Degrees and decimal minutes, e.g. 50° 39.33N or 01 55.17 W.
    m = raw.match(/^(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)\D*([NSEW])$/i);
    if (m) {
      var dm = Number(m[1]) + Number(m[2]) / 60;
      var h = m[3].toUpperCase();
      if (h === "S" || h === "W") dm = -dm;
      return dm;
    }
    return NaN;
  }

  // Decimal degrees -> degrees and decimal minutes as sailors write them:
  // 50.6555 -> "50 39.330N", -1.9195 -> "01 55.170W". Three decimals of a minute
  // (about 2 m) keep Race Officer positions exact. "" if value is not a number.
  function formatPosition(value, isLon, decimals) {
    if (typeof value !== "number" || !isFinite(value)) return "";
    decimals = decimals === undefined ? 3 : decimals;
    var hemi = isLon ? (value < 0 ? "W" : "E") : (value < 0 ? "S" : "N");
    var scale = Math.pow(10, decimals);
    var totalMinutes = Math.round(Math.abs(value) * 60 * scale) / scale;   // round once, so 59.9996' becomes the next degree
    var deg = Math.floor(totalMinutes / 60 + 1e-9);
    var minutes = totalMinutes - deg * 60;
    if (minutes < 0) minutes = 0;
    var minText = minutes.toFixed(decimals);
    if (minutes < 10) minText = "0" + minText;
    var degText = String(deg);
    if (deg < 10) degText = "0" + degText;
    return degText + " " + minText + hemi;
  }

  // Marks from /api/marks with latDec/lonDec added. IDs are upper-cased; marks
  // without an ID or a readable position are dropped. Other fields are kept.
  function normaliseMarks(raw) {
    var out = [];
    for (var i = 0; i < (raw || []).length; i++) {
      var src = raw[i] || {};
      var mark = {};
      for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k)) mark[k] = src[k];
      mark.id = String(src.id || "").replace(/^\s+|\s+$/g, "").toUpperCase();
      mark.name = String(src.name || src.id || "").replace(/^\s+|\s+$/g, "");
      mark.latDec = parsePosition(src.lat);
      mark.lonDec = parsePosition(src.lon);
      if (mark.id && isFinite(mark.latDec) && isFinite(mark.lonDec)) out.push(mark);
    }
    return out;
  }

  function markIndex(marks) {
    var byId = {};
    for (var i = 0; i < marks.length; i++) byId[marks[i].id] = marks[i];
    return byId;
  }

  // "O 1-8 4" -> ["O", "1", "8", "4"], keeping only IDs in markById.
  function parseCourse(text, markById) {
    var parts = String(text || "").toUpperCase().replace(/[^A-Z0-9\- ]/g, " ").split(/[\s\-]+/);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] && markById[parts[i]]) out.push(parts[i]);
    }
    return out;
  }

  // Initial great-circle bearing (degrees true) and distance (nm) between marks.
  function bearingAndDistance(from, to) {
    var lat1 = toRad(from.latDec), lat2 = toRad(to.latDec), dLon = toRad(to.lonDec - from.lonDec);
    var y = Math.sin(dLon) * Math.cos(lat2);
    var x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    var bearing = norm360(toDeg(Math.atan2(y, x)));
    var dLat = lat2 - lat1;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return {bearing: bearing, distanceNm: 3440.065 * c};
  }

  // Smallest angle between two directions, 0-180.
  function angleDiff(a, b) { return Math.abs(((a - b + 540) % 360) - 180); }

  // Tack sailing a bearing in wind from twd: "S" (starboard), "P" (port), or ""
  // dead upwind or downwind.
  function tack(bearing, twd) {
    var signed = ((twd - bearing + 540) % 360) - 180;
    if (Math.abs(signed) < 0.5 || Math.abs(Math.abs(signed) - 180) < 0.5) return "";
    return signed > 0 ? "S" : "P";
  }

  // Legs of a route of mark IDs: {from, to, bearing, distanceNm, twa}.
  function routeLegs(ids, markById, twd) {
    var legs = [];
    for (var i = 0; i < ids.length - 1; i++) {
      var from = markById[ids[i]], to = markById[ids[i + 1]];
      var bd = bearingAndDistance(from, to);
      legs.push({from: from, to: to, bearing: bd.bearing, distanceNm: bd.distanceNm,
                 twa: angleDiff(bd.bearing, twd)});
    }
    return legs;
  }

  // -- Sail chart -----------------------------------------------------------

  function nearest(values, target) {
    var best = values[0], bestDiff = Math.abs(values[0] - target);
    for (var i = 1; i < values.length; i++) {
      var d = Math.abs(values[i] - target);
      if (d < bestDiff) { best = values[i]; bestDiff = d; }
    }
    return best;
  }

  function firstIndex(values, value) {
    for (var i = 0; i < values.length; i++) if (values[i] === value) return i;
    return -1;
  }

  // Sail for a TWA/TWS from /api/sailchart data ({twas, rows: [{tws, sails}]}):
  // nearest TWS row and nearest TWA column. A heading can repeat (J122 North has
  // two 36° columns); the first match is used. "—" when the cell is blank.
  function sailFor(sailChart, twa, tws) {
    if (!sailChart || !sailChart.twas || !sailChart.twas.length || !sailChart.rows || !sailChart.rows.length) return "—";
    if (typeof tws !== "number" || !isFinite(tws)) return "—";
    var twsValues = [];
    for (var i = 0; i < sailChart.rows.length; i++) twsValues.push(sailChart.rows[i].tws);
    var row = sailChart.rows[firstIndex(twsValues, nearest(twsValues, tws))];
    var col = firstIndex(sailChart.twas, nearest(sailChart.twas, Math.round(twa)));
    var sail = row && col >= 0 ? String(row.sails[col] || "").replace(/^\s+|\s+$/g, "") : "";
    return sail || "—";
  }

  // -- Polar ----------------------------------------------------------------

  // Linear interpolation over points [{x, y}], clamped at the ends.
  function interpolate(points, x) {
    if (!points.length) return null;
    var sorted = points.slice().sort(function(a, b) { return a.x - b.x; });
    if (x <= sorted[0].x) return sorted[0].y;
    if (x >= sorted[sorted.length - 1].x) return sorted[sorted.length - 1].y;
    for (var i = 0; i < sorted.length - 1; i++) {
      var a = sorted[i], b = sorted[i + 1];
      if (x >= a.x && x <= b.x) {
        var f = (x - a.x) / (b.x - a.x || 1);
        return a.y + f * (b.y - a.y);
      }
    }
    return null;
  }

  // A polar row's points with speed, sorted by TWA (drops the 0,0 point).
  function usablePoints(row) {
    var pts = [];
    if (!row || !row.points) return pts;
    for (var i = 0; i < row.points.length; i++) {
      var p = row.points[i];
      if (p.twa > 0 && p.bsp > 0) pts.push(p);
    }
    pts.sort(function(a, b) { return a.twa - b.twa; });
    return pts;
  }

  function rowSpeedAtTwa(row, twa) {
    var pts = usablePoints(row), xy = [];
    for (var i = 0; i < pts.length; i++) xy.push({x: pts[i].twa, y: pts[i].bsp});
    return interpolate(xy, Math.abs(twa));
  }

  function rowMinTwa(row) {
    var pts = usablePoints(row);
    return pts.length ? pts[0].twa : null;
  }

  function rowMaxTwa(row) {
    var pts = usablePoints(row);
    return pts.length ? pts[pts.length - 1].twa : null;
  }

  function downwindVmg(p) { return p.bsp * Math.cos((180 - p.twa) * Math.PI / 180); }

  // The point with the best downwind VMG (TWA 90 or more); the deepest point if none.
  function rowBestDownwindVmg(row) {
    var pts = usablePoints(row);
    if (!pts.length) return null;
    var best = null;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i];
      if (p.twa < 90) continue;
      var vmg = downwindVmg(p);
      if (!best || vmg > best.vmg) best = {twa: p.twa, bsp: p.bsp, vmg: vmg};
    }
    if (!best) {
      var last = pts[pts.length - 1];
      best = {twa: last.twa, bsp: last.bsp, vmg: downwindVmg(last)};
    }
    return best;
  }

  // Apply fn to the polar rows either side of tws and interpolate the result
  // (a number, or an object of numbers). Clamped to the lightest/strongest row.
  function interpolateRowsByTws(rows, tws, fn) {
    if (!rows || !rows.length || typeof tws !== "number" || !isFinite(tws)) return null;
    var sorted = rows.slice().sort(function(a, b) { return a.tws - b.tws; });
    if (tws <= sorted[0].tws) return fn(sorted[0]);
    if (tws >= sorted[sorted.length - 1].tws) return fn(sorted[sorted.length - 1]);
    for (var i = 0; i < sorted.length - 1; i++) {
      var low = sorted[i], high = sorted[i + 1];
      if (tws >= low.tws && tws <= high.tws) {
        var a = fn(low), b = fn(high);
        if (a === null || b === null) return null;
        var f = (tws - low.tws) / (high.tws - low.tws || 1);
        if (typeof a === "number" && typeof b === "number") return a + f * (b - a);
        return {twa: a.twa + f * (b.twa - a.twa), bsp: a.bsp + f * (b.bsp - a.bsp),
                vmg: a.vmg + f * (b.vmg - a.vmg)};
      }
    }
    return null;
  }

  // Target speed for a leg's TWA from /api/polar rows, or null without a polar.
  //   bsp       target boat speed
  //   cmg       speed made good along the leg (used for leg time)
  //   polarTwa  the TWA the target is for
  //   mode      "direct"   the leg's own TWA
  //             "upwind"   tighter than the polar: sail the best upwind angle
  //             "downwind" deeper than the best downwind VMG angle: sail that angle
  //             "limited"  beyond the polar's deepest angle
  function targetSpeedInfo(polarRows, twa, tws) {
    if (!polarRows || !polarRows.length || typeof tws !== "number" || !isFinite(tws)) return null;
    var absTwa = Math.abs(twa);
    var minTwa = interpolateRowsByTws(polarRows, tws, rowMinTwa);
    var maxTwa = interpolateRowsByTws(polarRows, tws, rowMaxTwa);
    if (minTwa === null || maxTwa === null) return null;

    if (absTwa < minTwa) {
      var upBsp = interpolateRowsByTws(polarRows, tws, function(row) { return rowSpeedAtTwa(row, minTwa); });
      if (!upBsp) return null;
      var upCmg = upBsp * Math.cos((minTwa - absTwa) * Math.PI / 180);
      return {bsp: upBsp, cmg: Math.max(0, upCmg), polarTwa: minTwa, mode: "upwind"};
    }

    var bestDw = interpolateRowsByTws(polarRows, tws, rowBestDownwindVmg);
    if (bestDw && bestDw.twa >= 90 && absTwa > bestDw.twa) {
      var dwCmg = bestDw.bsp * Math.cos((absTwa - bestDw.twa) * Math.PI / 180);
      return {bsp: bestDw.bsp, cmg: Math.max(0, dwCmg), polarTwa: bestDw.twa, mode: "downwind"};
    }

    var polarTwa = Math.min(absTwa, maxTwa);
    var bsp = interpolateRowsByTws(polarRows, tws, function(row) { return rowSpeedAtTwa(row, polarTwa); });
    if (!bsp) return null;
    return {bsp: bsp, cmg: bsp, polarTwa: polarTwa, mode: polarTwa !== absTwa ? "limited" : "direct"};
  }

  // -- Bearing bar (phone and MFD) -------------------------------------------

  // Text for the bar: boat to the mark at the end of the current leg, and the
  // leg after it (the course once that mark is rounded). boatPos is
  // {latDec, lonDec} or null without a GPS fix.
  function bearingBar(legs, currentLeg, boatPos) {
    var out = {toMarkLabel: "To mark", toMarkBearing: "—", toMarkRange: "",
               nextLegLabel: "Next leg", nextLegBearing: "—", nextLegRange: ""};
    if (!legs.length) return out;
    var i = Math.max(0, Math.min(legs.length - 1, currentLeg));
    var leg = legs[i];
    out.toMarkLabel = "To " + leg.to.id;
    if (boatPos) {
      var bd = bearingAndDistance(boatPos, leg.to);
      out.toMarkBearing = bd.bearing.toFixed(0) + "°";
      out.toMarkRange = bd.distanceNm.toFixed(2) + " nm";
    } else {
      out.toMarkRange = "No GPS position";
    }
    var next = legs[i + 1];
    if (next) {
      out.nextLegLabel = "Next leg " + next.from.id + "→" + next.to.id;
      out.nextLegBearing = next.bearing.toFixed(0) + "°";
      out.nextLegRange = next.distanceNm.toFixed(2) + " nm";
    } else {
      out.nextLegRange = "Last leg";
    }
    return out;
  }

  return {
    toRad: toRad, toDeg: toDeg, norm360: norm360,
    parsePosition: parsePosition, formatPosition: formatPosition, normaliseMarks: normaliseMarks, markIndex: markIndex,
    parseCourse: parseCourse, bearingAndDistance: bearingAndDistance, angleDiff: angleDiff,
    tack: tack, routeLegs: routeLegs, sailFor: sailFor, interpolate: interpolate,
    targetSpeedInfo: targetSpeedInfo, bearingBar: bearingBar
  };
})();
