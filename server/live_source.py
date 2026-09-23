"""Base for instrument sources read over the network (H5000, NMEA 0183).

A LiveSource runs a background thread that connects, reads, and keeps the
latest value of each channel (expedition_dll.Var) with the time it arrived.
read(var) gives (value, age_seconds, error); a value older than STALE_SECONDS
counts as no data. If the link drops, the thread reconnects with a back-off.
"""

import threading
import time

STALE_SECONDS = 5.0
RECONNECT_SECONDS = (1, 2, 5, 10)      # back-off between failed connection attempts


class LiveSource:
    name = "source"

    def __init__(self, host, port):
        self.host = host
        self.port = int(port)
        self._values = {}                  # Var -> (value, time received)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.connected = False
        self.error = "Not started"
        self.last_message = 0.0

    # -- values ------------------------------------------------------------

    def set_value(self, var, value, now=None):
        with self._lock:
            self._values[var] = (value, now if now is not None else time.time())

    def read(self, var, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            item = self._values.get(var)
        if item is None:
            return None, None, self.error or f"No {var.name} from {self.name}"
        value, received = item
        age = now - received
        if age > STALE_SECONDS:
            return None, age, f"No recent {var.name} from {self.name} ({age:.0f} s old)"
        return value, age, None

    def status(self, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            ages = {var.name: round(now - t, 1) for var, (_, t) in self._values.items()}
        return {
            "source": self.name,
            "host": self.host,
            "port": self.port,
            "connected": self.connected,
            "error": self.error,
            "last_message_age": round(now - self.last_message, 1) if self.last_message else None,
            "channel_ages": ages,
        }

    # -- thread ------------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"{self.name} reader", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.close_connection()

    def running(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _run(self):
        failures = 0
        while not self._stop.is_set():
            try:
                self.connect()
                self.connected, self.error, failures = True, None, 0
                while not self._stop.is_set():
                    self.read_once()
                    self.last_message = time.time()
            except Exception as e:
                if not self._stop.is_set():
                    self.error = f"{self.name} {self.host}:{self.port}: {e or type(e).__name__}"
            finally:
                self.connected = False
                self.close_connection()
            if self._stop.is_set():
                break
            self._stop.wait(RECONNECT_SECONDS[min(failures, len(RECONNECT_SECONDS) - 1)])
            failures += 1

    # -- for subclasses ----------------------------------------------------

    def connect(self):
        """Open the connection (and subscribe, if the protocol needs it)."""
        raise NotImplementedError

    def read_once(self):
        """Block for the next message and store what it contains; raise if the link fails."""
        raise NotImplementedError

    def close_connection(self):
        pass
