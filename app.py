"""Mojito RTC TWA Calculator Flask application.

Run with `python app.py` (start_app.bat) on the Expedition PC; the pages are on
port 8765, served by Waitress. This file creates the Flask app, registers the
API modules, serves the three pages and starts the background threads. The
work is done in server/:

    server/__init__.py        VERSION, the release shown on every page
    server/storage.py         app folder and runtime/ paths, settings, JSON files
    server/instruments.py     instrument source, wind, position, wind history
    server/h5000.py           B&G H5000 websocket reader
    server/nmea0183.py        NMEA 0183 over TCP reader
    server/live_source.py     background reader shared by the two above
    server/course_data.py     course, current leg, marks, sail chart, polar, settings, uploads
    server/race_officer.py    Race Officer import, polling and start bar data
    server/tiles.py           course chart map tiles, saved for use offline
    server/expedition_dll.py  Expedition DLL wrapper
    server/mfd_advertiser.py  B&G/Navico MFD discovery

Leg calculations are done in the browser (static/legs.js).
"""

import socket
import sys

import waitress
from flask import Flask, jsonify, render_template, request

from server import VERSION, course_data, instruments, race_officer, storage, tiles
from server.mfd_advertiser import (MFD_MULTICAST_GROUP, MFD_MULTICAST_PORT, SEND_FROM_PORT,
                                   build_mfd_payload, get_local_ipv4_addresses, start_mfd_advertiser)

PORT = 8765
# Waitress worker threads. The course chart asks for dozens of map tiles at once,
# and a tile fetched from the internet holds its thread for up to 5 seconds.
THREADS = 16

app = Flask(__name__)
app.register_blueprint(instruments.bp)
app.register_blueprint(course_data.bp)
app.register_blueprint(race_officer.bp)
app.register_blueprint(tiles.bp)


@app.context_processor
def add_app_version():
    # Every page shows the release, so it is clear what is running on the boat.
    return {"app_version": VERSION}


@app.after_request
def add_no_cache_headers(response):
    # Some MFD browsers cache API responses aggressively. Map tiles are the
    # exception: they set their own headers so the browser keeps them.
    if request.path.startswith("/tiles/"):
        return response
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/phone")
def phone_view():
    return render_template("phone.html")


@app.route("/mfd")
def mfd_view():
    return render_template("mfd.html")


@app.route("/api/mfd_status")
def api_mfd_status():
    """The MFD advertisement payloads being multicast, one per local address."""
    addresses = get_local_ipv4_addresses()
    return jsonify({
        "ok": True,
        "multicast_group": MFD_MULTICAST_GROUP,
        "multicast_port": MFD_MULTICAST_PORT,
        "send_from_port": SEND_FROM_PORT,
        "addresses": addresses,
        "payloads": [build_mfd_payload(f"http://{ip}:{PORT}", ip) for ip in addresses],
    })


def listening_socket(port):
    """The port on every network address, for this copy of the app alone.

    Waitress opens its own port with SO_REUSEADDR, which on Windows lets a
    second program open the same port and take some of its requests: an earlier
    version left running would go on serving pages beside the new one. With
    SO_EXCLUSIVEADDRUSE the second copy fails to start instead.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # restart straight after a stop
        sock.bind(("0.0.0.0", port))
    except OSError:
        sock.close()
        raise
    return sock


def serve(port=PORT):
    """Serve the pages on every network address with Waitress until the window is closed.

    Waitress, not Flask's own server: that is meant for development only (and
    says so every time it starts).
    """
    try:
        sock = listening_socket(port)
    except OSError as exc:
        # Most often another copy (an earlier version?) is still running.
        print(f"Could not start on port {port}: {exc}")
        print("Is the app already running? Close its window, then start it again.")
        return 1
    print(f"Mojito RTC TWA Calculator {VERSION}")
    print(f"  On this PC:        http://localhost:{port}")
    for ip in get_local_ipv4_addresses():
        print(f"  On other devices:  http://{ip}:{port}")
    print("Close this window to stop the app.", flush=True)
    waitress.serve(app, sockets=[sock], threads=THREADS)
    return 0


def main():
    storage.prepare_runtime_dir()
    instruments.start_wind_sampler()
    start_mfd_advertiser(port=PORT)
    race_officer.start_poller()
    return serve()


if __name__ == "__main__":
    sys.exit(main())
