"""NMEA 0183 over TCP, e.g. from a chart plotter (port 10110).

Sentences used (any talker ID, checksums verified):

    MWD   true wind direction and speed                  -> Twd, Tws
    MWV   true wind angle and speed (reference T), used with true heading
          for TWD when no MWD is received                  -> Twd, Tws
    HDT   true heading                                     -> Hdg
    HDG   magnetic heading + deviation + variation         -> Hdg (true)
    VHW   true heading, boat speed through the water       -> Hdg, Bsp
    RMC   position, SOG, COG (true), variation             -> Lat, Lon, Sog, Cog
    GLL / GGA  position                                    -> Lat, Lon
    VTG   COG (true) and SOG                               -> Cog, Sog

All directions are stored as degrees true, speeds in knots.

Several sentences can carry the same value (heading in HDG and VHW, position
in RMC, GGA and GLL), and a plotter can pass on more than one device (two
compasses, two GPS). So that a value does not flip between them, each channel
takes it from one origin, a talker + sentence, in the order of PREFERENCE
below. A less preferred origin is used only when the one in use has sent
nothing for HOLD_SECONDS (see NmeaChannels).
"""

import socket
import time

from server.expedition_dll import Var
from server.live_source import LiveSource

KNOTS_PER = {"N": 1.0, "M": 1.943844, "K": 0.539957}     # MWV speed units: knots, m/s, km/h

# Sentences each channel is taken from, most preferred first.
PREFERENCE = {
    Var.Twd: ("MWD", "MWV"),
    Var.Tws: ("MWD", "MWV"),
    Var.Hdg: ("HDT", "VHW", "HDG"),
    Var.Bsp: ("VHW",),
    Var.Lat: ("RMC", "GGA", "GLL"),
    Var.Lon: ("RMC", "GGA", "GLL"),
    Var.Cog: ("RMC", "VTG"),
    Var.Sog: ("RMC", "VTG"),
}
HOLD_SECONDS = 3.0     # how long the origin in use may be silent before another is used


def checksum_ok(sentence):
    """True if the sentence has a valid *hh checksum (sentences without one are accepted)."""
    body, star, given = sentence.partition("*")
    if not star:
        return True
    calc = 0
    for ch in body[1:]:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def _num(text):
    try:
        return float(text) if text not in ("", None) else None
    except ValueError:
        return None


def _latlon(value, hemi, degree_digits):
    """NMEA ddmm.mmm / dddmm.mmm + N/S/E/W -> signed decimal degrees."""
    if not value or not hemi:
        return None
    try:
        deg = float(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError:
        return None
    v = deg + minutes / 60.0
    return -v if hemi in ("S", "W") else v


def _signed(value, direction):
    """A deviation/variation value with E/W -> degrees, east positive."""
    v = _num(value)
    if v is None:
        return None
    return -v if direction == "W" else v


class NmeaChannels:
    """Chooses which origin (talker + sentence) each channel's value comes from.

    offer() returns True if the value was taken. An origin keeps a channel
    while it keeps sending; a more preferred sentence (PREFERENCE) takes over
    at once; any other origin only after the one in use has been silent for
    HOLD_SECONDS.
    """

    def __init__(self):
        self._holder = {}             # Var -> (origin, time last taken)

    @staticmethod
    def rank(var, sentence):
        order = PREFERENCE.get(var, ())
        return order.index(sentence) if sentence in order else len(order)

    def offer(self, var, value, origin, now):
        talker, sentence = origin
        held = self._holder.get(var)
        if held:
            (held_talker, held_sentence), held_time = held
            same = origin == (held_talker, held_sentence)
            better = self.rank(var, sentence) < self.rank(var, held_sentence)
            silent = now - held_time > HOLD_SECONDS
            if not (same or better or silent):
                return False
        self._holder[var] = (origin, now)
        return True

    def origins(self):
        """{channel name: "talker+sentence"} currently in use."""
        return {var.name: talker + sentence for var, ((talker, sentence), _) in self._holder.items()}


class NmeaParser:
    """Turns sentences into channel values: {Var: value}. Keeps state between sentences.

    After each parse(), `origin` is the (talker, sentence) of that line.
    """

    def __init__(self):
        self.true_heading = None      # for MWV-based TWD
        self.variation = None         # from RMC or HDG, east positive
        self.origin = None

    def parse(self, line):
        line = line.strip()
        self.origin = None
        if not line.startswith("$") or not checksum_ok(line):
            return {}
        fields = line.split("*")[0].split(",")
        kind = fields[0][-3:]
        self.origin = (fields[0][1:-3], kind)
        handler = getattr(self, "_" + kind.lower(), None)
        if handler is None:
            return {}
        try:
            return handler(fields) or {}
        except (IndexError, ValueError):
            return {}

    def _mwd(self, f):
        # $--MWD,dir_T,T,dir_M,M,speed_kn,N,speed_ms,M
        twd, tws = _num(f[1]), _num(f[5])
        if twd is None and _num(f[3]) is not None and self.variation is not None:
            twd = (_num(f[3]) + self.variation) % 360
        out = {}
        if twd is not None:
            out[Var.Twd] = twd % 360
        if tws is not None:
            out[Var.Tws] = tws
        return out

    def _mwv(self, f):
        # $--MWV,angle,reference(R/T),speed,unit,status
        if f[2] != "T" or f[5][:1] != "A":
            return {}
        angle, speed = _num(f[1]), _num(f[3])
        out = {}
        if speed is not None and f[4] in KNOTS_PER:
            out[Var.Tws] = speed * KNOTS_PER[f[4]]
        if angle is not None and self.true_heading is not None:
            out[Var.Twd] = (self.true_heading + angle) % 360
        return out

    def _hdt(self, f):
        hdg = _num(f[1])
        if hdg is None:
            return {}
        self.true_heading = hdg % 360
        return {Var.Hdg: self.true_heading}

    def _hdg(self, f):
        # $--HDG,heading_M,deviation,E/W,variation,E/W
        mag = _num(f[1])
        dev = _signed(f[2], f[3]) or 0.0
        var = _signed(f[4], f[5])
        if var is not None:
            self.variation = var
        if mag is None or self.variation is None:
            return {}
        self.true_heading = (mag + dev + self.variation) % 360
        return {Var.Hdg: self.true_heading}

    def _vhw(self, f):
        # $--VHW,heading_T,T,heading_M,M,speed_kn,N,speed_kmh,K
        out = {}
        hdg = _num(f[1])
        if hdg is not None:
            self.true_heading = hdg % 360
            out[Var.Hdg] = self.true_heading
        bsp = _num(f[5])
        if bsp is not None:
            out[Var.Bsp] = bsp
        return out

    def _rmc(self, f):
        # $--RMC,time,status,lat,N/S,lon,E/W,sog,cog_T,date,variation,E/W,...
        var = _signed(f[10], f[11]) if len(f) > 11 else None
        if var is not None:
            self.variation = var
        if f[2] != "A":
            return {}
        out = {}
        lat, lon = _latlon(f[3], f[4], 2), _latlon(f[5], f[6], 3)
        if lat is not None and lon is not None:
            out[Var.Lat], out[Var.Lon] = lat, lon
        sog, cog = _num(f[7]), _num(f[8])
        if sog is not None:
            out[Var.Sog] = sog
        if cog is not None:
            out[Var.Cog] = cog % 360
        return out

    def _gll(self, f):
        # $--GLL,lat,N/S,lon,E/W,time,status
        if len(f) > 6 and f[6] != "A":
            return {}
        lat, lon = _latlon(f[1], f[2], 2), _latlon(f[3], f[4], 3)
        return {Var.Lat: lat, Var.Lon: lon} if lat is not None and lon is not None else {}

    def _gga(self, f):
        # $--GGA,time,lat,N/S,lon,E/W,quality,...
        if f[6] in ("", "0"):
            return {}
        lat, lon = _latlon(f[2], f[3], 2), _latlon(f[4], f[5], 3)
        return {Var.Lat: lat, Var.Lon: lon} if lat is not None and lon is not None else {}

    def _vtg(self, f):
        # $--VTG,cog_T,T,cog_M,M,sog_kn,N,sog_kmh,K
        out = {}
        cog, sog = _num(f[1]), _num(f[5])
        if cog is not None:
            out[Var.Cog] = cog % 360
        if sog is not None:
            out[Var.Sog] = sog
        return out


class Nmea0183Source(LiveSource):
    """NMEA 0183 sentences from a TCP server (the plotter)."""

    name = "NMEA 0183"
    READ_TIMEOUT = 10.0      # no bytes for this long counts as a dropped link

    def __init__(self, host, port):
        super().__init__(host, port)
        self._sock = None
        self._buffer = b""
        self.parser = NmeaParser()
        self.channels = NmeaChannels()

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), timeout=5)
        self._sock.settimeout(self.READ_TIMEOUT)
        self._buffer = b""
        self.parser = NmeaParser()
        self.channels = NmeaChannels()

    def status(self, now=None):
        status = super().status(now)
        status["channel_origins"] = self.channels.origins()
        return status

    def read_once(self):
        chunk = self._sock.recv(4096)
        if not chunk:
            raise ConnectionError("closed by the plotter")
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        if len(self._buffer) > 4096:          # no line ending: not NMEA
            self._buffer = b""
        now = time.time()
        for line in lines:
            self.take(line.decode("ascii", errors="replace"), now)

    def take(self, line, now):
        """Parse one sentence and keep the values its origin is chosen for."""
        heading_before = self.parser.true_heading
        values = self.parser.parse(line)
        for var, value in values.items():
            if self.channels.offer(var, value, self.parser.origin, now):
                self.set_value(var, value, now)
            elif var == Var.Hdg:
                # TWD from MWV uses the heading, so only the chosen compass counts.
                self.parser.true_heading = heading_before

    def close_connection(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
