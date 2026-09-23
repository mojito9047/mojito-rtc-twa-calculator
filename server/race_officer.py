"""Race Officer import, auto-import polling and start bar data.

Reads the Pwllheli Race Officer app's public API (see its docs/PUBLIC_API.md and
docs/RACE_OFFICER_INTEGRATION.md here):

    /public/race/state          cheap change check (signature)
    /api/current_race_course    race, course as set and as sailed, marks

The course is imported into runtime/marks.json and runtime/course.json only
once the race officer has set one. Poll state, including the race and start
information for /api/race_start, is kept in runtime/race_officer_poll_state.json.
"""

import gzip
import json
import threading
import time
from datetime import datetime
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

from server import storage

bp = Blueprint("race_officer", __name__)

STATE_FILE = "race_officer_poll_state.json"
FULL_CHECK_SECONDS = 60     # full fetch at least this often, even if the state signature is unchanged

# The run to the finish of a shortened course ends at this mark. Rounding codes
# stored in course.json: P port, S starboard, V via a waypoint, F run to the finish.
FINISH_MARK_ID = "FIN"

_sync_lock = threading.Lock()
_poller_started = False


# ---------------------------------------------------------------------------
# Talking to the Race Officer app
# ---------------------------------------------------------------------------

def base_url():
    return str(storage.load_settings()["race_officer_api_base"]).strip().rstrip("/")


def get_json(url, timeout=12):
    """Fetch JSON from the Race Officer app.

    The public club URL may sit behind Cloudflare/proxies, so the request uses a
    browser-like user agent and accepts gzip responses.
    """
    req = Request(url, headers={
        "Accept": "application/json,text/plain,*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "Mozilla/5.0 Mojito-RTC/1.0",
    })
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace"))


def fetch_state_signature(base):
    """Cheap change check via `/public/race/state`; None if unavailable."""
    try:
        data = get_json(base + "/public/race/state", timeout=8)
        if isinstance(data, dict) and data.get("ok") and data.get("signature"):
            return str(data["signature"])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Reading the Race Officer reply
# ---------------------------------------------------------------------------

def clean_id(value, fallback):
    """A mark code as a course ID: upper-case letters and digits, up to 10."""
    raw = str(value if value not in (None, "") else fallback).strip().upper()
    safe = "".join(ch for ch in raw if ch.isalnum())
    return safe[:10] if safe else str(fallback)


def rounding_code(value):
    """Race Officer rounding -> course.json code: port P, starboard S, via V, else ""."""
    s = str(value or "").strip().lower()
    if s.startswith("port"):
        return "P"
    if s.startswith("starboard"):
        return "S"
    if s == "via":
        return "V"
    return ""


def _dict(value):
    return value if isinstance(value, dict) else {}


def race_info(payload):
    """The race facts the displays need from `/api/current_race_course`.

    Older Race Officer versions have no `course_set`; they are treated as set so
    the import keeps working as before.
    """
    race = _dict(payload.get("race"))
    course = _dict(payload.get("course"))
    shortened_at = _dict(course.get("shortened_at"))
    sailed = _dict(course.get("sailed"))
    return {
        "race_id": race.get("id"),
        "race_name": race.get("name") or "",
        "series_name": race.get("series_name") or "",
        "course_set": bool(race.get("course_set", True)),
        "course_no": course.get("course_no"),
        "course_label": str(course.get("name") or course.get("course_no") or ""),
        "sequence_text": sailed.get("sequence_text") or course.get("sequence_text") or "",
        "first_warning_time": race.get("first_warning_time") or race.get("start_time") or "",
        "first_start_time": race.get("first_start_time") or "",
        "postponed": bool(race.get("postponed", False)),
        "postponement_flag": race.get("postponement_flag") or "",
        "postponement_ends_at": race.get("postponement_ends_at") or "",
        "race_finished": bool(race.get("race_finished", False)),
        "shortened": bool(course.get("shortened", False)),
        "shortened_label": shortened_at.get("label") or "",
    }


def _mark_record(mark_id, mark):
    return {"id": mark_id, "name": str(mark.get("name") or mark.get("display") or mark_id),
            "lat": str(float(mark["lat"])), "lon": str(float(mark["lon"]))}


def parse_current_payload(payload):
    """Convert `/api/current_race_course` into (marks, route_ids, roundings, course_name).

    Marks: every Race Officer mark with a position (compound parent marks have
    none and are skipped; their corners are kept). Route: `course.sailed`, the
    course as the fleet is sailing it, which after a shortening is cut at the
    shorten mark and ends with a run to the middle of the finish line, added as
    mark FIN. Repeated marks are kept in the route.
    """
    if not isinstance(payload, dict) or not payload.get("ok", True):
        raise ValueError("Race Officer response was not OK")

    course = _dict(payload.get("course"))
    all_marks = _dict(payload.get("marks"))
    sailed = _dict(course.get("sailed"))

    marks, ids = [], set()
    for raw_key, mark in all_marks.items():
        if not isinstance(mark, dict) or mark.get("lat") is None or mark.get("lon") is None:
            continue
        mark_id = clean_id(mark.get("code") or raw_key, raw_key)
        if mark_id not in ids:
            ids.add(mark_id)
            marks.append(_mark_record(mark_id, mark))

    # Prefer the course as sailed; fall back to the course as set, then course marks.
    expanded = sailed.get("expanded_marks")
    if not isinstance(expanded, list) or len(expanded) < 2:
        expanded = course.get("expanded_marks")
    if not isinstance(expanded, list) or len(expanded) < 2:
        expanded = course.get("marks") if isinstance(course.get("marks"), list) else []

    route, roundings = [], {}
    for idx, mark in enumerate(expanded):
        if not isinstance(mark, dict):
            continue
        mark_id = clean_id(mark.get("code") or mark.get("display") or mark.get("sequence_mark"), f"M{idx + 1}")
        # A route mark missing from the marks dictionary is added from its own position.
        if mark_id not in ids and mark.get("lat") is not None and mark.get("lon") is not None:
            ids.add(mark_id)
            marks.append(_mark_record(mark_id, mark))
        route.append(mark_id)

        # The rounding belongs to the leg ending at this mark; the first mark is the start.
        if len(route) >= 2:
            code = rounding_code("via" if mark.get("waypoint") else (mark.get("rounding") or mark.get("to_rounding")))
            if code:
                roundings[f"{len(route) - 2}:{route[-2]}-{route[-1]}"] = code

    # A shortened course ends with a run to the middle of the finish line.
    finish = sailed.get("finish") if isinstance(sailed.get("finish"), dict) else None
    if finish and finish.get("lat") is not None and finish.get("lon") is not None and route:
        marks = [m for m in marks if m["id"] != FINISH_MARK_ID]
        marks.append({"id": FINISH_MARK_ID, "name": str(finish.get("description") or "Finish"),
                      "lat": str(float(finish["lat"])), "lon": str(float(finish["lon"]))})
        route.append(FINISH_MARK_ID)
        roundings[f"{len(route) - 2}:{route[-2]}-{route[-1]}"] = "F"

    if len(route) < 2:
        raise ValueError("Race Officer current course did not contain at least two route marks")
    if len(marks) < 2:
        raise ValueError("Race Officer current course did not contain at least two usable mark positions")

    race = _dict(payload.get("race"))
    course_name = str(course.get("name") or course.get("course_no") or race.get("name") or "Current race course")
    return marks, route, roundings, course_name


def course_signature(route, roundings, course_name, marks=None, race_id=None):
    """What must change for a course to be re-imported.

    The race id is included so the next race sailed over the same course is
    still imported, which starts it at leg 0. Route mark positions are included
    so a re-laid mark is picked up.
    """
    route_marks = {m["id"]: [m["lat"], m["lon"]] for m in marks or [] if m["id"] in route}
    return json.dumps({"race_id": race_id, "course_name": course_name, "route": route,
                       "roundings": roundings, "route_marks": route_marks},
                      sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Poll state and local course files
# ---------------------------------------------------------------------------

def read_state():
    state = storage.read_json(storage.runtime_file(STATE_FILE), {})
    return state if isinstance(state, dict) else {}


def update_state(updates):
    """Merge updates into the saved poll state.

    Merging (rather than overwriting) matters on errors: losing the saved course
    signature would make the next good poll re-import and reset the current leg.
    """
    state = read_state()
    state.update(updates)
    storage.write_json(storage.runtime_file(STATE_FILE), state)
    return state


def record_error(message):
    update_state({"last_check": time.time(), "error": str(message)})


def keep_current_leg(old_route, new_route):
    """Current leg to use after an import.

    A shortening keeps the route up to the shorten mark, so a boat already part
    way round keeps its leg. Any other change starts again at leg 0.
    """
    try:
        current = int(storage.read_json(storage.runtime_file("current_leg.json"), {}).get("current_leg", 0))
    except Exception:
        return 0
    n = current + 2   # marks that define legs 0..current
    if current >= 0 and len(new_route) >= n and old_route[:n] == new_route[:n]:
        return current
    return 0


def write_course(marks, route, roundings, same_race=True):
    old = storage.read_json(storage.runtime_file("course.json"), {})
    old_route = str(old.get("course", "")).split() if isinstance(old, dict) else []
    leg = keep_current_leg(old_route, route) if same_race else 0
    storage.write_json(storage.runtime_file("marks.json"), marks)
    storage.write_json(storage.runtime_file("course.json"), {"course": " ".join(route), "roundings": roundings})
    storage.write_json(storage.runtime_file("current_leg.json"), {"current_leg": leg})


def clear_course():
    """Empty the active course while the race officer has not set one. Marks are kept."""
    storage.write_json(storage.runtime_file("course.json"), {"course": "", "roundings": {}})
    storage.write_json(storage.runtime_file("current_leg.json"), {"current_leg": 0})


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def import_current_if_changed(force=False):
    """Poll Race Officer and import only when the course changes.

    1. Poll `/public/race/state`. If its signature has not moved (and a full
       check was done in the last minute) there is nothing to do.
    2. Otherwise fetch `/api/current_race_course` and save the race/start info.
       With no course set, clear the showing course once for that race.
       Otherwise import `course.sailed` when its signature changed.
    force imports even if unchanged.
    """
    with _sync_lock:
        base = base_url()
        state = read_state()
        now = time.time()

        ro_state_sig = fetch_state_signature(base)
        recently_full = (now - float(state.get("last_full_check") or 0)) < FULL_CHECK_SECONDS
        if (not force and ro_state_sig and ro_state_sig == state.get("ro_state_signature")
                and recently_full and state.get("base") == base and not state.get("error")):
            update_state({"last_check": now})
            return {
                "changed": False,
                "base": base,
                "course_name": state.get("course_name"),
                "marks_count": state.get("marks_count", 0),
                "course": state.get("course", ""),
                "roundings": state.get("roundings", {}),
                "signature": state.get("signature"),
                "race": state.get("race", {}),
                "course_set": state.get("race", {}).get("course_set", True),
            }

        payload = get_json(base + "/api/current_race_course")
        race = race_info(payload)
        common = {"base": base, "last_check": now, "last_full_check": now,
                  "ro_state_signature": ro_state_sig, "race": race, "error": None}

        if not race["course_set"]:
            # Do not import the placeholder course a new race is created with,
            # and clear whatever course is showing (the placeholder, or the
            # previous race's course) once per race. A course typed in by hand
            # while waiting is left alone.
            cleared = False
            if state.get("course_cleared_for_race") != race["race_id"]:
                clear_course()
                cleared = True
            update_state({
                **common,
                "changed": cleared,
                "course_pending": True,
                "course_cleared_for_race": race["race_id"],
                # Forget the imported course so setting it (even to the same course) imports it.
                "signature": None if cleared else state.get("signature"),
                "course": "" if cleared else state.get("course", ""),
            })
            return {"changed": cleared, "base": base, "course_name": None, "marks_count": 0, "course": "",
                    "roundings": {}, "signature": state.get("signature"), "race": race, "course_set": False}

        marks, route, roundings, course_name = parse_current_payload(payload)
        signature = course_signature(route, roundings, course_name, marks, race["race_id"])
        changed = force or signature != state.get("signature")
        if changed:
            same_race = (state.get("race") or {}).get("race_id") == race["race_id"]
            write_course(marks, route, roundings, same_race)

        update_state({
            **common,
            "signature": signature,
            "last_import": now if changed else state.get("last_import"),
            "changed": changed,
            "course_pending": False,
            "course_name": course_name,
            "course": " ".join(route),
            "marks_count": len(marks),
            "roundings": roundings,
        })
        return {"changed": changed, "base": base, "course_name": course_name, "marks_count": len(marks),
                "course": " ".join(route), "roundings": roundings, "signature": signature,
                "race": race, "course_set": True}


def _poller_loop():
    """Background server-side auto-import loop."""
    while True:
        try:
            settings = storage.load_settings()
            if settings["race_officer_poll_enabled"]:
                try:
                    import_current_if_changed(force=False)
                except Exception as e:
                    record_error(e)
            time.sleep(settings["race_officer_poll_interval_seconds"])
        except Exception:
            time.sleep(10)


def start_poller():
    """Start the Race Officer poller thread (once per process)."""
    global _poller_started
    if _poller_started:
        return
    _poller_started = True
    threading.Thread(target=_poller_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _check_base(base):
    if not (base.startswith("http://") or base.startswith("https://")):
        raise ValueError("Base URL must start with http:// or https://")


@bp.route("/api/race_officer/base", methods=["GET", "POST"])
def api_race_officer_base():
    settings = storage.load_settings()
    if request.method == "GET":
        return jsonify({"ok": True, "base": settings["race_officer_api_base"], "error": None})
    try:
        data = request.get_json(force=True) if request.data else {}
        base = str(data.get("base", "")).strip().rstrip("/")
        if not base:
            raise ValueError("Base URL is blank")
        _check_base(base)
        settings["race_officer_api_base"] = base
        storage.save_settings(settings)
        return jsonify({"ok": True, "base": base, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "base": None, "error": str(e)}), 400


_EMPTY_RESULT = {"base": None, "course_name": None, "marks_count": 0, "course": "", "roundings": {}}


@bp.route("/api/race_officer/current_preview")
def api_race_officer_current_preview():
    """Read the current Race Officer course without changing anything here."""
    try:
        base = base_url()
        payload = get_json(base + "/api/current_race_course")
        race = race_info(payload)
        marks, route, roundings, course_name = parse_current_payload(payload)
        return jsonify({"ok": True, "base": base, "course_name": course_name, "marks_count": len(marks),
                        "course": " ".join(route), "roundings": roundings, "race": race,
                        "course_set": race["course_set"], "error": None})
    except Exception as e:
        return jsonify({"ok": False, **_EMPTY_RESULT, "error": str(e)}), 400


@bp.route("/api/race_officer/import_current", methods=["POST"])
def api_race_officer_import_current():
    """Import now, even if unchanged. Refused while no course is set."""
    try:
        result = import_current_if_changed(force=True)
        if not result["course_set"]:
            name = result["race"].get("race_name") or "the current race"
            raise ValueError(f"The race officer has not set a course for {name} yet")
        return jsonify({"ok": True, **result, "error": None})
    except Exception as e:
        return jsonify({"ok": False, **_EMPTY_RESULT, "error": str(e)}), 400


@bp.route("/api/race_officer/poll_status")
def api_race_officer_poll_status():
    try:
        settings = storage.load_settings()
        return jsonify({"ok": True, "enabled": settings["race_officer_poll_enabled"],
                        "interval_seconds": settings["race_officer_poll_interval_seconds"],
                        "state": read_state(), "error": None})
    except Exception as e:
        return jsonify({"ok": False, "enabled": False, "interval_seconds": 10, "state": {}, "error": str(e)}), 400


@bp.route("/api/race_officer/poll_config", methods=["POST"])
def api_race_officer_poll_config():
    """Turn auto-import on or off; a first check runs straight away when turned on."""
    try:
        data = request.get_json(force=True) if request.data else {}
        settings = storage.load_settings()
        enabled = bool(data.get("enabled", False))
        interval = max(5, min(300, int(data.get("interval_seconds", settings["race_officer_poll_interval_seconds"]))))
        base = str(data.get("base", "") or "").strip().rstrip("/")
        if base:
            _check_base(base)
            settings["race_officer_api_base"] = base
        settings["race_officer_poll_enabled"] = enabled
        settings["race_officer_poll_interval_seconds"] = interval
        storage.save_settings(settings)

        initial_check = initial_error = None
        if enabled:
            start_poller()
            try:
                initial_check = import_current_if_changed(force=False)
            except Exception as e:
                initial_error = str(e)
                try:
                    record_error(initial_error)
                except Exception:
                    pass
        return jsonify({"ok": True, "enabled": enabled, "interval_seconds": interval,
                        "initial_check": initial_check, "initial_error": initial_error, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "enabled": False, "interval_seconds": 10, "error": str(e)}), 400


@bp.route("/api/race_officer/poll_once", methods=["POST"])
def api_race_officer_poll_once():
    try:
        return jsonify({"ok": True, **import_current_if_changed(force=False), "error": None})
    except Exception as e:
        record_error(e)
        return jsonify({"ok": False, "changed": False, "error": str(e)}), 400


def parse_local_time(text):
    """Race Officer times are ISO local time with no zone; returns epoch seconds or None."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text)).timestamp()
    except Exception:
        return None


@bp.route("/api/race_start")
def api_race_start():
    """Start countdown and race status for the start bar.

    Seconds are worked out here so the legacy MFD page only has to count down.
    `live` is false when polling is off or the last good check is stale, in which
    case the displays hide the start bar rather than show old information.
    """
    settings = storage.load_settings()
    state = read_state()
    race = state.get("race") or {}
    now = time.time()
    enabled = settings["race_officer_poll_enabled"]
    interval = settings["race_officer_poll_interval_seconds"]
    last_good = float(state.get("last_full_check") or 0)
    if state.get("last_check") and not state.get("error"):
        last_good = max(last_good, float(state.get("last_check") or 0))
    age = now - last_good if last_good else None
    live = bool(enabled and race and age is not None and age < max(90, interval * 3 + 30))

    start_ts = parse_local_time(race.get("first_start_time"))
    ends_ts = parse_local_time(race.get("postponement_ends_at"))
    return jsonify({
        "ok": True,
        "live": live,
        "enabled": enabled,
        "age_seconds": age,
        "error": state.get("error"),
        "server_now": now,
        "race": race,
        "seconds_to_start": (start_ts - now) if start_ts else None,
        "start_clock": time.strftime("%H:%M:%S", time.localtime(start_ts)) if start_ts else "",
        "postponement_ends_clock": time.strftime("%H:%M", time.localtime(ends_ts)) if ends_ts else "",
    })
