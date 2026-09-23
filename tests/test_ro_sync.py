"""Race Officer polling: when to import, when to clear, keeping the current leg."""

import unittest

from server import race_officer
from tests.helpers import AppTestCase

FULL_ROUTE = "O 1 8 4 O 9 7 O"


class CourseNotSetTests(AppTestCase):
    def test_placeholder_course_is_not_imported(self):
        self.ro.payload = self.ro.make(course_set=False)
        result = self.sync()
        self.assertFalse(result["course_set"])
        self.assertNotEqual(self.course(), FULL_ROUTE)

    def test_showing_course_is_cleared_once_per_race(self):
        self.ro.payload = self.ro.make(course_set=False)
        self.write_json("current_leg.json", {"current_leg": 3})
        result = self.sync()
        self.assertTrue(result["changed"])
        self.assertEqual(self.course(), "")
        self.assertEqual(self.current_leg(), 0)

    def test_course_typed_while_waiting_is_kept(self):
        self.ro.payload = self.ro.make(course_set=False)
        self.sync()
        self.write_json("course.json", {"course": "O 1 O", "roundings": {}})
        self.ro.signature = "sig-2"          # force a full fetch
        self.sync()
        self.assertEqual(self.course(), "O 1 O")

    def test_previous_race_course_cleared_when_next_race_not_set(self):
        self.ro.payload = self.ro.make(race_id=643)
        self.sync()
        self.assertEqual(self.course(), FULL_ROUTE)
        self.ro.payload = self.ro.make(course_set=False, race_id=644)
        self.ro.signature = "sig-2"
        self.sync()
        self.assertEqual(self.course(), "")

    def test_setting_same_course_after_clear_imports_it(self):
        self.ro.payload = self.ro.make(course_set=False)
        self.sync()
        self.ro.payload = self.ro.make(course_set=True)
        self.ro.signature = "sig-2"
        result = self.sync()
        self.assertTrue(result["changed"])
        self.assertEqual(self.course(), FULL_ROUTE)

    def test_manual_import_refused_while_not_set(self):
        self.ro.payload = self.ro.make(course_set=False)
        resp = self.client.post("/api/race_officer/import_current", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("has not set a course", resp.get_json()["error"])


class ImportTests(AppTestCase):
    def test_course_set_imports(self):
        result = self.sync()
        self.assertTrue(result["changed"])
        self.assertEqual(self.course(), FULL_ROUTE)
        self.assertEqual(self.roundings()["3:4-O"], "S")

    def test_marks_written(self):
        self.sync()
        ids = {m["id"] for m in self.read_json("marks.json")}
        self.assertTrue({"O", "1", "8", "4", "9", "7"} <= ids)

    def test_unchanged_state_signature_skips_full_fetch(self):
        self.sync()
        full = self.ro.calls["full"]
        result = self.sync()
        self.assertFalse(result["changed"])
        self.assertEqual(self.ro.calls["full"], full)

    def test_full_fetch_at_least_every_minute(self):
        self.sync()
        state = race_officer.read_state()
        race_officer.update_state({"last_full_check": state["last_full_check"] - race_officer.FULL_CHECK_SECONDS - 1})
        full = self.ro.calls["full"]
        self.sync()
        self.assertEqual(self.ro.calls["full"], full + 1)

    def test_older_race_officer_without_state_endpoint_still_imports(self):
        self.ro.state_supported = False
        self.sync()
        self.assertEqual(self.course(), FULL_ROUTE)

    def test_moved_mark_reimports(self):
        self.sync()
        payload = self.ro.make()
        payload["marks"]["4"]["lat"] += 0.001
        self.ro.payload = payload
        self.ro.signature = "sig-2"
        self.assertTrue(self.sync()["changed"])

    def test_same_course_does_not_rewrite_files(self):
        self.sync()
        self.write_json("current_leg.json", {"current_leg": 4})
        self.ro.signature = "sig-2"          # e.g. a boat finished; course unchanged
        self.assertFalse(self.sync()["changed"])
        self.assertEqual(self.current_leg(), 4)

    def test_force_import_via_api(self):
        resp = self.client.post("/api/race_officer/import_current", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["course"], FULL_ROUTE)


class CurrentLegTests(AppTestCase):
    def test_shortening_keeps_current_leg(self):
        self.sync()
        self.write_json("current_leg.json", {"current_leg": 2})      # 8 -> 4
        self.ro.payload = self.ro.make(shorten_after=4)
        self.ro.signature = "sig-2"
        self.sync()
        self.assertEqual(self.course(), "O 1 8 4 FIN")
        self.assertEqual(self.current_leg(), 2)

    def test_changed_course_resets_leg(self):
        self.sync()
        self.write_json("current_leg.json", {"current_leg": 2})
        payload = self.ro.make()
        sailed = payload["course"]["sailed"]["expanded_marks"]
        sailed[1], sailed[2] = sailed[2], sailed[1]            # O 8 1 ...
        self.ro.payload = payload
        self.ro.signature = "sig-2"
        self.sync()
        self.assertEqual(self.current_leg(), 0)

    def test_next_race_with_same_course_resets_leg(self):
        self.sync()
        self.write_json("current_leg.json", {"current_leg": 5})
        self.ro.payload = self.ro.make(race_id=644)
        self.ro.signature = "sig-2"
        self.sync()
        self.assertEqual(self.current_leg(), 0)

    def test_network_error_does_not_reset_leg_on_recovery(self):
        self.sync()
        self.write_json("current_leg.json", {"current_leg": 3})
        self.ro.fail = True
        resp = self.client.post("/api/race_officer/poll_once", json={})
        self.assertEqual(resp.status_code, 400)
        state = race_officer.read_state()
        self.assertTrue(state["error"])
        self.assertTrue(state["signature"])
        self.ro.fail = False
        self.assertFalse(self.sync()["changed"])
        self.assertEqual(self.current_leg(), 3)


class PreviewTests(AppTestCase):
    def test_preview_changes_nothing(self):
        before = self.path("course.json").read_text(encoding="utf-8")
        resp = self.client.get("/api/race_officer/current_preview")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["course"], FULL_ROUTE)
        self.assertEqual(self.path("course.json").read_text(encoding="utf-8"), before)

    def test_preview_reports_course_not_set(self):
        self.ro.payload = self.ro.make(course_set=False)
        data = self.client.get("/api/race_officer/current_preview").get_json()
        self.assertFalse(data["course_set"])


if __name__ == "__main__":
    unittest.main()
