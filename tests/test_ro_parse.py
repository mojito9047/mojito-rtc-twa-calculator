"""Converting Race Officer /api/current_race_course into marks/course/roundings."""

import copy
import unittest

from server import race_officer
from tests.helpers import FakeRaceOfficer, load_fixture


class ParseCourseTests(unittest.TestCase):
    def setUp(self):
        self.ro = FakeRaceOfficer()

    def parse(self, payload):
        return race_officer.parse_current_payload(payload)

    def test_fixed_course_route_and_roundings(self):
        marks, route, roundings, name = self.parse(self.ro.make())
        self.assertEqual(route, ["O", "1", "8", "4", "O", "9", "7", "O"])
        self.assertEqual(roundings, {
            "0:O-1": "P", "1:1-8": "P", "2:8-4": "P", "3:4-O": "S",
            "4:O-9": "P", "5:9-7": "P", "6:7-O": "P",
        })
        self.assertEqual(name, "N")

    def test_repeated_marks_are_kept_in_route(self):
        _, route, _, _ = self.parse(self.ro.make())
        self.assertEqual(route.count("O"), 3)

    def test_every_route_mark_has_a_position(self):
        marks, route, _, _ = self.parse(self.ro.make())
        ids = {m["id"] for m in marks}
        for mark_id in route:
            self.assertIn(mark_id, ids)

    def test_compound_parent_marks_without_position_are_skipped(self):
        payload = self.ro.make()
        compound = [code for code, m in payload["marks"].items() if m.get("lat") is None]
        self.assertTrue(compound, "fixture should contain compound marks (Y, A)")
        marks, _, _, _ = self.parse(payload)
        ids = {m["id"] for m in marks}
        for code in compound:
            self.assertNotIn(code, ids)
        # ...but their corners, which have positions, are imported.
        corners = [c for c, m in payload["marks"].items() if m.get("component_of")]
        for code in corners:
            self.assertIn(race_officer.clean_id(code, code), ids)

    def test_marks_are_stored_as_decimal_strings(self):
        marks, _, _, _ = self.parse(self.ro.make())
        one = next(m for m in marks if m["id"] == "1")
        self.assertAlmostEqual(float(one["lat"]), 52.8783333333, places=6)
        self.assertAlmostEqual(float(one["lon"]), -4.405, places=6)
        self.assertEqual(one["name"], "Partington Marine")

    def test_shortened_course_uses_sailed_route_and_adds_finish(self):
        marks, route, roundings, _ = self.parse(self.ro.make(shorten_after=4))
        self.assertEqual(route, ["O", "1", "8", "4", race_officer.FINISH_MARK_ID])
        self.assertEqual(roundings["3:4-FIN"], "F")
        fin = next(m for m in marks if m["id"] == race_officer.FINISH_MARK_ID)
        self.assertAlmostEqual(float(fin["lat"]), 52.88059)
        self.assertEqual(fin["name"], "Middle of the finish line")

    def test_waypoint_becomes_via_leg(self):
        _, route, roundings, _ = self.parse(self.ro.make(waypoint_after=2))
        self.assertEqual(route[:4], ["O", "1", "TC", "8"])
        self.assertEqual(roundings["1:1-TC"], "V")
        self.assertEqual(roundings["2:TC-8"], "P")

    def test_older_race_officer_without_sailed_uses_course_as_set(self):
        payload = self.ro.make()
        del payload["course"]["sailed"]
        _, route, _, _ = self.parse(payload)
        self.assertEqual(route, ["O", "1", "8", "4", "O", "9", "7", "O"])

    def test_missing_marks_dictionary_falls_back_to_route_positions(self):
        payload = self.ro.make()
        payload["marks"] = {}
        marks, route, _, _ = self.parse(payload)
        self.assertEqual({m["id"] for m in marks}, set(route))

    def test_not_ok_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            self.parse({"ok": False})

    def test_course_with_fewer_than_two_marks_is_rejected(self):
        payload = self.ro.make()
        payload["course"]["sailed"]["expanded_marks"] = payload["course"]["sailed"]["expanded_marks"][:1]
        payload["course"]["expanded_marks"] = payload["course"]["expanded_marks"][:1]
        payload["course"]["marks"] = []
        with self.assertRaises(ValueError):
            self.parse(payload)


class RaceInfoTests(unittest.TestCase):
    def test_fields_from_payload(self):
        payload = FakeRaceOfficer().make(course_set=False, postponed=True)
        info = race_officer.race_info(payload)
        self.assertEqual(info["race_id"], 643)
        self.assertEqual(info["race_name"], payload["race"]["name"])
        self.assertFalse(info["course_set"])
        self.assertTrue(info["postponed"])
        self.assertEqual(info["postponement_flag"], "AP")
        self.assertEqual(info["course_label"], "N")

    def test_older_race_officer_without_course_set_counts_as_set(self):
        payload = load_fixture("ro_current_race_course.json")
        del payload["race"]["course_set"]
        self.assertTrue(race_officer.race_info(payload)["course_set"])

    def test_first_warning_falls_back_to_start_time(self):
        payload = copy.deepcopy(load_fixture("ro_current_race_course.json"))
        payload["race"].pop("first_warning_time", None)
        payload["race"]["start_time"] = "2026-08-13T10:49:00"
        self.assertEqual(race_officer.race_info(payload)["first_warning_time"], "2026-08-13T10:49:00")


class RoundingCodeTests(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(race_officer.rounding_code("port"), "P")
        self.assertEqual(race_officer.rounding_code("Starboard"), "S")
        self.assertEqual(race_officer.rounding_code("via"), "V")
        self.assertEqual(race_officer.rounding_code("start"), "")
        self.assertEqual(race_officer.rounding_code(None), "")


if __name__ == "__main__":
    unittest.main()
