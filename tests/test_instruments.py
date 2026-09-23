"""Instrument sources: NMEA 0183, the B&G H5000 websocket, and choosing between them.

Parsers are tested on real sentences and messages captured from the boat's
plotter and H5000 (tests/fixtures). The network readers are tested against
small local servers that stand in for the plotter and the H5000.
"""

import base64
import hashlib
import json
import math
import socket
import struct
import threading
import time
import unittest

from server import h5000, instruments, live_source, nmea0183, storage
from server.expedition_dll import Var
from server.websocket_client import WebSocket, WebSocketClosed
from tests.helpers import FIXTURES, AppTestCase

NMEA_LINES = (FIXTURES / "nmea0183_sample.txt").read_text(encoding="utf-8").splitlines()
H5000_MESSAGE = (FIXTURES / "h5000_data.json").read_text(encoding="utf-8").strip()


def wait_for(condition, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# NMEA 0183 parsing
# ---------------------------------------------------------------------------

class NmeaParserTests(unittest.TestCase):
    def parse_all(self, lines):
        parser, values = nmea0183.NmeaParser(), {}
        for line in lines:
            values.update(parser.parse(line))
        return values

    def test_checksums_of_captured_sentences(self):
        for line in NMEA_LINES:
            if line.startswith("$"):
                self.assertTrue(nmea0183.checksum_ok(line), line)
        self.assertFalse(nmea0183.checksum_ok("$WIMWD,6.2,T,6.6,M,5.5,N,2.8,M*55"))

    def test_bad_checksum_ignored(self):
        self.assertEqual(nmea0183.NmeaParser().parse("$WIMWD,6.2,T,6.6,M,5.5,N,2.8,M*00"), {})

    def test_captured_stream(self):
        v = self.parse_all(NMEA_LINES)
        self.assertAlmostEqual(v[Var.Twd], 6.2)            # MWD true direction
        self.assertAlmostEqual(v[Var.Tws], 5.5)            # MWD knots
        self.assertAlmostEqual(v[Var.Hdg], 175.0)          # VHW true / HDG 175.4 M with 0.4 W
        self.assertAlmostEqual(v[Var.Bsp], 0.0)
        self.assertAlmostEqual(v[Var.Lat], 52 + 53.2982 / 60, places=6)
        self.assertAlmostEqual(v[Var.Lon], -(4 + 24.4769 / 60), places=6)
        self.assertAlmostEqual(v[Var.Cog], 190.0)
        self.assertAlmostEqual(v[Var.Sog], 0.0)

    def test_hdg_magnetic_corrected_to_true(self):
        v = self.parse_all(["$IIHDG,175.4,,,0.4,W*33"])
        self.assertAlmostEqual(v[Var.Hdg], 175.0)

    def test_hdg_without_variation_gives_nothing(self):
        # Magnetic heading alone cannot be turned into true.
        line = "$IIHDG,175.4,,,,"
        line += "*%02X" % _xor(line)
        self.assertEqual(nmea0183.NmeaParser().parse(line), {})

    def test_true_mwv_used_without_mwd(self):
        # Captured: MWV true wind angle 178.2 with VHW true heading 174.6 -> TWD 352.8.
        v = self.parse_all(["$SDVHW,174.6,T,175.0,M,0.0,N,0.0,K*45", "$WIMWV,178.2,T,4.7,N,A*2A"])
        self.assertAlmostEqual(v[Var.Twd], 352.8)
        self.assertAlmostEqual(v[Var.Tws], 4.7)

    def test_origin_recorded(self):
        parser = nmea0183.NmeaParser()
        parser.parse("$IIHDG,175.4,,,0.4,W*33")
        self.assertEqual(parser.origin, ("II", "HDG"))

    def test_apparent_mwv_ignored(self):
        self.assertEqual(nmea0183.NmeaParser().parse("$WIMWV,191.4,R,5.5,N,A*2E"), {})

    def test_mwv_speed_units(self):
        line = "$WIMWV,90.0,T,5.0,M,A"
        line += "*%02X" % _xor(line)
        self.assertAlmostEqual(nmea0183.NmeaParser().parse(line)[Var.Tws], 5.0 * 1.943844)

    def test_rmc_without_fix_ignored(self):
        line = "$GPRMC,162630,V,5253.2982,N,00424.4769,W,0.0,190.0,230926,0.4,W,A"
        line += "*%02X" % _xor(line)
        self.assertEqual(nmea0183.NmeaParser().parse(line), {})

    def test_southern_and_eastern_positions(self):
        line = "$GPGLL,3352.1000,S,15112.6000,E,000000,A,A"
        line += "*%02X" % _xor(line)
        v = nmea0183.NmeaParser().parse(line)
        self.assertAlmostEqual(v[Var.Lat], -(33 + 52.1 / 60))
        self.assertAlmostEqual(v[Var.Lon], 151 + 12.6 / 60)

    def test_junk_ignored(self):
        parser = nmea0183.NmeaParser()
        for line in ["", "hello", "$", "$WIMWD", "$WIMWD,x,T", "!AIVDM,1,1,,,B3P,0*15"]:
            self.assertEqual(parser.parse(line), {})


def _xor(line):
    calc = 0
    for ch in line[1:]:
        calc ^= ord(ch)
    return calc


def sentence(body):
    """Add the checksum to a sentence."""
    return body + "*%02X" % _xor(body)


class ChannelPreferenceTests(unittest.TestCase):
    """Which sentence and talker each channel is taken from (NmeaChannels)."""

    def setUp(self):
        self.src = nmea0183.Nmea0183Source("127.0.0.1", 1)     # not started: lines are fed in directly

    def feed(self, lines, at):
        for line in lines:
            self.src.take(line, at)

    def value(self, var, at):
        return self.src.read(var, now=at)[0]

    def test_captured_stream_heading_from_vhw_not_hdg(self):
        # HDG arrives ten times as often as VHW, but VHW (true) is preferred.
        self.feed(NMEA_LINES, 100.0)
        self.feed(["$IIHDG,180.4,,,0.4,W" + "*%02X" % _xor("$IIHDG,180.4,,,0.4,W")] * 5, 100.5)
        self.assertAlmostEqual(self.value(Var.Hdg, 100.6), 175.0)
        self.assertEqual(self.src.channels.origins()["Hdg"], "SDVHW")
        self.assertEqual(self.src.channels.origins()["Lat"], "GPRMC")

    def test_hdt_takes_over_at_once(self):
        self.feed(["$SDVHW,175.0,T,175.4,M,0.0,N,0.0,K*46"], 100.0)
        self.feed([sentence("$HEHDT,176.0,T")], 100.1)
        self.assertAlmostEqual(self.value(Var.Hdg, 100.2), 176.0)

    def test_falls_back_when_preferred_goes_quiet(self):
        self.feed(["$SDVHW,175.0,T,175.4,M,0.0,N,0.0,K*46"], 100.0)
        self.feed([sentence("$IIHDG,190.4,,,0.4,W")], 102.0)                  # VHW still current
        self.assertAlmostEqual(self.value(Var.Hdg, 102.1), 175.0)
        self.feed([sentence("$IIHDG,190.4,,,0.4,W")], 100.0 + nmea0183.HOLD_SECONDS + 0.5)   # VHW silent
        self.assertAlmostEqual(self.value(Var.Hdg, 104.0), 190.0)

    def test_second_device_same_sentence_ignored_while_first_sends(self):
        self.feed([sentence("$IIHDG,175.4,,,0.4,W")], 100.0)
        self.feed([sentence("$HCHDG,200.4,,,0.4,W")], 100.5)                  # another compass
        self.assertAlmostEqual(self.value(Var.Hdg, 100.6), 175.0)
        self.feed([sentence("$IIHDG,175.6,,,0.4,W")], 101.0)
        self.assertAlmostEqual(self.value(Var.Hdg, 101.1), 175.2)
        self.feed([sentence("$HCHDG,200.4,,,0.4,W")], 105.0)                  # II has gone quiet
        self.assertAlmostEqual(self.value(Var.Hdg, 105.1), 200.0)

    def test_mwd_preferred_over_mwv_and_mwv_as_fallback(self):
        vhw = "$SDVHW,174.6,T,175.0,M,0.0,N,0.0,K*45"
        self.feed([vhw, "$WIMWD,353.3,T,353.7,M,4.7,N,2.4,M*5B", "$WIMWV,178.2,T,4.7,N,A*2A"], 100.0)
        self.assertAlmostEqual(self.value(Var.Twd, 100.1), 353.3)
        self.feed([vhw, "$WIMWV,178.2,T,4.7,N,A*2A"], 104.0)                   # MWD stopped
        self.assertAlmostEqual(self.value(Var.Twd, 104.1), 352.8)

    def test_mwv_uses_only_the_chosen_compass(self):
        self.feed(["$SDVHW,174.6,T,175.0,M,0.0,N,0.0,K*45"], 100.0)
        self.feed([sentence("$HCHDG,270.4,,,0.4,W")], 100.2)                  # not chosen for Hdg
        self.feed(["$WIMWV,178.2,T,4.7,N,A*2A"], 100.3)
        self.assertAlmostEqual(self.value(Var.Twd, 100.4), 352.8)             # 174.6 + 178.2, not 270 + 178.2

    def test_status_shows_origins(self):
        self.feed(NMEA_LINES, 100.0)
        origins = self.src.status(now=100.5)["channel_origins"]
        self.assertEqual((origins["Twd"], origins["Hdg"], origins["Cog"]), ("WIMWD", "SDVHW", "GPRMC"))


# ---------------------------------------------------------------------------
# H5000 messages
# ---------------------------------------------------------------------------

class H5000MessageTests(unittest.TestCase):
    def test_captured_message_uses_true_sysval(self):
        v = h5000.parse_message(H5000_MESSAGE)
        # sysVal radians -> degrees true; val was magnetic (354.2).
        self.assertAlmostEqual(v[Var.Twd], math.degrees(6.174210885902416))
        self.assertAlmostEqual(v[Var.Twd], 353.76, places=2)
        self.assertAlmostEqual(v[Var.Hdg], math.degrees(3.054999438113649))
        self.assertAlmostEqual(v[Var.Tws], 4.297646999359131)     # knots
        self.assertAlmostEqual(v[Var.Lat], 52.888308, places=5)
        self.assertAlmostEqual(v[Var.Lon], -4.407946, places=5)
        self.assertNotIn("TWA", [k.name for k in v])              # id 141 is not used

    def test_invalid_items_skipped(self):
        msg = json.dumps({"Data": [{"id": 142, "valid": False, "sysVal": 1.0}, {"id": 47, "valid": True, "sysVal": 9.5}]})
        self.assertEqual(h5000.parse_message(msg), {Var.Tws: 9.5})

    def test_other_messages_ignored(self):
        for text in ["", "not json", "[]", json.dumps({"DataList": {"list": [1]}}), json.dumps({"Data": [{"id": 142}]})]:
            self.assertEqual(h5000.parse_message(text), {})

    def test_subscription_requests_every_item(self):
        req = json.loads(h5000.subscription())["DataReq"]
        self.assertEqual({r["id"] for r in req}, set(h5000.ITEMS))
        self.assertTrue(all(r["repeat"] for r in req))


# ---------------------------------------------------------------------------
# Fake plotter and H5000
# ---------------------------------------------------------------------------

class FakeServer:
    """A local TCP server; `handle(conn)` runs for each connection in its own thread."""

    def __init__(self, handle):
        self.handle = handle
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            self.handle(conn)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self._stop = True
        self.sock.close()


def ws_accept(conn):
    """Server side of the websocket handshake; returns the request path."""
    head = b""
    while b"\r\n\r\n" not in head:
        head += conn.recv(1024)
    lines = head.decode().split("\r\n")
    key = next(l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("sec-websocket-key"))
    accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
    return lines[0].split()[1]


def ws_frame(opcode, payload, fin=True):
    n = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    head += bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n)
    return head + payload


def ws_read_client_frame(conn):
    """A masked client frame -> (opcode, payload)."""
    def exact(n):
        buf = b""
        while len(buf) < n:
            buf += conn.recv(n - len(buf))
        return buf
    b1, b2 = exact(2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack("!H", exact(2))[0]
    mask = exact(4)
    return b1 & 0x0F, bytes(b ^ mask[i % 4] for i, b in enumerate(exact(n)))


class WebSocketClientTests(unittest.TestCase):
    def test_handshake_frames_ping_and_fragments(self):
        received = {}

        def handle(conn):
            received["path"] = ws_accept(conn)
            received["subscription"] = ws_read_client_frame(conn)
            conn.sendall(ws_frame(0x9, b"hi"))                                # ping
            conn.sendall(ws_frame(0x1, b'{"a":', fin=False) + ws_frame(0x0, b"1}"))   # fragmented text
            received["pong"] = ws_read_client_frame(conn)
            conn.sendall(ws_frame(0x8, b""))                                  # close
            time.sleep(0.2)

        server = FakeServer(handle)
        try:
            ws = WebSocket("127.0.0.1", server.port, "/")
            ws.send_text('{"DataReq":[]}')
            self.assertEqual(ws.recv_text(), '{"a":1}')
            with self.assertRaises(WebSocketClosed):
                ws.recv_text()
            ws.close()
            self.assertEqual(received["path"], "/")
            self.assertEqual(received["subscription"], (0x1, b'{"DataReq":[]}'))
            self.assertEqual(received["pong"], (0xA, b"hi"))
        finally:
            server.close()

    def test_refused_handshake(self):
        def handle(conn):
            conn.recv(1024)
            conn.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")
        server = FakeServer(handle)
        try:
            with self.assertRaises(ValueError):
                WebSocket("127.0.0.1", server.port, "/")
        finally:
            server.close()


def fake_plotter(lines, repeat=True):
    def handle(conn):
        while True:
            for line in lines:
                conn.sendall((line + "\r\n").encode())
            if not repeat:
                return
            time.sleep(0.05)
    return FakeServer(handle)


def fake_h5000(message, subscriptions):
    def handle(conn):
        ws_accept(conn)
        subscriptions.append(ws_read_client_frame(conn)[1].decode())
        while True:
            conn.sendall(ws_frame(0x1, message.encode()))
            time.sleep(0.05)
    return FakeServer(handle)


class LiveSourceTests(unittest.TestCase):
    def test_nmea_source_reads_plotter(self):
        server = fake_plotter(NMEA_LINES)
        src = nmea0183.Nmea0183Source("127.0.0.1", server.port)
        try:
            src.start()
            self.assertTrue(wait_for(lambda: src.read(Var.Twd)[2] is None), src.status())
            value, age, error = src.read(Var.Twd)
            self.assertAlmostEqual(value, 6.2)
            self.assertLess(age, 2)
            self.assertTrue(src.status()["connected"])
        finally:
            src.stop()
            server.close()

    def test_nmea_source_reconnects(self):
        server = fake_plotter(NMEA_LINES, repeat=False)     # sends once, then hangs up
        src = nmea0183.Nmea0183Source("127.0.0.1", server.port)
        try:
            src.start()
            self.assertTrue(wait_for(lambda: server.connections >= 2, timeout=6))
        finally:
            src.stop()
            server.close()

    def test_h5000_source_subscribes_and_reads(self):
        subs = []
        server = fake_h5000(H5000_MESSAGE, subs)
        src = h5000.H5000Source("127.0.0.1", server.port)
        try:
            src.start()
            self.assertTrue(wait_for(lambda: src.read(Var.Lat)[2] is None), src.status())
            self.assertAlmostEqual(src.read(Var.Lat)[0], 52.888308, places=5)
            self.assertEqual({r["id"] for r in json.loads(subs[0])["DataReq"]}, set(h5000.ITEMS))
        finally:
            src.stop()
            server.close()

    def test_old_values_are_stale(self):
        src = nmea0183.Nmea0183Source("127.0.0.1", 1)
        src.set_value(Var.Twd, 90.0, now=100.0)
        self.assertEqual(src.read(Var.Twd, now=102.0)[0], 90.0)
        value, age, error = src.read(Var.Twd, now=100.0 + live_source.STALE_SECONDS + 1)
        self.assertIsNone(value)
        self.assertIn("No recent", error)

    def test_unreachable_source_reports_error(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()                                        # nothing listening here
        src = nmea0183.Nmea0183Source("127.0.0.1", port)
        try:
            src.start()
            self.assertTrue(wait_for(lambda: src.error and "127.0.0.1" in src.error))
            self.assertIsNotNone(src.read(Var.Twd)[2])
            self.assertFalse(src.status()["connected"])
        finally:
            src.stop()


# ---------------------------------------------------------------------------
# Choosing the source
# ---------------------------------------------------------------------------

class SourceSelectionTests(AppTestCase):
    FAKE_ONLY_EXPEDITION = True

    def test_default_is_expedition(self):
        self.assertEqual(storage.load_settings()["instrument_source"], "expedition")
        self.assertEqual(self.client.get("/api/twd").get_json()["twd"], 350.0)        # the fake Expedition
        self.assertEqual(self.client.get("/api/instruments").get_json()["kind"], "expedition")

    def test_nmea_source_feeds_the_app(self):
        server = fake_plotter(NMEA_LINES)
        try:
            self.set_settings(instrument_source="nmea0183", nmea_host="127.0.0.1", nmea_port=server.port)
            self.assertTrue(wait_for(lambda: self.client.get("/api/twd").get_json().get("source") == "nmea0183"))
            twd = self.client.get("/api/twd").get_json()
            self.assertAlmostEqual(twd["twd"], 6.2)
            pos = self.client.get("/api/position").get_json()
            self.assertAlmostEqual(pos["lat"], 52 + 53.2982 / 60, places=6)
            exp = self.client.get("/api/expedition").get_json()["data"]
            self.assertAlmostEqual(exp["Tws"], 5.5)
            status = self.client.get("/api/instruments").get_json()
            self.assertTrue(status["connected"])
            self.assertEqual(status["label"], "NMEA 0183")
            self.assertTrue(self.client.get("/api/health").get_json()["ok"])
        finally:
            server.close()

    def test_h5000_source_feeds_the_app(self):
        subs = []
        server = fake_h5000(H5000_MESSAGE, subs)
        try:
            self.set_settings(instrument_source="h5000", h5000_host="127.0.0.1", h5000_port=server.port)
            self.assertTrue(wait_for(lambda: self.client.get("/api/position").get_json()["ok"]))
            self.assertAlmostEqual(self.client.get("/api/twd").get_json()["twd"], 353.76, places=2)
        finally:
            server.close()

    def test_switching_back_stops_the_reader(self):
        server = fake_plotter(NMEA_LINES)
        try:
            self.set_settings(instrument_source="nmea0183", nmea_host="127.0.0.1", nmea_port=server.port)
            kind, live = instruments.selected_source()
            self.assertTrue(live.running())
            self.set_settings(instrument_source="expedition")
            kind, now_live = instruments.selected_source()
            self.assertIsNone(now_live)
            self.assertFalse(live.running())
            self.assertEqual(self.client.get("/api/twd").get_json()["twd"], 350.0)
        finally:
            server.close()

    def test_no_data_from_source(self):
        self.set_settings(instrument_source="nmea0183", nmea_host="127.0.0.1", nmea_port=1)
        data = self.client.get("/api/expedition").get_json()
        self.assertFalse(data["ok"])
        self.assertIsNone(data["data"]["Twd"])
        self.assertFalse(self.client.get("/api/position").get_json()["ok"])


class InstrumentSettingsTests(AppTestCase):
    def post(self, **fields):
        return self.client.post("/api/settings", json=fields)

    def test_defaults(self):
        s = self.client.get("/api/settings").get_json()["settings"]
        self.assertEqual((s["instrument_source"], s["h5000_host"], s["h5000_port"], s["nmea_host"], s["nmea_port"]),
                         ("expedition", "192.168.15.149", 2053, "192.168.15.166", 10110))

    def test_save_source_and_addresses(self):
        resp = self.post(instrument_source="h5000", h5000_host="10.0.0.5", h5000_port=2054, nmea_port=10111)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        s = storage.load_settings()
        self.assertEqual((s["instrument_source"], s["h5000_host"], s["h5000_port"], s["nmea_port"]),
                         ("h5000", "10.0.0.5", 2054, 10111))

    def test_other_settings_keep_instrument_settings(self):
        self.post(instrument_source="nmea0183")
        self.client.post("/api/race_officer/poll_config", json={"enabled": False})
        self.assertEqual(storage.load_settings()["instrument_source"], "nmea0183")

    def test_invalid_values_rejected(self):
        self.assertEqual(self.post(instrument_source="signalk").status_code, 400)
        self.assertEqual(self.post(nmea_port=70000).status_code, 400)
        self.assertEqual(self.post(instrument_source="h5000", h5000_host=" ").status_code, 400)

    def test_bad_file_values_fall_back(self):
        self.set_settings(instrument_source="nonsense", h5000_port="abc")
        s = storage.load_settings()
        self.assertEqual((s["instrument_source"], s["h5000_port"]), ("expedition", 2053))


if __name__ == "__main__":
    unittest.main()
