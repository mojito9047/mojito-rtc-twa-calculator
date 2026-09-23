"""The course, marks and configuration files the pages read and edit.

Course, current leg and marks are runtime state (runtime/*.json). The sail
chart, polar and Expedition marks XML are configuration files chosen in
settings.json. Leg calculations are not done here: the pages do them in
static/legs.js.
"""

import csv
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from flask import Blueprint, jsonify, request

from server import instruments, storage

bp = Blueprint("course_data", __name__)

# Rounding codes kept in course.json: P/S from the course editor; V (via a
# waypoint) and F (run to the finish) from a Race Officer import.
ROUNDING_CODES = ("P", "S", "V", "F", "")

# Shown until a course is saved (a fresh install seeds course.example.json instead).
DEFAULT_COURSE = {"course": "B F S E Q",
                  "roundings": {"0:B-F": "P", "1:F-S": "P", "2:S-E": "P", "3:E-Q": "P"}}


# ---------------------------------------------------------------------------
# Course and current leg
# ---------------------------------------------------------------------------

@bp.route("/api/course", methods=["GET", "POST"])
def api_course():
    path = storage.runtime_file("course.json")
    if request.method == "GET":
        try:
            course = dict(DEFAULT_COURSE)
            if path.exists():
                data = storage.read_json(path)
                if not isinstance(data, dict):
                    raise ValueError("course.json is not readable")
                roundings = data.get("roundings", {})
                course = {"course": str(data.get("course", DEFAULT_COURSE["course"])),
                          "roundings": roundings if isinstance(roundings, dict) else {}}
            return jsonify({"ok": True, **course, "error": None})
        except Exception as e:
            return jsonify({"ok": False, "course": DEFAULT_COURSE["course"], "roundings": {}, "error": str(e)}), 500

    try:
        data = request.get_json(force=True)
        course = str(data.get("course", "")).strip()
        roundings = data.get("roundings", {})
        if not isinstance(roundings, dict):
            roundings = {}
        clean = {str(k): str(v).upper() for k, v in roundings.items() if str(v).upper() in ROUNDING_CODES}
        storage.write_json(path, {"course": course, "roundings": clean})
        return jsonify({"ok": True, "course": course, "roundings": clean, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "course": "", "roundings": {}, "error": str(e)}), 400


@bp.route("/api/current_leg", methods=["GET", "POST"])
def api_current_leg():
    path = storage.runtime_file("current_leg.json")
    if request.method == "GET":
        try:
            leg = 0
            if path.exists():
                leg = max(0, int(storage.read_json(path, {}).get("current_leg", 0)))
            return jsonify({"ok": True, "current_leg": leg, "error": None})
        except Exception as e:
            return jsonify({"ok": False, "current_leg": 0, "error": str(e)}), 500

    try:
        leg = max(0, int(request.get_json(force=True).get("current_leg", 0)))
        storage.write_json(path, {"current_leg": leg})
        return jsonify({"ok": True, "current_leg": leg, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "current_leg": 0, "error": str(e)}), 400


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

@bp.route("/api/marks", methods=["GET", "POST"])
def api_marks():
    path = storage.runtime_file("marks.json")
    if request.method == "GET":
        marks = storage.read_json(path)
        if not isinstance(marks, list):
            return jsonify({"ok": False, "marks": [], "error": f"{path.name} is missing or unreadable"}), 500
        return jsonify({"ok": True, "marks": marks, "error": None})

    try:
        marks = request.get_json(force=True).get("marks", [])
        if not isinstance(marks, list):
            raise ValueError("marks must be a list")
        clean, seen = [], set()
        for m in marks:
            mark_id = str(m.get("id", "")).strip().upper()
            if not mark_id:
                continue
            if mark_id in seen:
                raise ValueError(f"Duplicate mark ID: {mark_id}")
            seen.add(mark_id)
            name = str(m.get("name", "")).strip()
            clean.append({"id": mark_id, "name": name or mark_id,
                          "lat": str(m.get("lat", "")).strip(), "lon": str(m.get("lon", "")).strip()})
        if len(clean) < 2:
            raise ValueError("At least two marks are required")
        storage.write_json(path, clean)
        return jsonify({"ok": True, "marks": clean, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "marks": [], "error": str(e)}), 400


def _dec_to_dm(value, is_lon=False):
    """52.878 -> "52° 52.70N" (degrees and decimal minutes, as the mark editor shows)."""
    value = float(value)
    hemi = ("E" if value >= 0 else "W") if is_lon else ("N" if value >= 0 else "S")
    deg = int(abs(value))
    minutes = (abs(value) - deg) * 60
    return f"{deg:0{3 if is_lon else 2}d}° {minutes:05.2f}{hemi}"


def _unique_id(base, used):
    """base, or base2, base3... (kept to 12 characters) if already in used (upper-case)."""
    candidate, n = base, 2
    while candidate.upper() in used:
        suffix = str(n)
        candidate = base[: max(1, 12 - len(suffix))] + suffix
        n += 1
    return candidate


@bp.route("/api/expedition_marks/groups")
def api_expedition_marks_groups():
    xml_path = storage.resolve_user_path(storage.load_settings()["expedition_marks_file"])
    try:
        if not xml_path.exists():
            raise FileNotFoundError(f"{xml_path.name} was not found")
        counter = Counter(mark.get("group", "") or "(no group)" for mark in ET.parse(xml_path).getroot().findall(".//mark"))
        groups = [{"name": name, "count": count}
                  for name, count in sorted(counter.items(), key=lambda x: (x[0] == "(no group)", x[0].lower()))]
        return jsonify({"ok": True, "groups": groups, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "groups": [], "error": str(e)}), 500


@bp.route("/api/expedition_marks/import", methods=["POST"])
def api_expedition_marks_import():
    """Import one group from the Expedition marks XML, replacing or adding to the marks."""
    xml_path = storage.resolve_user_path(storage.load_settings()["expedition_marks_file"])
    marks_path = storage.runtime_file("marks.json")
    try:
        data = request.get_json(force=True)
        group = data.get("group", "")
        replace = bool(data.get("replace", False))
        prefix = str(data.get("prefix", "") or "").strip().upper()
        group_match = "" if group == "(no group)" else group

        imported, used = [], set()
        for mark in ET.parse(xml_path).getroot().findall(".//mark"):
            if (mark.get("group", "") or "") != group_match:
                continue
            name = mark.get("name", "").strip() or mark.get("id", "").strip()
            lat, lon = mark.get("lat", "").strip(), mark.get("lon", "").strip()
            if not lat or not lon:
                continue
            # The Expedition name becomes the ID, made short and safe for courses.
            base_id = prefix + "".join(ch for ch in name.upper() if ch.isalnum())[:10]
            if not base_id:
                base_id = prefix + str(mark.get("id", "")).strip()
            mark_id = _unique_id(base_id, used)
            used.add(mark_id.upper())
            imported.append({"id": mark_id, "name": name,
                             "lat": _dec_to_dm(float(lat), False), "lon": _dec_to_dm(float(lon), True),
                             "expedition_id": mark.get("id", ""), "expedition_group": group_match})
        if not imported:
            raise ValueError(f"No marks found in group {group!r}")

        if replace:
            merged = imported
        else:
            existing = storage.read_json(marks_path, [])
            if not isinstance(existing, list):
                existing = []
            existing_ids = {str(m.get("id", "")).upper() for m in existing}
            merged = list(existing)
            for m in imported:
                m["id"] = _unique_id(m["id"], existing_ids)
                existing_ids.add(m["id"].upper())
                merged.append(m)

        storage.write_json(marks_path, merged)
        return jsonify({"ok": True, "imported_count": len(imported), "marks": merged, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "imported_count": 0, "marks": [], "error": str(e)}), 400


# ---------------------------------------------------------------------------
# Sail chart and polar
# ---------------------------------------------------------------------------

@bp.route("/api/sailchart")
def api_sailchart():
    """Tab-separated sail chart: TWA headings across, TWS down, a sail in each cell."""
    path = storage.resolve_user_path(storage.load_settings()["sailchart_file"])
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines(), delimiter="\t"))
        if not rows:
            raise ValueError(f"{path.name} is empty")
        twas = [int(float(x)) for x in rows[0][1:] if str(x).strip()]
        chart_rows = []
        for row in rows[1:]:
            if not row or not str(row[0]).strip():
                continue
            sails = row[1:] + [""] * (len(twas) - len(row[1:]))
            chart_rows.append({"tws": float(row[0]), "sails": sails[:len(twas)]})
        return jsonify({"ok": True, "twas": twas, "rows": chart_rows, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "twas": [], "rows": [], "error": str(e)}), 500


@bp.route("/api/polar")
def api_polar():
    """Expedition-style polar: TWS, then TWA / boat speed pairs, one wind speed per line."""
    path = storage.resolve_user_path(storage.load_settings().get("polar_file", "J122.txt"))
    try:
        rows = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.replace(",", "\t").split()
            if len(parts) < 3:
                continue
            values = [float(x) for x in parts]
            points = [{"twa": values[i], "bsp": values[i + 1]} for i in range(1, len(values) - 1, 2)]
            if points:
                rows.append({"tws": values[0], "points": points})
        if not rows:
            raise ValueError(f"No polar data found in {path.name}")
        rows.sort(key=lambda r: r["tws"])
        return jsonify({"ok": True, "rows": rows, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "rows": [], "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Settings and files
# ---------------------------------------------------------------------------

@bp.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"ok": True, "settings": storage.load_settings(), "error": None})
    try:
        data = request.get_json(force=True)
        current = storage.load_settings()

        def text(key):
            return str(data.get(key, current[key])).strip()

        updated = {
            "sailchart_file": text("sailchart_file"),
            "expedition_marks_file": text("expedition_marks_file"),
            "polar_file": text("polar_file"),
            "race_officer_api_base": text("race_officer_api_base").rstrip("/"),
            "race_officer_poll_enabled": bool(data.get("race_officer_poll_enabled", current["race_officer_poll_enabled"])),
            "race_officer_poll_interval_seconds": max(5, min(300, int(data.get(
                "race_officer_poll_interval_seconds", current["race_officer_poll_interval_seconds"])))),
        }
        for key, label in [("sailchart_file", "Sail chart file"), ("expedition_marks_file", "Expedition marks file"),
                           ("polar_file", "Polar file"), ("race_officer_api_base", "Race Officer API base URL")]:
            if not updated[key]:
                raise ValueError(f"{label} cannot be blank")
        if not updated["race_officer_api_base"].startswith(("http://", "https://")):
            raise ValueError("Race Officer address must start with http:// or https://")

        # Instrument source and the network addresses of the H5000 and plotter.
        source = text("instrument_source")
        if source not in storage.INSTRUMENT_SOURCES:
            raise ValueError("Instrument source must be expedition, h5000, nmea0183 or manual")
        updated["instrument_source"] = source
        if source == "manual" and current["instrument_source"] != "manual":
            _seed_manual_wind()
        for host_key, port_key, label in [("h5000_host", "h5000_port", "H5000"), ("nmea_host", "nmea_port", "NMEA 0183")]:
            updated[host_key] = text(host_key)
            try:
                port = int(data.get(port_key, current[port_key]))
            except (TypeError, ValueError):
                port = 0
            if not 1 <= port <= 65535:
                raise ValueError(f"{label} port must be 1-65535")
            updated[port_key] = port
        if source == "h5000" and not updated["h5000_host"]:
            raise ValueError("H5000 address cannot be blank")
        if source == "nmea0183" and not updated["nmea_host"]:
            raise ValueError("NMEA 0183 address cannot be blank")
        storage.save_settings(updated)
        return jsonify({"ok": True, "settings": updated, "error": None})
    except Exception as e:
        return jsonify({"ok": False, "settings": {}, "error": str(e)}), 400


def _seed_manual_wind():
    """Switching to manual wind with none entered yet: start from the wind in use now
    (the old source's, or the TWD last shown on the Course legs page)."""
    manual = instruments.read_manual_wind()
    if manual["twd"] is not None and manual["tws"] is not None:
        return
    wind = instruments.current_wind()      # still the old source: the new one is not saved yet
    if manual["twd"] is None and isinstance(wind["twd"], (int, float)):
        manual["twd"] = float(wind["twd"]) % 360
    if manual["tws"] is None and isinstance(wind["tws"], (int, float)):
        manual["tws"] = max(0.0, float(wind["tws"]))
    manual["updated"] = time.time()
    storage.write_json(storage.runtime_file("manual_wind.json"), manual)


@bp.route("/api/file_status")
def api_file_status():
    s = storage.load_settings()
    sail = storage.resolve_user_path(s["sailchart_file"])
    marks = storage.resolve_user_path(s["expedition_marks_file"])
    polar = storage.resolve_user_path(s["polar_file"])
    return jsonify({
        "ok": True,
        "sailchart_file": str(sail), "sailchart_exists": sail.exists(),
        "expedition_marks_file": str(marks), "expedition_marks_exists": marks.exists(),
        "polar_file": str(polar), "polar_exists": polar.exists(),
    })


UPLOAD_SETTING = {"sailchart": "sailchart_file", "polar": "polar_file", "marks": "expedition_marks_file"}


@bp.route("/api/upload_file", methods=["POST"])
def api_upload_file():
    """Save an uploaded sail chart, polar or Expedition marks XML and select it in settings."""
    file_type = request.form.get("type", "").strip()
    uploaded = request.files.get("file")
    if file_type not in UPLOAD_SETTING:
        return jsonify({"ok": False, "error": "File type must be sailchart, marks or polar"}), 400
    if uploaded is None or not uploaded.filename:
        return jsonify({"ok": False, "error": "No file selected"}), 400

    # Keep only the file name (no folders) and replace anything unusual.
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(uploaded.filename.replace("\\", "/")).name).strip() or "uploaded_file"
    if file_type == "marks" and not safe.lower().endswith(".xml"):
        return jsonify({"ok": False, "error": "Expedition marks file should be an XML file"}), 400

    target = storage.app_file(safe)
    uploaded.save(target)
    settings = storage.load_settings()
    settings[UPLOAD_SETTING[file_type]] = target.name
    storage.save_settings(settings)
    return jsonify({"ok": True, "filename": target.name, "path": str(target), "settings": settings, "error": None})
