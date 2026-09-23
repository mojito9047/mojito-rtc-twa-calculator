"""copy_previous_install.py: bringing settings, marks and course across from the previous version."""

import contextlib
import io
import json
import os
import pathlib
import tempfile
import time
import unittest

import copy_previous_install as cpi


class CopyPreviousInstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.parent = pathlib.Path(self._tmp.name)
        self.old = self.make_install("mojito_rtc_twa_calculator_v70", "v70")
        self.new = self.make_install("mojito_rtc_twa_calculator_v71", "v71")
        (self.new / "SailChart J122 North.txt").write_text("shipped chart", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def make_install(self, name, version=None):
        folder = self.parent / name
        (folder / "templates").mkdir(parents=True)
        (folder / "templates" / "index.html").write_text("<html>", encoding="utf-8")
        (folder / "app.py").write_text("", encoding="utf-8")
        if version:
            (folder / "server").mkdir()
            (folder / "server" / "__init__.py").write_text(f'VERSION = "{version}"\n', encoding="utf-8")
        return folder

    def use(self, folder, settings, runtime=None, hours_ago=1, in_runtime=True):
        """Give an install saved settings and state, last used some hours ago."""
        (folder / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        paths = [folder / "settings.json"]
        for name, data in (runtime or {}).items():
            path = folder / "runtime" / name if in_runtime else folder / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            paths.append(path)
        when = time.time() - hours_ago * 3600
        for path in paths:
            os.utime(path, (when, when))

    def run_main(self, *argv, answer="y"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cpi.main(list(argv), here=self.new, ask=lambda prompt: answer)
        return code, out.getvalue()

    def test_copies_settings_state_and_uploaded_files(self):
        (self.old / "My Chart.txt").write_text("uploaded chart", encoding="utf-8")
        (self.old / "SailChart J122 North.txt").write_text("edited chart", encoding="utf-8")
        settings = {"instrument_source": "h5000", "sailchart_file": "My Chart.txt",
                    "polar_file": "SailChart J122 North.txt", "expedition_marks_file": "C:\\Marks\\marks.xml"}
        self.use(self.old, settings, {"course.json": {"course": "O 1 O"}, "marks.json": [{"id": "O"}]})

        code, out = self.run_main()

        self.assertEqual(code, 0)
        self.assertIn("mojito_rtc_twa_calculator_v70 (v70)", out)
        self.assertEqual(json.loads((self.new / "settings.json").read_text())["instrument_source"], "h5000")
        self.assertEqual(json.loads((self.new / "runtime" / "course.json").read_text()), {"course": "O 1 O"})
        self.assertTrue((self.new / "runtime" / "marks.json").exists())
        # An uploaded file this version does not have is copied; a shipped one is kept, with a note.
        self.assertEqual((self.new / "My Chart.txt").read_text(), "uploaded chart")
        self.assertEqual((self.new / "SailChart J122 North.txt").read_text(), "shipped chart")
        self.assertIn("Kept this version's SailChart J122 North.txt", out)
        # The previous version is left as it was.
        self.assertEqual((self.old / "SailChart J122 North.txt").read_text(), "edited chart")
        self.assertTrue((self.old / "runtime" / "course.json").exists())

    def test_saved_map_tiles_come_across(self):
        self.use(self.old, {"instrument_source": "expedition"}, {"course.json": {"course": "O 1 O"}})
        tile = self.old / "runtime" / "tiles" / "osm" / "15" / "15770" / "10622.png"
        tile.parent.mkdir(parents=True)
        tile.write_bytes(b"png")
        code, out = self.run_main()
        self.assertIn("runtime/tiles (1 map tiles)", out)
        self.assertEqual((self.new / "runtime" / "tiles" / "osm" / "15" / "15770" / "10622.png").read_bytes(), b"png")
        self.assertTrue(tile.exists())                                     # the previous version keeps its own

    def test_state_from_the_app_folder_of_v60_and_earlier(self):
        old = self.make_install("mojito_rtc_twa_calculator_v59")          # no server/, no runtime/
        self.old.rename(self.parent / "unused")                            # leave v59 as the only one
        self.use(old, {"instrument_source": "expedition"}, {"course.json": {"course": "O 4 O"}}, in_runtime=False)
        code, out = self.run_main()
        self.assertIn("mojito_rtc_twa_calculator_v59 (mojito_rtc_twa_calculator_v59)", out)
        self.assertEqual(json.loads((self.new / "runtime" / "course.json").read_text()), {"course": "O 4 O"})

    def test_picks_the_most_recently_used_version(self):
        older = self.make_install("mojito_rtc_twa_calculator_v69", "v69")
        self.use(older, {"instrument_source": "nmea0183"}, hours_ago=48)
        self.use(self.old, {"instrument_source": "h5000"}, hours_ago=2)
        self.assertEqual(cpi.find_previous(self.new), self.old)
        self.run_main()
        self.assertEqual(json.loads((self.new / "settings.json").read_text())["instrument_source"], "h5000")

    def test_nothing_found(self):
        code, out = self.run_main()                                        # the old install was never used
        self.assertEqual(code, 0)
        self.assertIn("No earlier version found", out)
        self.assertFalse((self.new / "settings.json").exists())

    def test_not_copied_over_a_version_used_since(self):
        self.use(self.old, {"instrument_source": "h5000"}, hours_ago=5)
        self.use(self.new, {"instrument_source": "manual"}, hours_ago=1)
        code, out = self.run_main()
        self.assertIn("used since then", out)
        self.assertEqual(json.loads((self.new / "settings.json").read_text())["instrument_source"], "manual")

    def test_answer_no_copies_nothing(self):
        self.use(self.old, {"instrument_source": "h5000"}, {"course.json": {"course": "O 1 O"}})
        for answer in ("n", "no"):
            code, out = self.run_main(answer=answer)
            self.assertIn("Nothing copied", out)
        self.assertFalse((self.new / "settings.json").exists())
        self.assertFalse((self.new / "runtime").exists())

    def test_from_a_named_folder(self):
        self.use(self.old, {"instrument_source": "h5000"})
        code, _ = self.run_main("--from", str(self.old), "--yes", answer="n")   # --yes: no question asked
        self.assertEqual(code, 0)
        self.assertTrue((self.new / "settings.json").exists())
        code, out = self.run_main("--from", str(self.parent))
        self.assertEqual(code, 1)
        self.assertIn("is not a Mojito RTC TWA Calculator folder", out)


if __name__ == "__main__":
    unittest.main()
