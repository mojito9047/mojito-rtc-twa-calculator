"""Shared test setup.

AppTestCase runs each test against a throwaway copy of the app folder, with
Expedition and the Race Officer app replaced by fakes, so tests never touch
runtime/ or need either program running.
"""

import copy
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import app
from server import expedition_dll, instruments, race_officer, storage

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# Files copied into each test's app folder. Runtime files are seeded from the
# committed examples, the same way a fresh install starts.
APP_FILES = ["SailChart J122 North.txt", "J122.txt", "marks.xml",
             "marks.example.json", "course.example.json"]


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeRaceOfficer:
    """Stands in for the Race Officer app's public API.

    `payload` is what /api/current_race_course returns and `signature` what
    /public/race/state reports. Set `fail` to simulate the network being down.
    """

    def __init__(self):
        self.base_payload = load_fixture("ro_current_race_course.json")
        self.payload = self.make()
        self.signature = "sig-1"
        self.fail = False
        self.state_supported = True
        self.calls = {"state": 0, "full": 0}

    def make(self, course_set=True, start_in=None, postponed=False, shorten_after=None,
             race_id=643, waypoint_after=None):
        """Build a payload from the saved fixture.

        start_in: seconds until the first start (negative = already started).
        shorten_after: cut course.sailed after this many expanded marks and add
            the run to the finish, as Race Officer does after a shortening.
        waypoint_after: insert a waypoint (rounding "via") after this many
            expanded marks of course.sailed.
        """
        p = copy.deepcopy(self.base_payload)
        race = p["race"]
        race.update(id=race_id, course_set=course_set, postponed=postponed,
                    postponement_flag="AP" if postponed else "",
                    postponement_ends_at="", first_warning_time="", start_time="",
                    first_start_time="")
        if postponed:
            race["postponement_ends_at"] = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
        if start_in is not None:
            start = datetime.now() + timedelta(seconds=start_in)
            race["first_start_time"] = start.isoformat(timespec="seconds")
            race["first_warning_time"] = race["start_time"] = (start - timedelta(minutes=5)).isoformat(timespec="seconds")
        sailed = p["course"]["sailed"]
        if waypoint_after is not None:
            wp = dict(sailed["expanded_marks"][0])
            wp.update(code="TC", display="TC", name="Test waypoint", rounding="via",
                      waypoint=True, lat=52.872, lon=-4.41)
            sailed["expanded_marks"].insert(waypoint_after, wp)
        if shorten_after is not None:
            sailed["expanded_marks"] = sailed["expanded_marks"][:shorten_after]
            sailed["finish"] = {"lat": 52.88059, "lon": -4.4001742, "description": "Middle of the finish line"}
            p["course"]["shortened"] = True
            p["course"]["shortened_at"] = {"index": 2, "mark": "4", "display": "4",
                                           "label": "4 (rounding 1)", "time": ""}
        return p

    def get_json(self, url, timeout=12):
        if self.fail:
            raise OSError("network down")
        if url.endswith("/public/race/state"):
            self.calls["state"] += 1
            if not self.state_supported:
                raise OSError("HTTP 404")
            return {"ok": True, "signature": self.signature}
        if url.endswith("/api/current_race_course"):
            self.calls["full"] += 1
            return copy.deepcopy(self.payload)
        raise AssertionError(f"unexpected Race Officer URL {url}")


class FakeExpedition:
    """Values returned by read_var(); None means Expedition reports no data."""

    def __init__(self):
        self.values = {
            expedition_dll.Var.Twd: 350.0,
            expedition_dll.Var.Tws: 12.0,
            expedition_dll.Var.Bsp: 6.5,
            expedition_dll.Var.Hdg: 175.0,
            expedition_dll.Var.Cog: 174.0,
            expedition_dll.Var.Sog: 6.4,
            expedition_dll.Var.Lat: 52.8883,
            expedition_dll.Var.Lon: -4.4079,
        }

    def read_var(self, var):
        value = self.values.get(var)
        if value is None:
            return None, None, "Expedition returned invalid/no data for this variable."
        return value, 0, None


class AppTestCase(unittest.TestCase):
    """Test case with an isolated app folder, fake Expedition and fake Race Officer.

    By default read_var() itself is faked. Set FAKE_ONLY_EXPEDITION = True to
    fake just the Expedition DLL, so the instrument source selection is real.
    """

    FAKE_ONLY_EXPEDITION = False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        for name in APP_FILES:
            shutil.copy(ROOT / name, self.dir / name)
        # Tests start from known settings: the defaults (settings.json is not in
        # git or the release), with the fake Race Officer's address.
        settings = dict(storage.DEFAULT_SETTINGS)
        settings.update(race_officer_api_base="http://ro.test", race_officer_poll_enabled=True,
                        race_officer_poll_interval_seconds=10,
                        instrument_source="expedition",
                        h5000_host="192.168.15.149", h5000_port=2053, nmea_host="192.168.15.166", nmea_port=10110)
        self.write_json("settings.json", settings, runtime=False)

        self.ro = FakeRaceOfficer()
        self.exp = FakeExpedition()
        self._patches = [
            mock.patch.object(storage, "app_file", lambda name: self.dir / name),
            mock.patch.object(race_officer, "get_json", self.ro.get_json),
            mock.patch.object(instruments, "read_expedition_var" if self.FAKE_ONLY_EXPEDITION else "read_var",
                              self.exp.read_var),
        ]
        for p in self._patches:
            p.start()
        storage.prepare_runtime_dir()
        self.client = app.app.test_client()

    def tearDown(self):
        instruments.stop_live_source()
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def set_settings(self, **changes):
        settings = self.read_json("settings.json", runtime=False)
        settings.update(changes)
        self.write_json("settings.json", settings, runtime=False)

    # -- file helpers -------------------------------------------------------

    def path(self, name, runtime=True):
        return self.dir / "runtime" / name if runtime else self.dir / name

    def read_json(self, name, runtime=True):
        return json.loads(self.path(name, runtime).read_text(encoding="utf-8"))

    def write_json(self, name, data, runtime=True):
        path = self.path(name, runtime)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def course(self):
        return self.read_json("course.json")["course"]

    def roundings(self):
        return self.read_json("course.json")["roundings"]

    def current_leg(self):
        return self.read_json("current_leg.json")["current_leg"]

    def sync(self, force=False):
        return race_officer.import_current_if_changed(force=force)


# ---------------------------------------------------------------------------
# Running page JavaScript in Node
# ---------------------------------------------------------------------------

def node_available():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True, timeout=20)
        return True
    except Exception:
        return False


NODE = node_available()
requires_node = unittest.skipUnless(NODE, "Node.js is not installed; page JavaScript tests skipped")


def run_js(page=None, scripts=(), setup="", expr="null"):
    """Run a page's inline scripts (and any static scripts) in Node; return expr's value.

    page:    template name, e.g. "mfd.html" — its inline <script> blocks are run
             with a stub browser (see tests/js/harness.js).
    scripts: extra files relative to the app folder, e.g. "static/race_start.js".
    setup:   JavaScript run afterwards, to set page globals.
    expr:    JavaScript expression; its value is returned (via JSON).
    """
    request = {
        "page": str(ROOT / "templates" / page) if page else None,
        "scripts": [str(ROOT / s) for s in scripts],
        "setup": setup,
        "expr": expr,
    }
    proc = subprocess.run(["node", str(ROOT / "tests" / "js" / "harness.js")],
                          input=json.dumps(request), capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"JavaScript failed for {page or scripts}:\n{proc.stderr}")
    return json.loads(proc.stdout)
