"""File locations, settings and JSON state files.

Configuration (settings.json, sail chart, polar, marks.xml, the example files)
lives in the app folder. settings.json is written when settings are first
saved and is not in git or the release zip: until then DEFAULT_SETTINGS apply.
State the app rewrites while running lives in runtime/, also not in git.

Every path goes through app_file() or runtime_file(). Other modules call them
as storage.app_file(...), so tests can point the whole app at a temporary
folder by patching storage.app_file.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

RUNTIME_DIR_NAME = "runtime"
RUNTIME_FILES = ("marks.json", "course.json", "current_leg.json", "display_wind.json",
                 "wind_history.jsonl", "race_officer_poll_state.json", "manual_wind.json")

DEFAULT_SETTINGS = {
    "sailchart_file": "SailChart J122 North.txt",
    "expedition_marks_file": "marks.xml",
    "polar_file": "J122.txt",
    "race_officer_api_base": "https://pro.pwllhelisailingclub.org",
    "race_officer_poll_enabled": False,
    "race_officer_poll_interval_seconds": 10,
    # Instruments: "expedition", "h5000" (B&G websocket) or "nmea0183" (TCP from a plotter).
    "instrument_source": "expedition",
    "h5000_host": "192.168.15.149",
    "h5000_port": 2053,
    "nmea_host": "192.168.15.166",
    "nmea_port": 10110,
}

# "manual": no instruments; TWD/TWS are typed in on the Wind & Course page.
INSTRUMENT_SOURCES = ("expedition", "h5000", "nmea0183", "manual")


def _port(value, default):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def app_file(name):
    """A file in the app folder."""
    return APP_DIR / name


def runtime_file(name):
    """A file in runtime/, creating the folder if needed."""
    folder = app_file(RUNTIME_DIR_NAME)
    folder.mkdir(exist_ok=True)
    return folder / name


def resolve_user_path(path_text):
    """A settings file path: relative paths are in the app folder; full Windows paths work too."""
    p = Path(path_text).expanduser()
    if not p.is_absolute():
        p = app_file(path_text)
    return p


# ---------------------------------------------------------------------------
# JSON files
# ---------------------------------------------------------------------------

def read_json(path, default=None):
    """The JSON in path, or default if it is missing or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_bytes_atomic(path, data):
    """Write a file so readers never see it half-written.

    The data goes to a temporary file that then replaces the target. Each write
    has its own temporary file, so two requests saving the same file at once
    cannot take each other's. On Windows the replace fails while another thread
    has the target open, so it is retried briefly before a direct write.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        for _ in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.02)
        path.write_bytes(data)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def write_text_atomic(path, text):
    write_bytes_atomic(path, text.encode("utf-8"))


def write_json(path, data):
    write_text_atomic(path, json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings():
    """settings.json merged over the defaults; unknown keys are ignored."""
    settings = dict(DEFAULT_SETTINGS)
    data = read_json(app_file("settings.json"), {})
    if isinstance(data, dict):
        for key, value in data.items():
            if key in settings:
                settings[key] = value
    settings["race_officer_poll_enabled"] = bool(settings.get("race_officer_poll_enabled", False))
    try:
        settings["race_officer_poll_interval_seconds"] = max(5, min(300, int(settings["race_officer_poll_interval_seconds"])))
    except Exception:
        settings["race_officer_poll_interval_seconds"] = 10
    if settings["instrument_source"] not in INSTRUMENT_SOURCES:
        settings["instrument_source"] = "expedition"
    for key in ("h5000_host", "nmea_host"):
        settings[key] = str(settings[key] or DEFAULT_SETTINGS[key]).strip()
    for key in ("h5000_port", "nmea_port"):
        settings[key] = _port(settings[key], DEFAULT_SETTINGS[key])
    return settings


def save_settings(settings):
    write_json(app_file("settings.json"), settings)


# ---------------------------------------------------------------------------
# Runtime folder
# ---------------------------------------------------------------------------

def prepare_runtime_dir():
    """Set up runtime/: move state files from the app folder, then seed from examples.

    v60 and earlier kept the state files in the app folder. marks.json and
    course.json start from the committed *.example.json files when there is
    nothing to move.
    """
    for name in RUNTIME_FILES:
        old = app_file(name)
        new = runtime_file(name)
        if old.exists() and not new.exists():
            shutil.move(str(old), str(new))
    for name in ("marks.json", "course.json"):
        live = runtime_file(name)
        example = app_file(name.replace(".json", ".example.json"))
        if not live.exists() and example.exists():
            shutil.copyfile(example, live)
