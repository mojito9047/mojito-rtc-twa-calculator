"""Instruments: live channels, boat position and wind history.

Four sources, chosen on the Settings page (`instrument_source`):

    expedition   Expedition on this PC, read through its DLL (expedition_dll)
    h5000        the B&G H5000 websocket (h5000)
    nmea0183     NMEA 0183 over TCP from a plotter (nmea0183)
    manual       no instruments: TWD and TWS typed in on the Wind & Course
                 page (runtime/manual_wind.json); nothing else is available

read_var() reads a channel (expedition_dll.Var) from whichever is selected;
everything else (wind history, TWD, position, the pages) goes through it.
Directions are degrees true and speeds knots from every source.

A server thread samples TWD/TWS once a second into runtime/wind_history.jsonl.
The Course legs page also posts the TWD/TWS it is showing to /api/display_wind;
/api/wind (which every page reads) and /api/twd fall back to that when the
source's TWD is unavailable, so the MFD page does not drop to 0°.
"""

import json
import threading
import time

from flask import Blueprint, jsonify, request

from server import storage
from server.expedition_dll import ExpeditionDLL, Var
from server.h5000 import H5000Source
from server.nmea0183 import Nmea0183Source

bp = Blueprint("instruments", __name__)

WIND_HISTORY_SECONDS = 60 * 60      # keep one hour
WIND_HISTORY_MAX_SAMPLES = 5000

SOURCE_LABELS = {"expedition": "Expedition", "h5000": "B&G H5000", "nmea0183": "NMEA 0183",
                 "manual": "Manual wind"}

_expedition = None
last_error = None                   # why the DLL could not be loaded, if it could not

_wind_lock = threading.Lock()
_wind_sampler_started = False

_live = None                        # the running network source (H5000 or NMEA), if one is selected
_live_key = None                    # (source, host, port) it was started for
_live_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Choosing the source
# ---------------------------------------------------------------------------

def selected_source():
    """(source name, running LiveSource or None). Starts/stops network readers to match settings."""
    global _live, _live_key
    settings = storage.load_settings()
    kind = settings["instrument_source"]
    if kind == "h5000":
        key = (kind, settings["h5000_host"], settings["h5000_port"])
    elif kind == "nmea0183":
        key = (kind, settings["nmea_host"], settings["nmea_port"])
    else:
        key = None
    with _live_lock:
        if key != _live_key:
            if _live:
                _live.stop()
            _live = None
            if key:
                _live = (H5000Source if kind == "h5000" else Nmea0183Source)(key[1], key[2])
                _live.start()
            _live_key = key
        return kind, _live


def stop_live_source():
    """Stop the network reader (used by tests and on shutdown)."""
    global _live, _live_key
    with _live_lock:
        if _live:
            _live.stop()
        _live, _live_key = None, None


def source_status():
    kind, live = selected_source()
    if live:
        status = live.status()
    elif kind == "manual":
        manual = read_manual_wind()
        entered = manual["twd"] is not None and manual["tws"] is not None
        status = {"source": "Manual wind", "connected": entered,
                  "error": None if entered else "Enter TWD and TWS on the Wind & Course page"}
    else:
        exp = connect_expedition()
        status = {"source": "Expedition", "connected": exp is not None, "error": last_error}
    status["kind"] = kind
    status["label"] = SOURCE_LABELS.get(kind, kind)
    return status


def read_var(var):
    """Read one channel from the selected source: (value, age, error). error is None on success."""
    kind, live = selected_source()
    if live:
        return live.read(var)
    if kind == "manual":
        return read_manual_var(var)
    return read_expedition_var(var)


def read_manual_var(var):
    """The manual source: TWD and TWS as typed in; no other channel."""
    if var not in (Var.Twd, Var.Tws):
        return None, None, "No instruments (manual wind)"
    manual = read_manual_wind()
    value = manual["twd"] if var == Var.Twd else manual["tws"]
    if value is None:
        return None, None, "Manual wind not entered yet"
    return value, max(0.0, time.time() - manual["updated"]) if manual["updated"] else None, None


# ---------------------------------------------------------------------------
# Expedition DLL access
# ---------------------------------------------------------------------------

def connect_expedition():
    """Load the Expedition DLL once; None (with last_error set) if unavailable."""
    global _expedition, last_error
    if _expedition is not None:
        return _expedition
    try:
        _expedition = ExpeditionDLL.from_default_location()
        last_error = None
        return _expedition
    except Exception as e:
        last_error = str(e)
        return None


def read_expedition_var(var):
    """Read one Expedition channel: (value, age, error). error is None on success.

    The DLL's age output always equals the channel number, so it means nothing.
    """
    exp = connect_expedition()
    if exp is None:
        return None, None, last_error
    try:
        value, age = exp.get_var(var)
        if value is None:
            return None, age, "Expedition returned invalid/no data for this variable."
        return value, age, None
    except Exception as e:
        return None, None, str(e)


# ---------------------------------------------------------------------------
# Wind history
# ---------------------------------------------------------------------------

def _read_wind_history(now, keep_seconds=WIND_HISTORY_SECONDS):
    """Samples from the last keep_seconds. Call with _wind_lock held."""
    path = storage.runtime_file("wind_history.jsonl")
    samples = []
    if not path.exists():
        return samples
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            t = float(item.get("t", 0))
            if now - t <= keep_seconds:
                samples.append({"t": t, "twd": float(item.get("twd", 0)) % 360,
                                "tws": max(0.0, float(item.get("tws", 0)))})
    except Exception:
        # An unreadable file is treated as empty rather than erased here.
        return []
    return samples


def _write_wind_history(samples):
    """Call with _wind_lock held."""
    data = "\n".join(json.dumps(x) for x in samples[-WIND_HISTORY_MAX_SAMPLES:])
    storage.write_text_atomic(storage.runtime_file("wind_history.jsonl"), data + "\n" if data else "")


def append_wind_history_sample():
    """Add the current TWD/TWS, at most once a second, dropping samples over an hour old.

    Nothing is recorded with manual wind: the history is of the instruments.
    """
    if storage.load_settings()["instrument_source"] == "manual":
        return
    now = time.time()
    twd, _, err1 = read_var(Var.Twd)
    tws, _, err2 = read_var(Var.Tws)
    if err1 or err2 or not isinstance(twd, (int, float)) or not isinstance(tws, (int, float)):
        return
    sample = {"t": now, "twd": float(twd) % 360, "tws": max(0.0, float(tws))}
    with _wind_lock:
        samples = _read_wind_history(now)
        if not samples or now - float(samples[-1].get("t", 0)) >= 0.9:
            samples.append(sample)
        try:
            _write_wind_history(samples)
        except Exception:
            pass


def start_wind_sampler():
    """Start the once-a-second wind sampler thread (once per process)."""
    global _wind_sampler_started
    if _wind_sampler_started:
        return
    _wind_sampler_started = True

    def loop():
        while True:
            try:
                append_wind_history_sample()
            except Exception:
                pass
            time.sleep(1)

    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Displayed wind (fallback TWD)
# ---------------------------------------------------------------------------

def read_display_wind():
    """TWD/TWS last posted by the Course legs page, with its age in seconds."""
    state = {"twd": 225.0, "tws": None, "source": "default", "updated": 0, "age_seconds": None}
    data = storage.read_json(storage.runtime_file("display_wind.json"), {})
    if isinstance(data, dict):
        state.update(data)
    try:
        updated = float(state.get("updated") or 0)
        state["age_seconds"] = max(0, time.time() - updated) if updated else None
    except Exception:
        state["age_seconds"] = None
    return state


# ---------------------------------------------------------------------------
# The wind the displays use
# ---------------------------------------------------------------------------

MAX_MANUAL_TWS = 80.0


def read_manual_wind():
    """The saved manual TWD/TWS, {"twd", "tws", "updated"} (None if never entered)."""
    data = storage.read_json(storage.runtime_file("manual_wind.json"), {})
    data = data if isinstance(data, dict) else {}
    twd, tws = data.get("twd"), data.get("tws")
    return {"twd": float(twd) % 360 if isinstance(twd, (int, float)) else None,
            "tws": max(0.0, float(tws)) if isinstance(tws, (int, float)) else None,
            "updated": data.get("updated") or 0}


def current_wind():
    """The TWD/TWS every display should use now, and where it came from.

    source is the instrument source ("expedition", "h5000", "nmea0183",
    "manual"), or "display_fallback" for a TWD taken from the Course legs page
    because the source had none.
    """
    kind = storage.load_settings()["instrument_source"]
    twd, _, twd_error = read_var(Var.Twd)
    tws, _, tws_error = read_var(Var.Tws)
    source, warning = kind, None
    if twd_error and kind != "manual":
        fallback = read_display_wind().get("twd")
        if isinstance(fallback, (int, float)):
            twd, source, warning = fallback, "display_fallback", twd_error
    ok = twd is not None and tws is not None
    return {"ok": ok, "manual": kind == "manual", "source": source, "twd": twd, "tws": tws,
            "warning": warning, "error": None if ok else (twd_error or tws_error)}


@bp.route("/api/wind", methods=["GET", "POST"])
def api_wind():
    """GET: the wind to use (see current_wind) and the saved manual values.
    POST: the manual wind, {"twd": 0-360, "tws": 0-80} (either or both); it is
    used while the instrument source is "manual"."""
    if request.method == "POST":
        try:
            data = request.get_json(force=True) if request.data else {}
            saved = read_manual_wind()
            if data.get("twd") is not None:
                twd = float(data["twd"])
                if not 0 <= twd <= 360:
                    raise ValueError("TWD must be 0-360")
                saved["twd"] = twd % 360
            if data.get("tws") is not None:
                tws = float(data["tws"])
                if not 0 <= tws <= MAX_MANUAL_TWS:
                    raise ValueError(f"TWS must be 0-{MAX_MANUAL_TWS:.0f} kt")
                saved["tws"] = tws
            saved["updated"] = time.time()
            storage.write_json(storage.runtime_file("manual_wind.json"), saved)
        except (TypeError, ValueError) as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    manual = read_manual_wind()
    return jsonify({**current_wind(), "manual_wind": {"twd": manual["twd"], "tws": manual["tws"]}})

@bp.route("/api/display_wind", methods=["GET", "POST"])
def api_display_wind():
    if request.method == "GET":
        return jsonify({"ok": True, **read_display_wind(), "error": None})
    try:
        data = request.get_json(force=True) if request.data else {}
        state = read_display_wind()
        if data.get("twd") is not None:
            state["twd"] = float(data.get("twd")) % 360
        if data.get("tws") is not None:
            state["tws"] = max(0.0, float(data.get("tws")))
        state["source"] = str(data.get("source") or "course_legs_page")
        state["updated"] = time.time()
        storage.write_json(storage.runtime_file("display_wind.json"), {
            "twd": state["twd"], "tws": state["tws"], "source": state["source"], "updated": state["updated"]})
        return jsonify({"ok": True, **state, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/api/twd")
def api_twd():
    value, age, error = read_var(Var.Twd)
    if not error:
        return jsonify({"ok": True, "twd": value, "age": age,
                        "source": storage.load_settings()["instrument_source"], "error": None})
    fallback = read_display_wind()
    twd = fallback.get("twd")
    if isinstance(twd, (int, float)):
        return jsonify({"ok": True, "twd": twd, "age": fallback.get("age_seconds"),
                        "source": fallback.get("source", "display_fallback"), "warning": error, "error": None})
    return jsonify({"ok": False, "twd": None, "age": age, "error": error}), 500


@bp.route("/api/expedition")
def api_expedition():
    """Instrument values. ok is false if any channel errors; valid channels are still returned."""
    output, errors, ages = {}, {}, {}
    for name in ["Bsp", "Twd", "Tws", "Hdg", "Cog", "Sog"]:
        value, age, error = read_var(getattr(Var, name))
        output[name] = value
        ages[name] = age
        if error:
            errors[name] = error
    return jsonify({"ok": len(errors) == 0, "data": output, "ages": ages, "errors": errors})


@bp.route("/api/position")
def api_position():
    """Boat position from Expedition, decimal degrees. ok is false with no GPS fix."""
    lat, _, lat_error = read_var(Var.Lat)
    lon, _, lon_error = read_var(Var.Lon)
    valid = (lat_error is None and lon_error is None and lat is not None and lon is not None
             and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0))
    return jsonify({
        "ok": bool(valid),
        "lat": lat if valid else None,
        "lon": lon if valid else None,
        "error": None if valid else (lat_error or lon_error or "No position from Expedition"),
    })


@bp.route("/api/wind_history")
def api_wind_history():
    """Samples for the last `minutes` (1-60, default 5). The sampler thread is the only writer."""
    start_wind_sampler()
    now = time.time()
    try:
        minutes = max(1, min(60, float(request.args.get("minutes", "5"))))
    except Exception:
        minutes = 5
    with _wind_lock:
        samples_all = _read_wind_history(now)
    since = now - minutes * 60
    return jsonify({
        "ok": True,
        "server_now": now,
        "minutes": minutes,
        "samples": [x for x in samples_all if float(x.get("t", 0)) >= since],
        "current": samples_all[-1] if samples_all else None,
        "error": None,
    })


@bp.route("/api/instruments")
def api_instruments():
    """The selected instrument source and whether it is delivering data."""
    return jsonify({"ok": True, **source_status()})


@bp.route("/api/health")
def api_health():
    status = source_status()
    return jsonify({"ok": bool(status["connected"]), "source": status["kind"], "connected": bool(status["connected"]),
                    "expedition_connected": _expedition is not None, "error": status.get("error")})
