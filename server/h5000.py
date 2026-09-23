"""B&G H5000 websocket (Navico GoFree protocol, port 2053).

After connecting, the app subscribes to the data items it needs:

    {"DataReq": [{"id": 142, "repeat": true, "inst": 0}, ...]}

and the H5000 then sends {"Data": [{"id", "valid", "val", "sysVal", ...}]}
messages continuously.

Each item has `val`, in the display's units and reference (magnetic headings
if the display is set to magnetic), and `sysVal`, the underlying value:
angles and positions in radians, referenced to true; speeds in knots. The app
uses `sysVal`, so it does not depend on how the displays are set up. Checked
against the plotter's NMEA stream: TWD sysVal 6.1656 rad = 353.3°T, matching
MWD's true direction, while val was 353.7 (magnetic).
"""

import json
import math
import socket
import time

from server.expedition_dll import Var
from server.live_source import LiveSource
from server.websocket_client import WebSocket

# GoFree data id -> (channel, how sysVal converts)
ITEMS = {
    142: (Var.Twd, "angle"),       # True Wind Direction
    47: (Var.Tws, "speed"),        # True Wind Speed
    42: (Var.Bsp, "speed"),        # Boat Speed
    37: (Var.Hdg, "angle"),        # Heading
    9: (Var.Cog, "angle"),         # Course Over Ground
    41: (Var.Sog, "speed"),        # Speed Over Ground
    421: (Var.Lat, "position"),    # GPS Position Latitude
    422: (Var.Lon, "position"),    # GPS Position Longitude
}


def convert(kind, sys_val):
    if kind == "angle":
        return math.degrees(sys_val) % 360
    if kind == "position":
        return math.degrees(sys_val)
    return sys_val                   # speeds: knots


def parse_message(text):
    """{Var: value} from one H5000 message; items marked invalid are left out."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    out = {}
    for item in data.get("Data", []) if isinstance(data, dict) else []:
        spec = ITEMS.get(item.get("id")) if isinstance(item, dict) else None
        if not spec or not item.get("valid", False):
            continue
        sys_val = item.get("sysVal")
        if isinstance(sys_val, (int, float)) and math.isfinite(sys_val):
            var, kind = spec
            out[var] = convert(kind, sys_val)
    return out


def subscription():
    return json.dumps({"DataReq": [{"id": i, "repeat": True, "inst": 0} for i in ITEMS]})


class H5000Source(LiveSource):
    name = "H5000"
    READ_TIMEOUT = 10.0      # no message for this long counts as a dropped link

    def __init__(self, host, port):
        super().__init__(host, port)
        self._ws = None

    def connect(self):
        self._ws = WebSocket(self.host, self.port, "/", timeout=5)
        self._ws.send_text(subscription())
        self._ws.settimeout(self.READ_TIMEOUT)

    def read_once(self):
        try:
            text = self._ws.recv_text()
        except socket.timeout:
            # A timeout part-way through a frame leaves the stream out of step,
            # so treat it as a dropped link and reconnect.
            raise ConnectionError(f"no data for {self.READ_TIMEOUT:.0f} s")
        now = time.time()
        for var, value in parse_message(text).items():
            self.set_value(var, value, now)

    def close_connection(self):
        if self._ws:
            self._ws.close()
            self._ws = None
