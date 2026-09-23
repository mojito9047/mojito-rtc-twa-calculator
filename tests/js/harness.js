// Runs a page's inline <script> blocks in Node with a stub browser, then
// evaluates an expression and prints its value as JSON.
//
// Input on stdin: {"page": path|null, "scripts": [paths], "setup": js, "expr": js}
// The stub browser is just enough for the page scripts to load: no network
// (fetch never resolves, XHR never answers) and no timers (setInterval and
// setTimeout do nothing), so page start-up code cannot change the test state.
// Top-level `let`/`const` declarations stay visible to `setup` and `expr`
// because everything runs in one vm context.
"use strict";
const fs = require("fs");
const vm = require("vm");

const request = JSON.parse(fs.readFileSync(0, "utf8"));

function makeElement(id) {
  const el = {
    id: id || "",
    innerHTML: "",
    textContent: "",
    innerText: "",
    value: "",
    checked: false,
    disabled: false,
    className: "",
    style: {},
    children: [],
    offsetWidth: 0,   // pages treat 0 as "hidden" (the Course chart skips drawing)
    offsetHeight: 0,
    clientWidth: 0,
    clientHeight: 0,
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      toggle(c, on) { if (on === undefined ? !this._set.has(c) : on) this._set.add(c); else this._set.delete(c); },
      contains(c) { return this._set.has(c); },
    },
    addEventListener() {},
    removeEventListener() {},
    appendChild(child) { this.children.push(child); return child; },
    removeChild() {},
    setAttribute() {},
    getAttribute() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getContext() { return new Proxy({}, { get: () => () => {} }); },
    focus() {},
    click() {},
  };
  return el;
}

const elements = {};
const document = {
  getElementById(id) { return elements[id] || (elements[id] = makeElement(id)); },
  createElement(tag) { return makeElement(""); },
  createTextNode(text) { return { text }; },
  getElementsByTagName() { return [makeElement("head")]; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  body: makeElement("body"),
  head: makeElement("head"),
};

class XMLHttpRequest {
  open() {}
  send() {}
  setRequestHeader() {}
}

const context = {
  document,
  XMLHttpRequest,
  console,
  JSON, Math, Date, Number, String, Array, Object, Promise, Set, Map, RegExp, Error, isFinite, isNaN, parseFloat, parseInt,
  fetch: () => new Promise(() => {}),
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout: () => 0,
  clearTimeout: () => {},
  requestAnimationFrame: () => 0,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: { userAgent: "node-test" },
  location: { href: "http://localhost:8765/", reload() {} },
  alert() {},
  addEventListener() {},
  open() {},
  devicePixelRatio: 1,
  __elements: elements,
};
context.window = context;
vm.createContext(context);

// The page's scripts in document order: inline code, and the app's own
// /static/ files (loaded from disk). Leaflet (/static/leaflet/) needs a real
// browser, so it is skipped: pages then take the no-Leaflet path, and a test
// can supply a stand-in `window.L`. External scripts are skipped too.
function pageScripts(pagePath) {
  const path = require("path");
  const appRoot = path.resolve(path.dirname(pagePath), "..");
  const html = fs.readFileSync(pagePath, "utf8");
  const out = [];
  const re = /<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi;
  let m, n = 0;
  while ((m = re.exec(html))) {
    const src = /\ssrc\s*=\s*["']([^"']+)["']/.exec(m[1] || "");
    n += 1;
    if (!src) out.push({ name: `${pagePath}#script${n}`, code: m[2] });
    else if (src[1].startsWith("/static/") && !src[1].startsWith("/static/leaflet/")) {
      const file = path.join(appRoot, src[1].replace(/\?.*$/, ""));
      out.push({ name: file, code: fs.readFileSync(file, "utf8") });
    }
  }
  return out;
}

try {
  if (request.page) {
    for (const s of pageScripts(request.page)) vm.runInContext(s.code, context, { filename: s.name });
  }
  for (const file of request.scripts || []) {
    vm.runInContext(fs.readFileSync(file, "utf8"), context, { filename: file });
  }
  if (request.setup) vm.runInContext(request.setup, context, { filename: "setup" });
  const value = vm.runInContext(`JSON.stringify((${request.expr}))`, context, { filename: "expr" });
  process.stdout.write(value === undefined ? "null" : value);
} catch (e) {
  process.stderr.write((e && e.stack) || String(e));
  process.exit(1);
}
