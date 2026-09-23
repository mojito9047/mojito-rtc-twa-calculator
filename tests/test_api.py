"""The app's own HTTP API: course, marks, current leg, race start, wind and position."""

import json
import re
import unittest
from pathlib import Path

import app
from server import VERSION, expedition_dll, race_officer, storage
from tests.helpers import AppTestCase


class CourseApiTests(AppTestCase):
    def test_round_trip(self):
        body = {"course": "O 1 8", "roundings": {"0:O-1": "P", "1:1-8": "S"}}
        self.assertEqual(self.client.post("/api/course", json=body).status_code, 200)
        data = self.client.get("/api/course").get_json()
        self.assertEqual(data["course"], "O 1 8")
        self.assertEqual(data["roundings"], body["roundings"])

    def test_via_and_finish_roundings_survive_resave(self):
        # A Race Officer import can add V (waypoint) and F (finish) legs; saving
        # the course from the editor must not strip them.
        body = {"course": "O 1 TC 8 FIN",
                "roundings": {"0:O-1": "P", "1:1-TC": "V", "2:TC-8": "S", "3:8-FIN": "F", "x": "bogus"}}
        self.client.post("/api/course", json=body)
        self.assertEqual(self.roundings(), {"0:O-1": "P", "1:1-TC": "V", "2:TC-8": "S", "3:8-FIN": "F"})

    def test_empty_course_stays_empty(self):
        # A cleared course must not fall back to the built-in default course.
        self.write_json("course.json", {"course": "", "roundings": {}})
        self.assertEqual(self.client.get("/api/course").get_json()["course"], "")


class CurrentLegApiTests(AppTestCase):
    def test_round_trip(self):
        self.client.post("/api/current_leg", json={"current_leg": 3})
        self.assertEqual(self.client.get("/api/current_leg").get_json()["current_leg"], 3)

    def test_negative_clamped_to_zero(self):
        self.client.post("/api/current_leg", json={"current_leg": -2})
        self.assertEqual(self.current_leg(), 0)


class MarksApiTests(AppTestCase):
    def test_get_returns_seeded_example_marks(self):
        data = self.client.get("/api/marks").get_json()
        self.assertTrue(data["ok"])
        self.assertGreater(len(data["marks"]), 2)

    def test_save_writes_runtime_file(self):
        marks = [{"id": "A", "name": "Alpha", "lat": "52.8", "lon": "-4.4"},
                 {"id": "B", "name": "Bravo", "lat": "52.9", "lon": "-4.3"}]
        self.assertEqual(self.client.post("/api/marks", json={"marks": marks}).status_code, 200)
        self.assertEqual([m["id"] for m in self.read_json("marks.json")], ["A", "B"])


class RaceStartApiTests(AppTestCase):
    def start(self):
        return self.client.get("/api/race_start").get_json()

    def test_countdown(self):
        self.ro.payload = self.ro.make(start_in=180)
        self.sync()
        data = self.start()
        self.assertTrue(data["live"])
        self.assertTrue(170 < data["seconds_to_start"] <= 180)
        self.assertRegex(data["start_clock"], r"^\d\d:\d\d:\d\d$")

    def test_started(self):
        self.ro.payload = self.ro.make(start_in=-600)
        self.sync()
        self.assertLess(self.start()["seconds_to_start"], -590)

    def test_no_start_time(self):
        self.sync()
        data = self.start()
        self.assertIsNone(data["seconds_to_start"])
        self.assertEqual(data["start_clock"], "")

    def test_postponed(self):
        self.ro.payload = self.ro.make(start_in=300, postponed=True)
        self.sync()
        data = self.start()
        self.assertTrue(data["race"]["postponed"])
        self.assertEqual(data["race"]["postponement_flag"], "AP")
        self.assertRegex(data["postponement_ends_clock"], r"^\d\d:\d\d$")

    def test_shortened(self):
        self.ro.payload = self.ro.make(shorten_after=4)
        self.sync()
        race = self.start()["race"]
        self.assertTrue(race["shortened"])
        self.assertEqual(race["shortened_label"], "4 (rounding 1)")

    def test_course_not_set(self):
        self.ro.payload = self.ro.make(course_set=False)
        self.sync()
        self.assertFalse(self.start()["race"]["course_set"])

    def test_not_live_when_polling_off(self):
        self.sync()
        settings = self.read_json("settings.json", runtime=False)
        settings["race_officer_poll_enabled"] = False
        self.write_json("settings.json", settings, runtime=False)
        self.assertFalse(self.start()["live"])

    def test_not_live_when_stale(self):
        self.sync()
        old = race_officer.read_state()["last_check"] - 3600
        race_officer.update_state({"last_check": old, "last_full_check": old})
        self.assertFalse(self.start()["live"])

    def test_not_live_before_first_poll(self):
        self.assertFalse(self.start()["live"])


class ExpeditionApiTests(AppTestCase):
    def test_channel_numbers(self):
        # Checked against a running Expedition; enums.py has Lat..Sog one low.
        v = expedition_dll.Var
        self.assertEqual((v.Bsp, v.Tws, v.Twd, v.Hdg), (1, 5, 6, 13))
        self.assertEqual((v.Lat, v.Lon, v.Cog, v.Sog), (48, 49, 50, 51))

    def test_position(self):
        data = self.client.get("/api/position").get_json()
        self.assertTrue(data["ok"])
        self.assertAlmostEqual(data["lat"], 52.8883)
        self.assertAlmostEqual(data["lon"], -4.4079)

    def test_position_missing(self):
        self.exp.values[expedition_dll.Var.Lat] = None
        data = self.client.get("/api/position").get_json()
        self.assertFalse(data["ok"])
        self.assertIsNone(data["lat"])

    def test_position_zero_zero_is_no_fix(self):
        self.exp.values[expedition_dll.Var.Lat] = 0.0
        self.exp.values[expedition_dll.Var.Lon] = 0.0
        self.assertFalse(self.client.get("/api/position").get_json()["ok"])

    def test_position_out_of_range_is_no_fix(self):
        self.exp.values[expedition_dll.Var.Lat] = 174.0     # e.g. a COG read by mistake
        self.assertFalse(self.client.get("/api/position").get_json()["ok"])

    def test_expedition_values(self):
        data = self.client.get("/api/expedition").get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["Twd"], 350.0)
        self.assertEqual(data["data"]["Sog"], 6.4)

    def test_twd_from_expedition(self):
        data = self.client.get("/api/twd").get_json()
        self.assertEqual(data["source"], "expedition")
        self.assertEqual(data["twd"], 350.0)

    def test_twd_falls_back_to_displayed_wind(self):
        self.client.post("/api/display_wind", json={"twd": 123, "tws": 9})
        self.exp.values[expedition_dll.Var.Twd] = None
        data = self.client.get("/api/twd").get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["twd"], 123)


class WindTests(AppTestCase):
    """/api/wind: the wind every display uses; "manual" is the source with no instruments."""

    FAKE_ONLY_EXPEDITION = True       # the manual source is chosen inside read_var

    def wind(self):
        return self.client.get("/api/wind").get_json()

    def use_manual(self):
        resp = self.client.post("/api/settings", json={"instrument_source": "manual"})
        self.assertEqual(resp.status_code, 200, resp.get_json())

    def test_instruments_by_default(self):
        w = self.wind()
        self.assertEqual((w["manual"], w["source"], w["twd"], w["tws"], w["ok"]), (False, "expedition", 350.0, 12.0, True))

    def test_switching_to_manual_starts_from_the_wind_in_use(self):
        self.use_manual()
        w = self.wind()
        self.assertEqual((w["manual"], w["source"], w["twd"], w["tws"]), (True, "manual", 350.0, 12.0))

    def test_manual_wind_used_everywhere(self):
        self.use_manual()
        w = self.client.post("/api/wind", json={"twd": 200, "tws": 8.5}).get_json()
        self.assertEqual((w["twd"], w["tws"]), (200.0, 8.5))
        twd = self.client.get("/api/twd").get_json()
        self.assertEqual((twd["twd"], twd["source"]), (200.0, "manual"))
        self.assertEqual(self.client.get("/api/expedition").get_json()["data"]["Tws"], 8.5)   # MFD's TWS path

    def test_manual_has_no_other_instruments(self):
        self.use_manual()
        data = self.client.get("/api/expedition").get_json()
        self.assertIsNone(data["data"]["Bsp"])
        self.assertIn("manual wind", data["errors"]["Hdg"])
        self.assertFalse(self.client.get("/api/position").get_json()["ok"])
        status = self.client.get("/api/instruments").get_json()
        self.assertEqual((status["kind"], status["label"], status["connected"]), ("manual", "Manual wind", True))

    def test_manual_values_kept_while_on_instruments(self):
        self.use_manual()
        self.client.post("/api/wind", json={"twd": 90, "tws": 15})
        self.client.post("/api/settings", json={"instrument_source": "expedition"})
        self.assertEqual(self.wind()["twd"], 350.0)
        self.assertEqual(self.wind()["manual_wind"], {"twd": 90.0, "tws": 15.0})
        self.use_manual()                                   # not re-seeded: the saved values come back
        self.assertEqual((self.wind()["twd"], self.wind()["tws"]), (90.0, 15.0))

    def test_manual_input_checked(self):
        for body in ({"twd": 400}, {"twd": -5}, {"tws": -1}, {"tws": 100}, {"twd": "north"}):
            self.assertEqual(self.client.post("/api/wind", json=body).status_code, 400, body)

    def test_manual_without_values(self):
        self.set_settings(instrument_source="manual")       # e.g. edited in settings.json
        w = self.wind()
        self.assertFalse(w["ok"])
        self.assertEqual(w["error"], "Manual wind not entered yet")
        self.assertFalse(self.client.get("/api/instruments").get_json()["connected"])

    def test_instrument_twd_missing_uses_last_shown(self):
        self.client.post("/api/display_wind", json={"twd": 123, "tws": 9})
        self.exp.values[expedition_dll.Var.Twd] = None
        w = self.wind()
        self.assertEqual((w["twd"], w["source"], w["ok"]), (123, "display_fallback", True))

    def test_manual_wind_is_runtime_state(self):
        self.assertIn("manual_wind.json", storage.RUNTIME_FILES)


class FileApiTests(AppTestCase):
    def test_sail_chart_parses(self):
        data = self.client.get("/api/sailchart").get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["twas"])
        self.assertTrue(data["rows"])

    def test_polar_parses(self):
        data = self.client.get("/api/polar").get_json()
        self.assertTrue(data["ok"])
        row6 = next(r for r in data["rows"] if r["tws"] == 6.0)
        self.assertIn({"twa": 90.0, "bsp": 6.97}, row6["points"])


class UploadTests(AppTestCase):
    def upload(self, file_type, name, content):
        import io
        return self.client.post("/api/upload_file", data={"type": file_type, "file": (io.BytesIO(content), name)},
                                content_type="multipart/form-data")

    def test_polar_upload_saves_and_selects_file(self):
        resp = self.upload("polar", "New Polar.txt", b"6 45 5.0 90 7.0 180 3.5\n")
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertTrue((self.dir / "New Polar.txt").exists())
        self.assertEqual(self.read_json("settings.json", runtime=False)["polar_file"], "New Polar.txt")
        self.assertEqual(self.client.get("/api/polar").get_json()["rows"][0]["points"][1], {"twa": 90.0, "bsp": 7.0})

    def test_unsafe_filename_is_cleaned(self):
        resp = self.upload("sailchart", "..\\..\\evil<>.txt", b"\t36\n10\tJ1\n")
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertEqual(resp.get_json()["filename"], "evil_.txt")      # no path, unsafe characters replaced
        self.assertTrue((self.dir / "evil_.txt").exists())

    def test_marks_upload_must_be_xml(self):
        self.assertEqual(self.upload("marks", "marks.txt", b"x").status_code, 400)

    def test_unknown_type_rejected(self):
        self.assertEqual(self.upload("script", "a.txt", b"x").status_code, 400)


class ExpeditionMarksImportTests(AppTestCase):
    def test_groups_listed(self):
        groups = {g["name"]: g["count"] for g in self.client.get("/api/expedition_marks/groups").get_json()["groups"]}
        self.assertIn("Solent", groups)
        self.assertGreater(groups["Solent"], 0)

    def test_import_group_replaces_marks(self):
        resp = self.client.post("/api/expedition_marks/import", json={"group": "ISORA", "replace": True})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertEqual(len(self.read_json("marks.json")), resp.get_json()["imported_count"])

    def test_import_group_merges_without_duplicate_ids(self):
        before = len(self.read_json("marks.json"))
        resp = self.client.post("/api/expedition_marks/import", json={"group": "ISORA", "replace": False})
        marks = self.read_json("marks.json")
        self.assertEqual(len(marks), before + resp.get_json()["imported_count"])
        ids = [m["id"].upper() for m in marks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_group_rejected(self):
        resp = self.client.post("/api/expedition_marks/import", json={"group": "Nowhere"})
        self.assertEqual(resp.status_code, 400)


class SettingsApiTests(AppTestCase):
    def test_interval_clamped(self):
        self.client.post("/api/settings", json={"race_officer_poll_interval_seconds": 1})
        self.assertEqual(self.client.get("/api/settings").get_json()["settings"]["race_officer_poll_interval_seconds"], 5)

    def test_race_officer_address(self):
        resp = self.client.post("/api/settings", json={"race_officer_api_base": "https://pro.example.org/"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(storage.load_settings()["race_officer_api_base"], "https://pro.example.org")
        self.assertEqual(self.client.get("/api/race_officer/base").get_json()["base"], "https://pro.example.org")
        self.assertEqual(self.client.post("/api/settings", json={"race_officer_api_base": "pro.example.org"}).status_code, 400)

    def test_defaults_without_settings_json(self):
        # settings.json is not in git or the release zip: a fresh install starts from the defaults.
        self.path("settings.json", runtime=False).unlink()
        settings = self.client.get("/api/settings").get_json()["settings"]
        self.assertEqual(settings["race_officer_api_base"], "https://pro.pwllhelisailingclub.org")
        self.assertFalse(settings["race_officer_poll_enabled"])
        self.assertEqual(settings["instrument_source"], "expedition")
        self.assertEqual(settings["sailchart_file"], "SailChart J122 North.txt")
        self.assertTrue(self.client.get("/api/file_status").get_json()["sailchart_exists"])

    def test_blank_sail_chart_rejected(self):
        self.assertEqual(self.client.post("/api/settings", json={"sailchart_file": " "}).status_code, 400)

    def test_file_status(self):
        data = self.client.get("/api/file_status").get_json()
        self.assertTrue(data["sailchart_exists"] and data["polar_exists"] and data["expedition_marks_exists"])


class RuntimeFolderTests(AppTestCase):
    def test_seeded_from_examples(self):
        example = json.loads((self.dir / "course.example.json").read_text(encoding="utf-8"))
        self.assertEqual(self.read_json("course.json"), example)

    def test_legacy_files_moved(self):
        legacy = {"course": "O 1 O", "roundings": {}}
        self.path("course.json").unlink()
        self.write_json("course.json", legacy, runtime=False)
        storage.prepare_runtime_dir()
        self.assertFalse(self.path("course.json", runtime=False).exists())
        self.assertEqual(self.read_json("course.json"), legacy)

    def test_existing_runtime_file_not_overwritten(self):
        self.write_json("course.json", {"course": "O 9 O", "roundings": {}})
        self.write_json("course.json", {"course": "LEGACY", "roundings": {}}, runtime=False)
        storage.prepare_runtime_dir()
        self.assertEqual(self.course(), "O 9 O")


class RouteTests(unittest.TestCase):
    # Every URL the pages, the MFD and the docs rely on (the 27 served before
    # app.py was split into server/ in v64).
    EXPECTED = {
        "/", "/phone", "/mfd", "/api/display_wind", "/api/twd", "/api/expedition", "/api/position",
        "/api/upload_file", "/api/current_leg", "/api/course", "/api/race_officer/base",
        "/api/race_officer/current_preview", "/api/race_officer/import_current",
        "/api/race_officer/poll_status", "/api/race_officer/poll_config", "/api/race_officer/poll_once",
        "/api/race_start", "/api/settings", "/api/file_status", "/api/expedition_marks/groups",
        "/api/expedition_marks/import", "/api/marks", "/api/sailchart", "/api/polar", "/api/wind_history",
        "/api/mfd_status", "/api/health",
        "/api/instruments",                 # v67: instrument source status
        "/api/wind",                        # v69: the wind every display uses
    }

    def test_all_urls_still_served(self):
        served = {rule.rule for rule in app.app.url_map.iter_rules() if not rule.rule.startswith("/static")}
        self.assertEqual(served, self.EXPECTED)


class StorageTests(AppTestCase):
    def test_atomic_write_leaves_no_temp_file(self):
        target = self.path("course.json")
        storage.write_json(target, {"course": "O 1", "roundings": {}})
        self.assertEqual(self.course(), "O 1")
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_concurrent_writes_to_one_file(self):
        # The Course legs page can post its displayed wind twice at once; with a
        # shared temporary file one of the two writes used to fail (400).
        import threading
        errors = []

        def writer(n):
            try:
                for i in range(40):
                    storage.write_json(self.path("display_wind.json"), {"twd": n, "i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertIn(self.read_json("display_wind.json")["twd"], range(4))
        self.assertEqual(list(self.path("display_wind.json").parent.glob("*.tmp")), [])

    def test_atomic_write_survives_file_in_use(self):
        # On Windows the replace fails while another thread is reading the file.
        from unittest import mock
        calls = {"n": 0}
        real_replace = storage.os.replace

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("in use")
            return real_replace(src, dst)

        with mock.patch.object(storage.os, "replace", flaky_replace), mock.patch.object(storage.time, "sleep"):
            storage.write_json(self.path("course.json"), {"course": "O 8", "roundings": {}})
        self.assertEqual(self.course(), "O 8")

    def test_settings_defaults_and_clamping(self):
        self.write_json("settings.json", {"race_officer_poll_interval_seconds": 9999, "unknown": 1}, runtime=False)
        s = storage.load_settings()
        self.assertEqual(s["race_officer_poll_interval_seconds"], 300)
        self.assertEqual(s["polar_file"], "J122.txt")
        self.assertNotIn("unknown", s)


class PageTests(AppTestCase):
    def test_pages_render(self):
        for url in ["/", "/phone", "/mfd"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertIn(b"/static/race_start.js", resp.data, url)

    def test_one_race_officer_address_field(self):
        html = self.client.get("/").data.decode()
        self.assertEqual(html.count('id="raceOfficerApiBase"'), 1)
        self.assertNotIn("raceOfficerImportBase", html)
        self.assertIn('id="raceOfficerBaseShown"', html)

    def test_wind_and_course_page(self):
        html = self.client.get("/").data.decode()
        page = html[html.index('id="calculatorView"'):html.index('id="resultsView"')]
        self.assertIn('id="courseChartMap"', page)             # the chart is on this page
        self.assertIn('id="windMode"', page)
        self.assertNotIn('id="markListCourse"', html)          # the marks list is gone
        self.assertNotIn('id="tabChart"', html)                # and so is the separate chart tab
        self.assertNotIn('id="chartView"', html)
        self.assertNotIn('id="live"', html)                    # replaced by the Manual wind source
        self.assertIn('<option value="manual">', html)
        self.assertIn('class="card windStrip"', page)          # the wind is one compact strip
        self.assertNotIn('id="instrumentData"', page)          # without the instrument readout under it
        self.assertNotIn('class="grid"', page)                 # and the course card is full width

    def test_header(self):
        html = self.client.get("/").data.decode()
        self.assertIn("<h1>RTC TWA Calculator</h1>", html)
        self.assertIn("<title>RTC TWA Calculator</title>", html)
        self.assertNotIn("Reads live True Wind Direction", html)
        self.assertRegex(html, r'id="windModeHelp" hidden')    # shown only with manual wind

    def test_course_legs_page_has_no_marks_card(self):
        html = self.client.get("/").data.decode()
        page = html[html.index('id="resultsView"'):html.index('id="marksView"')]
        self.assertNotIn('id="markList"', page)
        self.assertNotIn("<h2>Marks</h2>", page)

    def test_marks_saved_in_degrees_and_minutes(self):
        marks = [{"id": "A", "name": "Alpha", "lat": "50 39.330N", "lon": "01 55.170W"},
                 {"id": "B", "name": "Bravo", "lat": "52 52.700N", "lon": "04 24.300W"}]
        self.assertEqual(self.client.post("/api/marks", json={"marks": marks}).status_code, 200)
        self.assertEqual(self.read_json("marks.json")[0]["lat"], "50 39.330N")

    def test_settings_sections_and_save_bar(self):
        html = self.client.get("/").data.decode()
        settings = html[html.index('id="settingsView"'):]
        for heading in ("<h2>Instruments</h2>", "<h2>Race Officer</h2>", ">Files</h2>"):
            self.assertIn(heading, settings)
        self.assertIn('class="settingsActions"', settings)
        # Every saved field is marked for the unsaved-changes tracking.
        for field in ("instrumentSource", "h5000Host", "h5000Port", "nmeaHost", "nmeaPort", "raceOfficerApiBase",
                      "sailchartFile", "polarFile", "expeditionMarksFile"):
            self.assertRegex(settings, f'id="{field}"[^>]*data-setting')

    def test_version_on_every_page(self):
        for url in ["/", "/phone", "/mfd"]:
            self.assertIn(VERSION, self.client.get(url).data.decode(), url)

    def test_version_matches_readme(self):
        # The newest "### vNN" heading in the README's version history.
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        headings = re.findall(r"^### (v\d+)\s*$", readme, re.M)
        self.assertEqual(max(headings, key=lambda v: int(v[1:])), VERSION)

    def test_sections_are_tabs(self):
        html = self.client.get("/").data.decode()
        nav = html[html.index('role="tablist"'):html.index("</nav>")]
        tabs = re.findall(r'<button class="tab[^"]*" role="tab" id="(\w+)"', nav)
        self.assertEqual(tabs, ["tabCalculator", "tabResults", "tabMarks", "tabImport", "tabRaceOfficer", "tabSettings"])
        self.assertIn("/static/fonts.css", html)

    def test_logo_has_transparent_background(self):
        html = self.client.get("/").data.decode()
        self.assertIn('src="/static/mojito-logo.png"', html)
        resp = self.client.get("/static/mojito-logo.png")
        try:
            self.assertEqual(resp.status_code, 200)
            data = resp.data
        finally:
            resp.close()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(data[25], 6)                           # colour type 6: RGB with alpha

    def test_fonts_bundled(self):
        # Served by the app, so the pages look right with no internet connection.
        css = self.client.get("/static/fonts.css")
        try:
            files = re.findall(r"url\('(fonts/[^']+)'\)", css.data.decode())
        finally:
            css.close()
        self.assertTrue(files)
        for name in files:
            resp = self.client.get("/static/" + name)
            try:
                self.assertEqual(resp.status_code, 200, name)
            finally:
                resp.close()

    def test_mfd_has_no_heading(self):
        self.assertNotIn(b"<h1>", self.client.get("/mfd").data)

    def test_static_script_served(self):
        resp = self.client.get("/static/race_start.js")
        try:
            self.assertEqual(resp.status_code, 200)
        finally:
            resp.close()


if __name__ == "__main__":
    unittest.main()
