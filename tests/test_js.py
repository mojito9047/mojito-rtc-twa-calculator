"""Page JavaScript, run in Node (skipped when Node is not installed).

The leg calculations are copied into index.html, phone.html and mfd.html, and
the copies have drifted before (v57). These tests run each page's own script
and check the three agree, and agree with independent reference values.
"""

import json
import re
import unittest

import app
from tests.helpers import ROOT, FakeRaceOfficer, requires_node, run_js

PAGES = {
    # page: name of its target-speed function
    "index.html": "targetSpeedInfoFor",
    "phone.html": "targetSpeedInfoFor",
    "mfd.html": "targetSpeedInfo",
}


def data_setup():
    """JavaScript that loads the real sail chart and polar into a page's globals."""
    client = app.app.test_client()
    sail = client.get("/api/sailchart").get_json()
    polar = client.get("/api/polar").get_json()
    return ("sailChart = {twas: %s, rows: %s}; polarData = {rows: %s};"
            "try { polarLoaded = true; sailChartLoaded = true; } catch (e) {}"
            % (json.dumps(sail["twas"]), json.dumps(sail["rows"]), json.dumps(polar["rows"])))


@requires_node
class CalculationAgreementTests(unittest.TestCase):
    """Sail choice, target speed and tack must be identical on every page."""

    TWAS = list(range(0, 181, 5)) + [37, 41, 44, 152, 163, 178]
    TWSS = [3, 4, 6, 7.5, 10, 12, 14, 16, 20, 25, 30]

    @classmethod
    def setUpClass(cls):
        setup = data_setup()
        cls.results = {}
        grid = json.dumps([[a, s] for a in cls.TWAS for s in cls.TWSS])
        for page, fn in PAGES.items():
            cls.results[page] = run_js(page=page, setup=setup, expr=f"""
              {grid}.map(function (p) {{
                var info = {fn}(p[0], p[1]);
                return {{twa: p[0], tws: p[1], sail: sailFor(p[0], p[1]),
                         bsp: info && info.bsp, cmg: info && info.cmg,
                         polarTwa: info && info.polarTwa, mode: info && info.mode}};
              }})""")

    def test_sail_choice_agrees(self):
        base = self.results["index.html"]
        for page in ("phone.html", "mfd.html"):
            for a, b in zip(base, self.results[page]):
                self.assertEqual(a["sail"], b["sail"], f"{page} TWA {a['twa']} TWS {a['tws']}")

    def test_target_speed_agrees(self):
        base = self.results["index.html"]
        for page in ("phone.html", "mfd.html"):
            for a, b in zip(base, self.results[page]):
                where = f"{page} TWA {a['twa']} TWS {a['tws']}"
                self.assertEqual(a["mode"], b["mode"], where)
                for key in ("bsp", "cmg", "polarTwa"):
                    if a[key] is None:
                        self.assertIsNone(b[key], where)
                    else:
                        self.assertAlmostEqual(a[key], b[key], places=6, msg=f"{where} {key}")

    def test_polar_points_reproduced_exactly(self):
        # A TWA/TWS that is a point in J122.txt gives that point's speed.
        client = app.app.test_client()
        rows = client.get("/api/polar").get_json()["rows"]
        row = next(r for r in rows if r["tws"] == 12.0)
        point = next(p for p in row["points"] if p["twa"] == 90.0)
        got = next(r for r in self.results["mfd.html"] if r["twa"] == 90 and r["tws"] == 12)
        self.assertAlmostEqual(got["bsp"], point["bsp"], places=6)

    def test_upwind_and_downwind_use_vmg(self):
        for page, rows in self.results.items():
            close = next(r for r in rows if r["twa"] == 20 and r["tws"] == 12)
            run = next(r for r in rows if r["twa"] == 180 and r["tws"] == 12)
            self.assertEqual(close["mode"], "upwind", page)
            self.assertEqual(run["mode"], "downwind", page)
            self.assertLess(close["cmg"], close["bsp"], page)


@requires_node
class GeometryTests(unittest.TestCase):
    """Bearings and distances against the Race Officer app's own leg figures."""

    @classmethod
    def setUpClass(cls):
        payload = FakeRaceOfficer().make()
        cls.legs = payload["course"]["legs"]
        points = {m["code"]: {"latDec": m["lat"], "lonDec": m["lon"]}
                  for m in payload["course"]["expanded_marks"]}
        cls.pairs = [[points[l["from_mark"]], points[l["to_mark"]]] for l in cls.legs]

    def test_leg_bearing_and_distance_match_race_officer(self):
        for page in PAGES:
            got = run_js(page=page, expr="%s.map(function (p) { return bearingAndDistance(p[0], p[1]); })"
                         % json.dumps(self.pairs))
            for leg, bd in zip(self.legs, got):
                where = f"{page} {leg['from']}->{leg['to']}"
                self.assertAlmostEqual(bd["bearing"], leg["bearing_deg"], delta=0.1, msg=where)
                self.assertAlmostEqual(bd["distanceNm"], leg["distance_nm"], delta=0.002, msg=where)

    def test_tack_side_agrees(self):
        cases = [[0, 90], [90, 0], [200, 350], [350, 10], [45, 45], [10, 190]]
        answers = {}
        for page in PAGES:
            got = run_js(page=page, expr="%s.map(function (c) { return side(c[0], c[1]); })" % json.dumps(cases))
            answers[page] = [(s or "-")[0] for s in got]      # "Starboard"/"S" -> "S", "—"/"" -> "-"/"—"
        self.assertEqual(answers["index.html"][:4], ["S", "P", "S", "S"])
        self.assertEqual(answers["index.html"], answers["phone.html"])
        for i, (a, b) in enumerate(zip(answers["index.html"], answers["mfd.html"])):
            if a in "SP":
                self.assertEqual(a, b, f"case {cases[i]}")

    def test_position_formats(self):
        # Formats from the README and the Race Officer app.
        cases = [["52.8783333333", 52.8783333333], ["-4.405", -4.405],
                 ["52° 52.700'N", 52.8783333333], ["04° 24.300'W", -4.405],
                 ["50° 39.33N", 50.6555], ["01° 55.17W", -1.9195]]
        for page in PAGES:
            got = run_js(page=page, expr="%s.map(function (c) { return parsePosition(c[0], /W|E/.test(c[0])); })"
                         % json.dumps(cases))
            for (text, want), value in zip(cases, got):
                self.assertAlmostEqual(value, want, places=4, msg=f"{page} {text!r}")


@requires_node
class RaceStartBarTests(unittest.TestCase):
    """static/race_start.js: what the start bar shows for each race state."""

    RACE = {"race_name": "Race 5", "course_set": True, "course_no": 1, "course_label": "N",
            "postponed": False, "postponement_flag": "", "race_finished": False,
            "shortened": False, "shortened_label": ""}

    def bar(self, info, frame=False):
        setup = """
          XMLHttpRequest = function () {};
          XMLHttpRequest.prototype.open = function () {};
          XMLHttpRequest.prototype.send = function () {
            this.readyState = 4; this.status = 200; this.responseText = %s;
            this.onreadystatechange();
          };
          document.getElementById("frame").className = "mfdBar";
          MojitoRaceStart.attach("bar", %s);
        """ % (json.dumps(json.dumps(info)),
               json.dumps({"theme": "dark", "frame": "frame"} if frame else {"theme": "light"}))
        return run_js(scripts=["static/race_start.js"], setup=setup, expr="""{
            html: __elements.bar.innerHTML, cls: __elements.bar.className,
            display: __elements.bar.style.display || "", frameCls: __elements.frame.className}""")

    def info(self, **race):
        data = {"ok": True, "live": True, "seconds_to_start": None, "start_clock": "",
                "postponement_ends_clock": "", "race": dict(self.RACE)}
        data["race"].update({k: v for k, v in race.items() if k in self.RACE})
        data.update({k: v for k, v in race.items() if k not in self.RACE})
        return data

    def test_countdown(self):
        out = self.bar(self.info(seconds_to_start=245, start_clock="14:05:00"))
        self.assertIn("Start in 4:0", out["html"])
        self.assertIn("First start 14:05:00", out["html"])
        self.assertIn("Race 5 · Course 1 N", out["html"])
        self.assertEqual(out["display"], "block")

    def test_last_minute_is_urgent(self):
        out = self.bar(self.info(seconds_to_start=42, start_clock="14:05:00"))
        self.assertIn("rsb-urgent", out["cls"])

    def test_long_countdown_shows_hours(self):
        out = self.bar(self.info(seconds_to_start=3725, start_clock="15:05:00"))
        self.assertIn("Start in 1:02:0", out["html"])

    def test_racing(self):
        out = self.bar(self.info(seconds_to_start=-754, start_clock="13:52:00"))
        self.assertIn("Racing +12:3", out["html"])
        self.assertIn("rsb-racing", out["cls"])

    def test_postponed(self):
        out = self.bar(self.info(postponed=True, postponement_flag="AP over H",
                                 seconds_to_start=300, postponement_ends_clock="14:30"))
        self.assertIn("AP over H — start postponed", out["html"])
        self.assertIn("AP down at 14:30", out["html"])
        self.assertNotIn("Start in", out["html"])

    def test_no_start_time(self):
        self.assertIn("No start time set", self.bar(self.info())["html"])

    def test_course_not_set(self):
        out = self.bar(self.info(course_set=False))
        self.assertIn("Course not set yet", out["html"])
        self.assertNotIn("Course 1", out["html"])

    def test_shortened(self):
        out = self.bar(self.info(shortened=True, shortened_label="4 (rounding 1)", seconds_to_start=-60))
        self.assertIn("Course shortened at 4 (rounding 1)", out["html"])

    def test_finished(self):
        self.assertIn("Race finished", self.bar(self.info(race_finished=True))["html"])

    def test_html_is_escaped(self):
        out = self.bar(self.info(race_name="<b>x</b>"))
        self.assertIn("&lt;b&gt;", out["html"])

    def test_hidden_when_not_live(self):
        out = self.bar(self.info(live=False))
        self.assertEqual(out["display"], "none")

    def test_frame_mode_colours_frame_and_stays_visible(self):
        out = self.bar(self.info(seconds_to_start=-10, start_clock="13:52:00"), frame=True)
        self.assertIn("mfdBar", out["frameCls"])
        self.assertIn("rsb-racing", out["frameCls"])
        self.assertNotEqual(out["display"], "none")
        empty = self.bar(self.info(live=False), frame=True)
        self.assertEqual(empty["html"], "")
        self.assertIn("mfdBar", empty["frameCls"])


@requires_node
class BearingBarTests(unittest.TestCase):
    """MFD and phone bars: bearing from the boat to the next mark, and the next leg."""

    # page: (current leg variable, function returning the legs, text property)
    BAR_PAGES = {
        "mfd.html": ("currentLeg", "getLegs", "innerHTML"),
        "phone.html": ("currentLegIndex", "routeLegs", "textContent"),
    }
    MARKS = """
      marks = normaliseMarks([
        {id: "O", name: "O", lat: "52.8791166667", lon: "-4.3993333333"},
        {id: "1", name: "1", lat: "52.8783333333", lon: "-4.405"},
        {id: "8", name: "8", lat: "52.8666666667", lon: "-4.4116666667"}]);
      markById = {}; for (var i = 0; i < marks.length; i++) markById[marks[i].id] = marks[i];
    """
    CELLS = ["toMarkLabel", "toMarkBearing", "toMarkRange", "nextLegLabel", "nextLegBearing", "nextLegRange"]

    def bearings(self, page, leg, boat, course="O 1 8"):
        leg_var, legs_fn, prop = self.BAR_PAGES[page]
        setup = self.MARKS + 'courseText = "%s"; %s = %d; boatPos = %s; renderBearings(%s());' % (
            course, leg_var, leg, boat, legs_fn)
        expr = "{" + ", ".join("%s: __elements.%s.%s" % (c, c, prop) for c in self.CELLS) + "}"
        return run_js(page=page, setup=setup, expr=expr)

    def test_boat_at_start_mark(self):
        for page in self.BAR_PAGES:
            out = self.bearings(page, 0, "{latDec: 52.8791166667, lonDec: -4.3993333333}")
            self.assertEqual(out["toMarkLabel"], "To 1", page)
            self.assertEqual(out["toMarkBearing"], "257°", page)     # same as leg O->1
            self.assertEqual(out["toMarkRange"], "0.21 nm", page)
            self.assertEqual(out["nextLegLabel"], "Next leg 1→8", page)
            self.assertEqual(out["nextLegBearing"], "199°", page)

    def test_last_leg(self):
        for page in self.BAR_PAGES:
            out = self.bearings(page, 1, "{latDec: 52.8783333333, lonDec: -4.405}")
            self.assertEqual(out["toMarkLabel"], "To 8", page)
            self.assertEqual(out["nextLegBearing"], "—", page)
            self.assertEqual(out["nextLegRange"], "Last leg", page)

    def test_no_gps(self):
        for page in self.BAR_PAGES:
            out = self.bearings(page, 0, "null")
            self.assertEqual(out["toMarkBearing"], "—", page)
            self.assertEqual(out["toMarkRange"], "No GPS position", page)
            self.assertEqual(out["nextLegBearing"], "199°", page)    # next leg does not need GPS

    def test_no_course(self):
        for page in self.BAR_PAGES:
            out = self.bearings(page, 0, "null", course="")
            self.assertEqual(out["toMarkBearing"], "—", page)
            self.assertEqual(out["nextLegBearing"], "—", page)

    def test_pages_agree(self):
        boat = "{latDec: 52.872, lonDec: -4.402}"
        results = [self.bearings(page, 0, boat) for page in self.BAR_PAGES]
        self.assertEqual(results[0], results[1])


@requires_node
class WindStripTests(unittest.TestCase):
    """Course legs page: the wind strip for instruments and for manual wind."""

    def strip(self, mode):
        return run_js(page="index.html", setup='setWindMode("%s");' % mode, expr="""{
            label: __elements.windMode.textContent, help_hidden: __elements.windModeHelp.hidden,
            twd_disabled: __elements.twd.disabled, tws_disabled: __elements.tws.disabled}""")

    def test_instruments(self):
        self.assertEqual(self.strip("instruments"),
                         {"label": "Wind: Instruments", "help_hidden": True, "twd_disabled": True, "tws_disabled": True})

    def test_manual(self):
        self.assertEqual(self.strip("manual"),
                         {"label": "Wind: Manual", "help_hidden": False, "twd_disabled": False, "tws_disabled": False})


class LegacyBrowserTests(unittest.TestCase):
    """The MFD's embedded browser is old: its page and race_start.js must be ES5."""

    FORBIDDEN = [
        (r"=>", "arrow function"),
        (r"\blet\s", "let"),
        (r"\bconst\s", "const"),
        (r"`", "template literal"),
        (r"\basync\s", "async"),
        (r"\bawait\s", "await"),
        (r"\bclass\s+\w", "class"),
        (r"\.\.\.\w", "spread"),
        (r"\bfetch\(", "fetch (use XMLHttpRequest)"),
        (r"\?\.", "optional chaining"),
        (r"\?\?", "nullish coalescing"),
        (r"\.padStart\(|\.includes\(|\.startsWith\(|\.endsWith\(", "ES2015+ string method"),
        (r"Object\.entries|Object\.values|Object\.fromEntries|Array\.from|\.find\(|\.findIndex\(", "ES2015+ built-in"),
    ]

    @staticmethod
    def code_only(js):
        """Blank out comments and string literals so only code is checked."""
        out, i, n = [], 0, len(js)
        while i < n:
            c = js[i]
            if js.startswith("//", i):
                j = js.find("\n", i)
                i = n if j < 0 else j
            elif js.startswith("/*", i):
                j = js.find("*/", i + 2)
                i = n if j < 0 else j + 2
            elif c in "'\"":
                j = i + 1
                while j < n and js[j] != c:
                    j += 2 if js[j] == "\\" else 1
                out.append('""')
                i = j + 1
            else:
                out.append(c)
                i += 1
        return "".join(out)

    def check(self, name, js):
        code = self.code_only(js)
        for pattern, what in self.FORBIDDEN:
            m = re.search(pattern, code)
            if m:
                line = code[:m.start()].count("\n") + 1
                self.fail(f"{name}: {what} at line {line} is not supported by older MFD browsers")

    def test_mfd_page_scripts(self):
        html = (ROOT / "templates" / "mfd.html").read_text(encoding="utf-8")
        for i, block in enumerate(re.findall(r"<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)</script>", html)):
            self.check(f"mfd.html script {i + 1}", block)

    def test_scripts_loaded_by_mfd_page(self):
        html = (ROOT / "templates" / "mfd.html").read_text(encoding="utf-8")
        srcs = re.findall(r'<script[^>]*\ssrc="(/static/[^"]+)"', html)
        self.assertIn("/static/legs.js", srcs)
        self.assertIn("/static/race_start.js", srcs)
        for src in srcs:
            self.check(src, (ROOT / src.lstrip("/")).read_text(encoding="utf-8"))

    def test_checker_catches_modern_syntax(self):
        with self.assertRaises(AssertionError):
            self.check("sample", "var f = (x) => x;")
        with self.assertRaises(AssertionError):
            self.check("sample", "let a = 1;")
        self.check("sample", "var s = 'a => b, let x, `tick`'; // const y => z")


@requires_node
class SharedLegsTests(unittest.TestCase):
    """static/legs.js directly: the one copy of the leg calculations."""

    def legs(self, expr, setup=""):
        return run_js(scripts=["static/legs.js"], setup=setup, expr=expr)

    @staticmethod
    def page_scripts(page):
        """(name, code) of a page's scripts in load order: inline blocks and /static/ files."""
        html = (ROOT / "templates" / page).read_text(encoding="utf-8")
        out = []
        for attrs, body in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html):
            src = re.search(r'\ssrc="([^"]+)"', attrs)
            if not src:
                out.append((f"{page} inline", body))
            elif src.group(1).startswith("/static/"):
                out.append((src.group(1), (ROOT / src.group(1).lstrip("/")).read_text(encoding="utf-8")))
        return out

    def test_every_page_uses_shared_script(self):
        for page in PAGES:
            scripts = self.page_scripts(page)
            names = [n for n, _ in scripts]
            self.assertIn("/static/legs.js", names, page)
            # ...loaded before any script that uses it.
            first_use = next(i for i, (n, code) in enumerate(scripts) if n != "/static/legs.js" and "MojitoLegs." in code)
            self.assertLess(names.index("/static/legs.js"), first_use, page)
            for name, code in scripts:
                if name == "/static/legs.js":
                    continue
                for fn in ("function rowBestDownwindVmg", "function interpolateRowsByTws", "function polarUsablePoints"):
                    self.assertNotIn(fn, code, f"{name} has its own copy of {fn}")

    def test_main_and_phone_pages_have_no_inline_code(self):
        # The MFD page keeps its code inline on purpose (one file for its old browser).
        for page, script in (("index.html", "/static/index.js"), ("phone.html", "/static/phone.js")):
            html = (ROOT / "templates" / page).read_text(encoding="utf-8")
            self.assertNotIn("<style", html, page)
            self.assertEqual([n for n, _ in self.page_scripts(page)],
                             ["/static/legs.js", "/static/race_start.js", script], page)

    def test_format_position(self):
        out = self.legs("""[MojitoLegs.formatPosition(50.6555, false), MojitoLegs.formatPosition(-1.9195, true),
            MojitoLegs.formatPosition(52.8783333333, false), MojitoLegs.formatPosition(-4.405, true),
            MojitoLegs.formatPosition(-33.8683, false), MojitoLegs.formatPosition(151.21, true),
            MojitoLegs.formatPosition(52.9999999, false), MojitoLegs.formatPosition(0.001, true),
            MojitoLegs.formatPosition(NaN, false), MojitoLegs.formatPosition(52.5, false, 2)]""")
        self.assertEqual(out, ["50 39.330N", "01 55.170W", "52 52.700N", "04 24.300W",
                               "33 52.098S", "151 12.600E", "53 00.000N", "00 00.060E", "", "52 30.00N"])

    def test_formatted_positions_read_back_to_within_a_metre(self):
        # The editor shows formatted positions and saves what it shows.
        out = self.legs("""(function () {
            var worst = 0, v, back;
            for (v = -89.9; v < 90; v += 0.3719) {
              back = MojitoLegs.parsePosition(MojitoLegs.formatPosition(v, false));
              worst = Math.max(worst, Math.abs(back - v));
              back = MojitoLegs.parsePosition(MojitoLegs.formatPosition(v * 2, true));
              worst = Math.max(worst, Math.abs(back - v * 2));
            }
            return worst;
          })()""")
        self.assertLess(out * 60 * 1852, 1.0)            # under a metre

    def test_parse_course_keeps_known_marks_in_order(self):
        out = self.legs('MojitoLegs.parseCourse("o 1-8 x 1, O", {O: 1, "1": 1, "8": 1})')
        self.assertEqual(out, ["O", "1", "8", "1", "O"])

    def test_normalise_marks(self):
        out = self.legs("""MojitoLegs.normaliseMarks([
            {id: " o ", lat: "52° 52.747'N", lon: "04° 23.960'W", extra: 1},
            {id: "", lat: "1", lon: "1"}, {id: "X", lat: "?", lon: "1"}])""")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "O")
        self.assertEqual(out[0]["extra"], 1)
        self.assertAlmostEqual(out[0]["latDec"], 52.8791166667, places=6)
        self.assertAlmostEqual(out[0]["lonDec"], -4.3993333333, places=6)

    def test_tack(self):
        out = self.legs("[MojitoLegs.tack(0, 90), MojitoLegs.tack(90, 0), MojitoLegs.tack(45, 45), MojitoLegs.tack(10, 190)]")
        self.assertEqual(out, ["S", "P", "", ""])

    def test_route_legs(self):
        out = self.legs("""(function () {
            var m = MojitoLegs.markIndex(MojitoLegs.normaliseMarks([
              {id: "O", lat: "52.8791166667", lon: "-4.3993333333"}, {id: "1", lat: "52.8783333333", lon: "-4.405"}]));
            return MojitoLegs.routeLegs(["O", "1", "O"], m, 347).map(function (l) {
              return [l.from.id, l.to.id, Math.round(l.bearing * 10) / 10, Math.round(l.twa)]; });
          })()""")
        self.assertEqual(out, [["O", "1", 257.1, 90], ["1", "O", 77.1, 90]])

    def test_no_polar_or_chart(self):
        out = self.legs("[MojitoLegs.targetSpeedInfo([], 90, 12), MojitoLegs.sailFor({twas: [], rows: []}, 90, 12), "
                        "MojitoLegs.targetSpeedInfo([{tws: 6, points: []}], 90, NaN)]")
        self.assertEqual(out, [None, "—", None])

    def test_sail_chart_blank_and_padded_cells(self):
        chart = '{twas: [40, 90], rows: [{tws: 10, sails: [" J2 ", ""]}]}'
        self.assertEqual(self.legs("[MojitoLegs.sailFor(%s, 42, 11), MojitoLegs.sailFor(%s, 88, 11)]" % (chart, chart)),
                         ["J2", "—"])

    def test_polar_without_deep_angles_is_limited_to_deepest_point(self):
        # Nothing at 90° or deeper: no downwind VMG target, so the target is the
        # polar's deepest angle, marked "limited".
        out = self.legs("MojitoLegs.targetSpeedInfo([{tws: 10, points: [{twa: 45, bsp: 6}, {twa: 80, bsp: 7}]}], 170, 10)")
        self.assertEqual((out["polarTwa"], out["bsp"], out["mode"]), (80, 7, "limited"))

    def test_bearing_bar_clamps_leg_index(self):
        out = self.legs("""(function () {
            var m = MojitoLegs.markIndex(MojitoLegs.normaliseMarks([
              {id: "O", lat: "52.8791166667", lon: "-4.3993333333"}, {id: "1", lat: "52.8783333333", lon: "-4.405"}]));
            return MojitoLegs.bearingBar(MojitoLegs.routeLegs(["O", "1"], m, 0), 7, null);
          })()""")
        self.assertEqual(out["toMarkLabel"], "To 1")
        self.assertEqual(out["nextLegRange"], "Last leg")


if __name__ == "__main__":
    unittest.main()
