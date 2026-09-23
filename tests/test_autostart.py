"""autostart.py: starting the app when you sign in to Windows, and keeping that on the newest version."""

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import autostart


class AutostartTests(unittest.TestCase):
    """The logic, with a stand-in for Windows' shortcuts: a .lnk file holding its target's path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        self.startup = root / "Startup"
        self.startup.mkdir()
        self.old = self.make_install(root / "mojito_rtc_twa_calculator_v73")
        self.new = self.make_install(root / "mojito_rtc_twa_calculator_v74")
        for name, fake in (("shortcut_targets", self.fake_targets), ("write_shortcut", self.fake_write)):
            patch = mock.patch.object(autostart, name, fake)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)

    @staticmethod
    def make_install(folder):
        (folder / "templates").mkdir(parents=True)
        (folder / "templates" / "index.html").write_text("<html>", encoding="utf-8")
        for name in ("app.py", "start_app.bat"):
            (folder / name).write_text("", encoding="utf-8")
        return folder

    @staticmethod
    def fake_targets(folder):
        return {p: pathlib.Path(p.read_text(encoding="utf-8")) for p in pathlib.Path(folder).glob("*.lnk")}

    @staticmethod
    def fake_write(path, target):
        pathlib.Path(path).write_text(str(target), encoding="utf-8")

    def shortcut(self, name, target):
        (self.startup / name).write_text(str(target), encoding="utf-8")

    def targets(self):
        return {p.name: pathlib.Path(p.read_text(encoding="utf-8")) for p in self.startup.glob("*.lnk")}

    def run_main(self, *argv, answers=()):
        replies = list(answers)

        def ask(prompt):
            if not replies:
                raise AssertionError(f"not expected to ask: {prompt}")
            return replies.pop(0)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = autostart.main(list(argv), here=self.new, folder=self.startup, ask=ask)
        return code, out.getvalue()

    def test_install_asks_and_turns_it_on(self):
        code, out = self.run_main("--install", answers=["y"])
        self.assertEqual(code, 0)
        self.assertEqual(self.targets(), {autostart.SHORTCUT_NAME: self.new / "start_app.bat"})
        self.assertIn("double-click autostart.bat", out)

    def test_install_answer_no(self):
        for answer in ("n", ""):
            code, out = self.run_main("--install", answers=[answer])
            self.assertIn("Auto-start not set up", out)
        self.assertEqual(self.targets(), {})

    def test_install_no_answer(self):
        # No keyboard (input ended): treated as no.
        def eof(prompt):
            raise EOFError

        with contextlib.redirect_stdout(io.StringIO()):
            autostart.main(["--install"], here=self.new, folder=self.startup, ask=eof)
        self.assertEqual(self.targets(), {})

    def test_upgrade_moves_auto_start_to_the_new_version_without_asking(self):
        self.shortcut(autostart.SHORTCUT_NAME, self.old / "start_app.bat")
        code, out = self.run_main("--install")                          # asking would fail the test
        self.assertIn("moved to this version", out)
        self.assertEqual(self.targets(), {autostart.SHORTCUT_NAME: self.new / "start_app.bat"})

    def test_a_shortcut_made_by_hand_is_replaced(self):
        # Made as README described before v75, to an earlier version.
        self.shortcut("start_app.bat - Shortcut.lnk", self.old / "start_app.bat")
        code, out = self.run_main("--install")
        self.assertEqual(self.targets(), {autostart.SHORTCUT_NAME: self.new / "start_app.bat"})

    def test_other_shortcuts_are_left_alone(self):
        self.shortcut("Expedition.lnk", pathlib.Path(r"C:\Program Files\Expedition\Expedition.exe"))
        self.run_main("--install", answers=["y"])                       # none of ours: it asks
        self.run_main("--off")
        self.assertEqual(set(self.targets()), {"Expedition.lnk"})

    def test_already_on_for_this_version(self):
        self.shortcut(autostart.SHORTCUT_NAME, self.new / "start_app.bat")
        code, out = self.run_main("--install")
        self.assertIn("Auto-start is on for this version", out)

    def test_off_removes_every_copy(self):
        self.shortcut(autostart.SHORTCUT_NAME, self.old / "start_app.bat")
        self.shortcut("start_app.bat - Shortcut.lnk", self.new / "start_app.bat")
        code, out = self.run_main("--off")
        self.assertIn("Auto-start turned off", out)
        self.assertEqual(self.targets(), {})
        self.assertIn("already off", self.run_main("--off")[1])

    def test_status(self):
        self.assertIn("Auto-start is off", self.run_main("--status")[1])
        self.shortcut(autostart.SHORTCUT_NAME, self.old / "start_app.bat")
        self.assertIn("starts mojito_rtc_twa_calculator_v73", self.run_main("--status")[1])
        self.run_main("--on")
        self.assertIn("starts this version", self.run_main("--status")[1])

    def test_autostart_bat_menu_can_switch_to_this_version(self):
        self.shortcut(autostart.SHORTCUT_NAME, self.old / "start_app.bat")
        code, out = self.run_main(answers=["n", "y"])                   # not off; yes, this version
        self.assertIn("moved to this version", out)
        self.assertEqual(self.targets(), {autostart.SHORTCUT_NAME: self.new / "start_app.bat"})

    def test_autostart_bat_menu_turns_it_off(self):
        self.shortcut(autostart.SHORTCUT_NAME, self.new / "start_app.bat")
        self.run_main(answers=["y"])
        self.assertEqual(self.targets(), {})


@unittest.skipUnless(sys.platform == "win32", "Windows shortcuts")
class WindowsShortcutTests(unittest.TestCase):
    def test_real_shortcut_starts_minimised(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            target = folder / "app folder" / "start_app.bat"             # a space in the path
            target.parent.mkdir()
            target.write_text("", encoding="utf-8")
            lnk = folder / autostart.SHORTCUT_NAME
            autostart.write_shortcut(lnk, target)
            self.assertEqual(autostart.shortcut_targets(folder), {lnk: target})
            style = autostart._powershell(
                "(New-Object -ComObject WScript.Shell).CreateShortcut($env:MOJITO_LNK).WindowStyle", MOJITO_LNK=lnk)
            self.assertEqual(style, str(autostart.MINIMISED))

    def test_startup_folder(self):
        self.assertTrue(str(autostart.startup_folder()).endswith(r"Start Menu\Programs\Startup"))


if __name__ == "__main__":
    unittest.main()
