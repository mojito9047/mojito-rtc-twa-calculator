"""A minimal websocket client (RFC 6455) for the B&G H5000.

Enough for the H5000's JSON feed: the opening handshake, sending masked text
frames, and receiving text frames (with fragments), answering pings and
noticing a close. Written here so the app needs nothing beyond Flask.
"""

import base64
import hashlib
import os
import socket
import struct

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketClosed(Exception):
    pass


class WebSocket:
    def __init__(self, host, port, path="/", timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        try:
            self._handshake(host, port, path)
        except Exception:
            self.sock.close()
            raise

    def _handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise WebSocketClosed("connection closed during handshake")
            head += chunk
            if len(head) > 8192:
                raise ValueError("websocket handshake response too long")
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ValueError(f"websocket handshake refused: {lines[0]}")
        headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if ":" in l)}
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expected:
            raise ValueError("websocket handshake: bad Sec-WebSocket-Accept")

    def settimeout(self, seconds):
        self.sock.settimeout(seconds)

    def _send_frame(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_text(self, text):
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise WebSocketClosed("connection closed")
            buf += chunk
        return buf

    def _recv_frame(self):
        b1, b2 = self._recv_exact(2)
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if b2 & 0x80 else None
        payload = self._recv_exact(n)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return bool(b1 & 0x80), b1 & 0x0F, payload

    def recv_text(self):
        """The next text (or binary) message as a string. Raises socket.timeout, WebSocketClosed."""
        parts, opcode = [], None
        while True:
            fin, op, payload = self._recv_frame()
            if op == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                raise WebSocketClosed("closed by server")
            if op in (OP_TEXT, OP_BINARY):
                parts, opcode = [payload], op
            elif op == OP_CONT and opcode is not None:
                parts.append(payload)
            if fin and opcode is not None:
                return b"".join(parts).decode("utf-8", errors="replace")

    def close(self):
        try:
            self._send_frame(OP_CLOSE, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
