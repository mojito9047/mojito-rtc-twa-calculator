"""The release tooling (tools/release.py): version, release notes, what the zip may hold.

tools/ is developer tooling and not in the release zip, so these are skipped
when the suite runs on an installed copy.
"""

import importlib.util
import pathlib
import unittest

from server import VERSION

ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE_PY = ROOT / "tools" / "release.py"


def load_release():
    spec = importlib.util.spec_from_file_location("release", RELEASE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(RELEASE_PY.exists(), "developer tooling, not in the release zip")
class ReleaseToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load_release()

    def good_names(self, version="v71"):
        top = self.release.folder_name(version) + "/"
        names = [top + name for name in self.release.REQUIRED]
        names += [top + "wheels/flask-3.0.3-py3-none-any.whl"]
        names += [top + f"wheels/markupsafe-3.0.3-cp{v.replace('.', '')}-cp{v.replace('.', '')}-win_amd64.whl"
                  for v in self.release.PYTHON_VERSIONS]
        return names

    def test_version_and_names(self):
        self.assertEqual(self.release.read_version(), VERSION)
        self.assertEqual(self.release.folder_name("v71"), "mojito_rtc_twa_calculator_v71")
        self.assertEqual(self.release.zip_path("v71").name, "mojito_rtc_twa_calculator_v71.zip")

    def test_release_notes_are_the_readme_section(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notes = self.release.release_notes("v70", readme)
        self.assertTrue(notes.startswith("- The main page uses the Pwllheli Race Officer's look"))
        self.assertIn("Every page shows the app version", notes)
        self.assertNotIn("### v", notes)
        self.assertTrue(self.release.release_notes(VERSION, readme))          # this version has notes
        with self.assertRaises(self.release.ReleaseError):
            self.release.release_notes("v999", readme)

    def test_required_files_exist(self):
        for name in self.release.REQUIRED:
            self.assertTrue((ROOT / name).is_file(), name)

    def test_a_complete_zip_passes(self):
        self.assertEqual(self.release.check_zip_names(self.good_names(), "v71"), [])

    def test_zip_problems_are_found(self):
        top = "mojito_rtc_twa_calculator_v71/"
        for extra in ("settings.json", "runtime/course.json", "server/__pycache__/app.cpython-314.pyc",
                      ".venv/Scripts/python.exe", "tools/release.py", "make_release.bat"):
            problems = self.release.check_zip_names(self.good_names() + [top + extra], "v71")
            self.assertTrue(any(extra in p for p in problems), (extra, problems))
        names = [n for n in self.good_names() if "cp311" not in n and not n.endswith("/LICENSE")]
        problems = self.release.check_zip_names(names + ["stray.txt"], "v71")
        self.assertIn("missing: LICENSE", problems)
        self.assertIn("no MarkupSafe wheel for Python 3.11", problems)
        self.assertIn("outside mojito_rtc_twa_calculator_v71/: stray.txt", problems)


if __name__ == "__main__":
    unittest.main()
