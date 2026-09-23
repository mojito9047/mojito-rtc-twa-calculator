"""Course chart map tiles (server/tiles.py): fetched once with the internet, then served from runtime/tiles/."""

import os
import time
import urllib.error
from unittest import mock

from server import VERSION, tiles
from tests.helpers import ROOT, AppTestCase

PNG = tiles.PNG_SIGNATURE + b"tile"
OSM = "/tiles/osm/15/15770/10622.png"
SEAMARK = "/tiles/seamark/15/15770/10622.png"


class TileCacheTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.fetched = []
        self.online = True
        self.missing = False
        tiles._offline_until = 0.0
        patch = mock.patch.object(tiles, "fetch_tile", self.fake_fetch)
        patch.start()
        self.addCleanup(patch.stop)

    def fake_fetch(self, url):
        self.fetched.append(url)
        if not self.online:
            raise urllib.error.URLError("no internet")
        if self.missing:
            raise tiles.TileMissing()
        return PNG

    def get(self, url):
        resp = self.client.get(url)
        try:
            return resp.status_code, resp.data, resp.headers.get("Cache-Control")
        finally:
            resp.close()

    def saved(self, layer="osm", suffix=".png"):
        return self.dir / "runtime" / "tiles" / layer / "15" / "15770" / f"10622{suffix}"

    def age(self, path, days):
        when = time.time() - days * 24 * 3600
        os.utime(path, (when, when))

    def test_fetched_once_then_served_from_the_saved_copy(self):
        self.assertEqual(self.get(OSM)[:2], (200, PNG))
        self.assertEqual(self.fetched, ["https://tile.openstreetmap.org/15/15770/10622.png"])
        self.assertEqual(self.saved().read_bytes(), PNG)
        self.assertEqual(self.get(OSM)[:2], (200, PNG))
        self.assertEqual(len(self.fetched), 1)                  # not fetched again within the week

    def test_offline_serves_the_saved_copy_however_old(self):
        self.get(OSM)
        self.age(self.saved(), days=60)
        self.online = False
        self.assertEqual(self.get(OSM)[:2], (200, PNG))

    def test_refreshed_after_a_week_when_online(self):
        self.get(OSM)
        self.age(self.saved(), days=8)
        self.get(OSM)
        self.assertEqual(len(self.fetched), 2)
        self.assertLess(time.time() - self.saved().stat().st_mtime, 60)

    def test_offline_and_not_saved(self):
        self.online = False
        status, _, cache = self.get(OSM)
        self.assertEqual(status, 404)
        self.assertEqual(cache, "no-store")                    # the browser asks again later
        self.assertFalse(self.saved().exists())

    def test_servers_left_alone_for_a_minute_after_a_failure(self):
        self.online = False
        self.get(OSM)
        self.get(SEAMARK)                                      # not tried: still "offline"
        self.assertEqual(len(self.fetched), 1)
        tiles._offline_until = 0.0                             # the minute is up
        self.online = True
        self.assertEqual(self.get(SEAMARK)[0], 200)

    def test_missing_seamark_tile_remembered(self):
        self.missing = True
        status, _, cache = self.get(SEAMARK)
        self.assertEqual(status, 404)
        self.assertEqual(cache, tiles.BROWSER_CACHE)
        self.assertTrue(self.saved("seamark", ".none").exists())
        self.get(SEAMARK)
        self.assertEqual(len(self.fetched), 1)                 # not asked again within the week

    def test_browser_may_keep_tiles(self):
        # Every other response is no-cache (for the MFD); tiles are the exception.
        self.assertEqual(self.get(OSM)[2], tiles.BROWSER_CACHE)
        self.assertIn("no-store", self.client.get("/api/course").headers["Cache-Control"])

    def test_bad_tile_addresses(self):
        for url in ("/tiles/google/15/1/1.png", "/tiles/osm/20/1/1.png", "/tiles/osm/3/8/1.png", "/tiles/osm/3/1/8.png"):
            self.assertEqual(self.get(url)[0], 404, url)
        self.assertEqual(self.fetched, [])


class TileFetchTests(AppTestCase):
    def test_identifies_the_app(self):
        # OpenStreetMap's tile policy asks for a User-Agent that identifies the application.
        seen = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return PNG

        def urlopen(request, timeout):
            seen["agent"] = request.get_header("User-agent")
            seen["timeout"] = timeout
            return Response()

        with mock.patch.object(tiles.urllib.request, "urlopen", urlopen):
            self.assertEqual(tiles.fetch_tile("https://tile.openstreetmap.org/1/0/0.png"), PNG)
        self.assertIn(VERSION, seen["agent"])
        self.assertIn("github.com/mojito9047/mojito-rtc-twa-calculator", seen["agent"])
        self.assertLessEqual(seen["timeout"], 10)

    def test_not_a_png_is_an_error(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"<html>blocked</html>"

        with mock.patch.object(tiles.urllib.request, "urlopen", lambda request, timeout: Response()):
            with self.assertRaises(OSError):
                tiles.fetch_tile("https://tile.openstreetmap.org/1/0/0.png")

    def test_page_uses_the_local_leaflet_and_tiles(self):
        html = self.client.get("/").data.decode()
        self.assertIn('src="/static/leaflet/leaflet.js"', html)
        self.assertIn('href="/static/leaflet/leaflet.css"', html)
        self.assertNotIn("unpkg.com", html)
        script = (ROOT / "static" / "index.js").read_text(encoding="utf-8")
        self.assertIn('"/tiles/osm/{z}/{x}/{y}.png"', script)
        self.assertIn('"/tiles/seamark/{z}/{x}/{y}.png"', script)
        self.assertNotIn("tile.openstreetmap.org", script)
        for name in ("leaflet.js", "leaflet.css", "images/layers.png", "LICENSE"):
            resp = self.client.get("/static/leaflet/" + name)
            try:
                self.assertEqual(resp.status_code, 200, name)
            finally:
                resp.close()
