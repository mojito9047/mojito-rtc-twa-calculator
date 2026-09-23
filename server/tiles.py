"""Map tiles for the course chart, kept for use without the internet.

The chart asks this app for its tiles (/tiles/osm/{z}/{x}/{y}.png and
/tiles/seamark/{z}/{x}/{y}.png) instead of the tile servers. The first time a
tile is shown with an internet connection it is fetched from OpenStreetMap or
OpenSeaMap and saved in runtime/tiles/<layer>/<z>/<x>/<y>.png. After that the
saved copy is served, refreshed once it is a week old if the internet is there.
Without the internet any saved copy is served, however old, so every area
viewed at home is on the chart on the water.

OpenSeaMap has no tile where there are no seamarks (404). That is remembered
too, as an empty <y>.none file, so it is not asked again for a week.

OpenStreetMap's tile usage policy asks for an identifying User-Agent and for
tiles to be kept at least a week; tiles are fetched only as they are viewed,
never in bulk. After a failed connection the tile servers are left alone for a
minute, so an offline chart does not wait on every tile.
"""

import threading
import time
import urllib.error
import urllib.request

from flask import Blueprint, Response, abort

from server import VERSION, storage

bp = Blueprint("tiles", __name__)

SOURCES = {
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "seamark": "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
}
MAX_ZOOM = 19
FRESH_SECONDS = 7 * 24 * 3600          # refresh a saved tile after a week (when online)
OFFLINE_RETRY_SECONDS = 60             # after a failed connection, serve saved tiles only for this long
TIMEOUT_SECONDS = 5
USER_AGENT = f"MojitoRTCTWACalculator/{VERSION} (+https://github.com/mojito9047/mojito-rtc-twa-calculator)"
BROWSER_CACHE = "public, max-age=86400"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_lock = threading.Lock()
_offline_until = 0.0


class TileMissing(Exception):
    """The tile server has no tile there (normal for seamarks away from any)."""


def fetch_tile(url):
    """The tile's PNG bytes. TileMissing for a 404; OSError when offline or the server fails."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise TileMissing() from exc
        raise
    if not data.startswith(PNG_SIGNATURE):
        raise OSError("not a PNG tile")
    return data


def tile_path(layer, z, x, y):
    return storage.runtime_file("tiles") / layer / str(z) / str(x) / f"{y}.png"


def _age(path):
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def _online():
    with _lock:
        return time.time() >= _offline_until


def _went_offline():
    global _offline_until
    with _lock:
        _offline_until = time.time() + OFFLINE_RETRY_SECONDS


def _save(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        storage.write_bytes_atomic(path, data)
    except OSError:
        pass                            # served anyway; saved next time it is shown


def _serve(path):
    """A saved tile, or 404 for a remembered missing tile or nothing saved."""
    if path is not None and path.suffix == ".png":
        try:
            return Response(path.read_bytes(), mimetype="image/png", headers={"Cache-Control": BROWSER_CACHE})
        except OSError:
            pass
    # Nothing saved: let the browser ask again later. Remembered missing: it may keep that.
    cache = BROWSER_CACHE if path is not None and path.suffix == ".none" else "no-store"
    return Response(status=404, headers={"Cache-Control": cache})


@bp.route("/tiles/<layer>/<int:z>/<int:x>/<int:y>.png")
def tile(layer, z, x, y):
    if layer not in SOURCES or z > MAX_ZOOM or x >= 2 ** z or y >= 2 ** z:
        abort(404)
    path = tile_path(layer, z, x, y)
    missing = path.with_suffix(".none")

    for saved in (path, missing):
        age = _age(saved)
        if age is not None and age < FRESH_SECONDS:
            return _serve(saved)
    stale = path if path.exists() else (missing if missing.exists() else None)
    if not _online():
        return _serve(stale)

    try:
        data = fetch_tile(SOURCES[layer].format(z=z, x=x, y=y))
    except TileMissing:
        _save(missing, b"")
        path.unlink(missing_ok=True)
        return _serve(missing)
    except OSError:
        _went_offline()
        return _serve(stale)
    _save(path, data)
    missing.unlink(missing_ok=True)
    return Response(data, mimetype="image/png", headers={"Cache-Control": BROWSER_CACHE})
