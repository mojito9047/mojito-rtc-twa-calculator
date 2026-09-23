// Phone/tablet page (templates/phone.html): start and bearing bar, course
// table, wind history plot.
//
// Loaded after static/legs.js (leg calculations) and static/race_start.js
// (start bar). Functions are global so the page's onclick/onchange
// attributes can call them.

let marks = [];
let markById = {};
let courseText = "";
let courseRoundings = {};
let sailChart = { twas: [], rows: [] };
let polarData = { rows: [] };
let twd = 0;
let tws = 0;
let windManual = false;   // the wind is the manual one from the Wind & Course page
let currentLegIndex = 0;
let boatPos = null;   // {latDec, lonDec} from Expedition, or null with no fix

// Leg calculations are in static/legs.js (MojitoLegs), shared with the Course
// legs and MFD pages. These are the names the rest of this page uses.
const norm360 = MojitoLegs.norm360;
const angleDiff = MojitoLegs.angleDiff;
const bearingAndDistance = MojitoLegs.bearingAndDistance;
function parsePosition(value) { return MojitoLegs.parsePosition(value); }
function normaliseMarks(rawMarks) { return MojitoLegs.normaliseMarks(rawMarks); }
function parseCourse(text) { return MojitoLegs.parseCourse(text, markById); }
function side(courseBearing, twd) {
  const t = MojitoLegs.tack(courseBearing, twd);
  return t === "S" ? "Starboard" : t === "P" ? "Port" : "—";
}
function sailFor(twa, tws) { return MojitoLegs.sailFor(sailChart, twa, tws); }
function targetSpeedInfoFor(twa, tws) { return MojitoLegs.targetSpeedInfo(polarData.rows, twa, tws); }

// Bar: boat to the next mark, and the next leg (same text as the MFD).
function renderBearings(legs) {
  const bar = MojitoLegs.bearingBar(legs, currentLegIndex, boatPos);
  for (const id of Object.keys(bar)) setText(id, bar[id]);
}


function sideAbbrev(courseBearing,twd){
  const s=side(courseBearing,twd);
  if(s==="Port")return"P";
  if(s==="Starboard")return"S";
  return"—";
}
function twaClass(courseBearing,twd){
  const s=side(courseBearing,twd);
  if(s==="Port")return"port";
  if(s==="Starboard")return"starboard";
  return"";
}
function currentRouteKey(index, fromId, toId){return `${index}:${fromId}-${toId}`;}

function getLeg(from,to){
  const bd=bearingAndDistance(from,to);
  const twa=angleDiff(bd.bearing,twd);
  return {from,to,...bd,twa};
}
async function loadCurrentLeg(){
  try {
    const data = await fetchJson("/api/current_leg");
    currentLegIndex = Math.max(0, Number(data.current_leg || 0));
  } catch(e) {}
}

async function saveCurrentLeg(){
  try {
    await fetch("/api/current_leg", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({current_leg: currentLegIndex})
    });
  } catch(e) {}
}


function moveCurrentLeg(delta){
  const legs = routeLegs();
  if (!legs.length) return;
  currentLegIndex = Math.max(0, Math.min(legs.length - 1, currentLegIndex + delta));
  saveCurrentLeg();
  render();
}

function updatePhoneLegStatus(legs){
  const status = document.getElementById("phoneLegStatus");
  if (!status) return;
  if (!legs.length) {
    status.textContent = "Leg —";
    return;
  }
  currentLegIndex = Math.max(0, Math.min(legs.length - 1, currentLegIndex));
  const leg = legs[currentLegIndex];
  status.textContent = `${currentLegIndex + 1}/${legs.length} ${leg.from.id}→${leg.to.id}`;
}

function routeLegs(){
  const route=parseCourse(courseText);
  const legs=[];
  for(let i=0;i<route.length-1;i++) legs.push(getLeg(markById[route[i]], markById[route[i+1]]));
  return legs;
}

function formatTargetBsp(info){
  if(!info)return"—";
  if(info.mode==="upwind"||info.mode==="downwind")return`${info.bsp.toFixed(1)}@${info.polarTwa.toFixed(0)}°`;
  return`${info.bsp.toFixed(1)}`;
}
function formatLegTime(distanceNm,speedKt){
  if(!speedKt||speedKt<=0)return"—";
  const totalMinutes=distanceNm/speedKt*60;
  if(totalMinutes<60)return`${totalMinutes.toFixed(1)}m`;
  const h=Math.floor(totalMinutes/60);
  const m=Math.round(totalMinutes%60);
  return`${h}h${String(m).padStart(2,"0")}`;
}

function roundingBadge(value){
  if(value==="P")return`<span class="roundBadge roundP">P</span>`;
  if(value==="S")return`<span class="roundBadge roundS">S</span>`;
  if(value==="V")return`<span class="roundBadge roundNone">Via</span>`;
  if(value==="F")return`<span class="roundBadge roundNone">Fin</span>`;
  return`<span class="roundBadge roundNone">—</span>`;
}

function unwrapTwd(samples) {
  if (!samples.length) return [];
  const out = [];
  let prev = samples[0].twd;
  let offset = 0;
  out.push({...samples[0], twdPlot: prev});

  for (let i = 1; i < samples.length; i++) {
    let v = samples[i].twd + offset;
    while (v - prev > 180) { offset -= 360; v = samples[i].twd + offset; }
    while (v - prev < -180) { offset += 360; v = samples[i].twd + offset; }
    out.push({...samples[i], twdPlot: v});
    prev = v;
  }
  return out;
}

function drawWindHistory(samples, serverNow = null, minutesOverride = null) {
  const canvas = document.getElementById("windHistoryCanvas");
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, Math.floor(rect.width * dpr));
  canvas.height = Math.max(320, Math.floor(rect.height * dpr));

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const w = canvas.width / dpr;
  const h = canvas.height / dpr;

  const bg = "#020617";
  const grid = "#334155";
  const gridSoft = "#1e293b";
  const text = "#f8fafc";
  const muted = "#cbd5e1";
  const twdLine = "#f8fafc";
  const twsLine = "#93c5fd";
  const twdCurrent = "#ef4444";
  const twsCurrent = "#22c55e";

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  const top = 34, bottom = 28, left = 34, mid = w / 2, right = w - 16;
  const plotH = h - top - bottom;

  const mins = Number(minutesOverride || document.getElementById("historyMinutes")?.value || 5);
  const now = Number(serverNow || Date.now() / 1000);
  const t0 = now - mins * 60;
  const t1 = now;

  ctx.strokeStyle = gridSoft;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = top + (plotH * i / 5);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }
  for (let i = 0; i <= 4; i++) {
    const x1 = left + (mid - left) * i / 4;
    const x2 = mid + (right - mid) * i / 4;
    ctx.strokeStyle = i === 0 || i === 4 ? grid : gridSoft;
    ctx.beginPath(); ctx.moveTo(x1, top); ctx.lineTo(x1, h-bottom); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, top); ctx.lineTo(x2, h-bottom); ctx.stroke();
  }

  ctx.strokeStyle = grid;
  ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.moveTo(mid, top); ctx.lineTo(mid, h-bottom); ctx.stroke();

  ctx.fillStyle = text;
  ctx.font = "14px system-ui";
  ctx.textAlign = "center";
  ctx.fillText("TWD", mid / 2, 18);
  ctx.fillText("TWS", mid + (right - mid) / 2, 18);

  ctx.fillStyle = muted;
  ctx.font = "11px system-ui";
  ctx.textAlign = "left";
  ctx.fillText("now", 4, top + 12);
  ctx.fillText(`-${mins}m`, 4, h - bottom - 4);

  const visibleSamples = samples
    .filter(s => typeof s.t === "number" && s.t >= t0 && s.t <= t1)
    .sort((a, b) => a.t - b.t);

  if (!visibleSamples.length) {
    ctx.fillStyle = muted;
    ctx.textAlign = "center";
    ctx.font = "13px system-ui";
    ctx.fillText("Waiting for wind history…", w / 2, h / 2);
    ctx.font = "11px system-ui";
    ctx.fillText(`${mins} minute rolling window`, w / 2, h - 8);
    return;
  }

  const unwrapped = unwrapTwd(visibleSamples);
  const twdValues = unwrapped.map(s => s.twdPlot);
  const twsValues = visibleSamples.map(s => s.tws);

  const twdLatest = twdValues[twdValues.length - 1];
  const twsLatest = twsValues[twsValues.length - 1];

  const twdPad = 10;
  const twsPad = 1.5;
  const twdMin = Math.floor((Math.min(...twdValues, twdLatest - twdPad)) / 10) * 10;
  const twdMax = Math.ceil((Math.max(...twdValues, twdLatest + twdPad)) / 10) * 10;
  const twsMin = Math.max(0, Math.floor(Math.min(...twsValues, twsLatest - twsPad)));
  const twsMax = Math.max(twsMin + 1, Math.ceil(Math.max(...twsValues, twsLatest + twsPad)));

  ctx.font = "12px system-ui";
  ctx.fillStyle = muted;
  ctx.textAlign = "left";
  ctx.fillText(`${norm360(twdMin).toFixed(0)}`, 2, 30);
  ctx.textAlign = "center";
  ctx.fillStyle = text;
  ctx.fillText(`${norm360(twdLatest).toFixed(1)}`, mid / 2, 30);
  ctx.fillStyle = muted;
  ctx.textAlign = "right";
  ctx.fillText(`${norm360(twdMax).toFixed(0)}`, mid - 4, 30);

  ctx.textAlign = "left";
  ctx.fillText(`${twsMin.toFixed(0)}`, mid + 4, 30);
  ctx.textAlign = "center";
  ctx.fillStyle = text;
  ctx.fillText(`${twsLatest.toFixed(1)}`, mid + (right - mid) / 2, 30);
  ctx.fillStyle = muted;
  ctx.textAlign = "right";
  ctx.fillText(`${twsMax.toFixed(0)}`, w - 2, 30);

  // Current time is at the top; older history runs down the plot.
  const yForTime = t => top + ((t1 - t) / (t1 - t0 || 1)) * plotH;
  const xTwd = v => left + ((v - twdMin) / (twdMax - twdMin || 1)) * (mid - left);
  const xTws = v => mid + ((v - twsMin) / (twsMax - twsMin || 1)) * (right - mid);

  function drawLine(items, xFn, valKey, strokeStyle) {
    if (!items.length) return;
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < items.length; i++) {
      const x = xFn(items[i][valKey]);
      const y = yForTime(items[i].t);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  drawLine(unwrapped, xTwd, "twdPlot", twdLine);
  drawLine(visibleSamples, xTws, "tws", twsLine);

  ctx.strokeStyle = twdCurrent;
  ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(xTwd(twdLatest), top); ctx.lineTo(xTwd(twdLatest), h-bottom); ctx.stroke();

  ctx.strokeStyle = twsCurrent;
  ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(xTws(twsLatest), top); ctx.lineTo(xTws(twsLatest), h-bottom); ctx.stroke();

  ctx.fillStyle = muted;
  ctx.font = "11px system-ui";
  ctx.textAlign = "left";
  ctx.fillText("now", 4, h - 8);
  ctx.textAlign = "center";
  ctx.fillText(`history down: ${mins}m`, w / 2, h - 8);
  ctx.textAlign = "right";
  ctx.fillText(`-${mins}m`, w - 4, h - 8);
}
async function loadWindHistory() {
  const mins = document.getElementById("historyMinutes")?.value || "5";
  try {
    const data = await fetchJson(`/api/wind_history?minutes=${encodeURIComponent(mins)}`);
    if (data.current) {
      if (typeof data.current.twd === "number") twd = norm360(data.current.twd);
      if (typeof data.current.tws === "number") tws = Math.max(0, data.current.tws);
    }
    drawWindHistory(data.samples || [], data.server_now, data.minutes);
  } catch(e) {
    // Leave plot unchanged if history is temporarily unavailable.
  }
}

async function fetchJson(url) {
  const r = await fetch(url, {cache:"no-store"});
  const data = await r.json();
  if(!r.ok || data.ok === false) throw new Error(data.error || `Could not load ${url}`);
  return data;
}

async function loadAll(){
  try {
    const [marksResp, courseResp, sailResp, polarResp] = await Promise.all([
      fetchJson("/api/marks"),
      fetchJson("/api/course"),
      fetchJson("/api/sailchart"),
      fetchJson("/api/polar")
    ]);

    marks = normaliseMarks(marksResp.marks || []);
    markById = Object.fromEntries(marks.map(m => [m.id, m]));
    courseText = courseResp.course || "";
    courseRoundings = courseResp.roundings || {};
    sailChart = {twas:sailResp.twas || [], rows:sailResp.rows || []};
    polarData = {rows:polarResp.rows || []};

    await loadCurrentLeg();
    await loadWind();
    render();
  } catch(e) {
    showError(e.message);
  }
}

// The wind used for the legs comes from /api/wind (the instruments, or the
// manual wind when the instrument source is Manual wind). The history plot is
// the sampled wind.
async function loadWind(){
  try {
    const r = await fetch("/api/wind", {cache:"no-store"});
    const w = await r.json();
    windManual = !!w.manual;
    if (typeof w.twd === "number") twd = norm360(w.twd);
    if (typeof w.tws === "number") tws = Math.max(0, w.tws);
  } catch(e) {
    // Keep the previous wind if it is temporarily unavailable.
  }
  try {
    const mins = document.getElementById("historyMinutes")?.value || "5";
    const hist = await fetchJson(`/api/wind_history?minutes=${encodeURIComponent(mins)}`);
    drawWindHistory(hist.samples || [], hist.server_now, hist.minutes);
  } catch(e) {
    // Leave the plot unchanged if history is temporarily unavailable.
  }
}

function showError(msg){
  const el=document.getElementById("error");
  el.style.display="block";
  el.textContent=msg;
}

async function loadPosition(){
  try {
    const pos = await fetchJson("/api/position");
    boatPos = {latDec: pos.lat, lonDec: pos.lon};
  } catch(e) {
    boatPos = null;   // no GPS fix, or Expedition unavailable
  }
}

function setText(id, text){
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// Same as the MFD bar. Middle: boat to the mark at the end of the current leg.
// Right: the leg after it, i.e. the course once that mark is rounded.

function render(){
  document.getElementById("meta").innerHTML = `TWD ${twd.toFixed(0)}°  TWS ${tws.toFixed(1)} kt` +
    (windManual ? ' <span class="manualWind">MANUAL</span>' : "");
  const tbody=document.getElementById("legs");
  const legs=routeLegs();
  updatePhoneLegStatus(legs);   // also clamps currentLegIndex to the course
  renderBearings(legs);
  tbody.innerHTML="";
  if(!legs.length){
    tbody.innerHTML=`<tr><td colspan="8">No course set</td></tr>`;
    return;
  }
  for(let i=0;i<legs.length;i++){
    const leg=legs[i];
    const key=currentRouteKey(i, leg.from.id, leg.to.id);
    const rounding=courseRoundings[key] || "";
    const info=targetSpeedInfoFor(leg.twa,tws);
    const sp=info?info.cmg:null;
    const tr=document.createElement("tr");
    if (i === currentLegIndex) tr.className = "currentLegRow";
    const twaSide=sideAbbrev(leg.bearing,twd);
    tr.innerHTML=`
      <td>${leg.from.id}→${leg.to.id}</td>
      <td>${roundingBadge(rounding)}</td>
      <td>${leg.distanceNm.toFixed(2)}</td>
      <td>${leg.bearing.toFixed(0)}°</td>
      <td class="${twaClass(leg.bearing,twd)}">${leg.twa.toFixed(0)}° ${twaSide}</td>
      <td>${sailFor(leg.twa,tws)}</td>
      <td>${formatTargetBsp(info)}</td>
      <td>${formatLegTime(leg.distanceNm,sp)}</td>
    `;
    tbody.appendChild(tr);
  }
}

loadAll();
setInterval(async () => { await loadCurrentLeg(); await loadWind(); await loadPosition(); render(); }, 1000);
setInterval(loadAll, 10000);
window.addEventListener("resize", loadWindHistory);

// Start bar, sharing the bar with the bearings (static/race_start.js).
MojitoRaceStart.attach("raceStartBar", {theme: "dark", frame: "phoneBar"});
