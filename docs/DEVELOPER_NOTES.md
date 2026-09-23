# Developer notes

## Structure

| File | Notes |
| --- | --- |
| `app.py` | Creates the Flask app, registers the `server/` blueprints, serves the three pages and `/api/mfd_status`, starts the background threads, then serves with Waitress (`serve()`, 16 threads). It opens port 8765 itself with `SO_EXCLUSIVEADDRUSE`: Waitress's own `SO_REUSEADDR` would let a second copy share the port on Windows. |
| `server/__init__.py` | `VERSION`, the release shown on every page. Bump it with each tagged version; a test checks it matches the newest version in the README. |
| `server/storage.py` | Every file path (`app_file`, `runtime_file`), settings, safe JSON writes, runtime folder setup. |
| `server/instruments.py` | Chooses the instrument source (`read_var`), Expedition connection, manual wind, `/api/wind`, position, wind history sampler, displayed-wind fallback. |
| `server/live_source.py` | Base for network sources: background reader, latest values with age, reconnect. |
| `server/h5000.py` | B&G H5000 websocket (GoFree protocol). |
| `server/nmea0183.py` | NMEA 0183 over TCP: sentence parser and reader. |
| `server/websocket_client.py` | Minimal websocket client for the H5000. |
| `server/course_data.py` | Course, current leg, marks, Expedition marks import, sail chart and polar parsing, settings, uploads. |
| `server/race_officer.py` | Race Officer import, auto-import polling, `/api/race_start`. |
| `server/expedition_dll.py` | Minimal direct wrapper around Expedition's `ExpDLL.dll`, and the channel numbers (`Var`). |
| `server/mfd_advertiser.py` | UDP multicast advertiser for B&G/Navico MFD browser-panel discovery. |
| `templates/index.html` | Main page's HTML only: a tab for each section, Wind & Course (with the course chart), Course legs, mark editor, imports, Race Officer controls, settings. |
| `static/index.js`, `static/index.css` | The main page's script and styles. Functions are global so the HTML's `onclick` attributes can call them. The styles are the Pwllheli Race Officer's race-document theme (paper, hairline rules, square corners, dark instrument panels). |
| `static/fonts.css`, `static/fonts/` | Archivo, Archivo Narrow and IBM Plex Mono (SIL Open Font Licence, `static/fonts/OFL.txt`), the Race Officer's fonts, served locally so the main page looks the same with no internet connection. |
| `templates/phone.html` | Phone/tablet page's HTML only. |
| `static/phone.js`, `static/phone.css` | The phone page's script and styles. |
| `templates/mfd.html` | Legacy-compatible MFD display (ES5 only; see below). Its script and styles stay inline, so the MFD's browser has one page to load. |
| `static/mojito-logo.png` | The logo in the main page's header, with a transparent background (made from `mojito-logo.jpg`, the original artwork). |
| `static/legs.js` | Leg calculations shared by all three pages (ES5): positions, route, bearing and range, TWA and tack, sail choice, target speed, bearing bar text. |
| `static/race_start.js` | Start bar shared by all three pages (ES5). |
| `server/tiles.py` | Course chart map tiles: fetched from OpenStreetMap/OpenSeaMap as they are shown, saved in `runtime/tiles/`, served from there with no internet. |
| `static/leaflet/` | Leaflet 1.9.4 (BSD 2-clause, its `LICENSE` alongside), served by the app so the chart works offline. The JavaScript tests skip it (`tests/js/harness.js`); a test can supply a stand-in `window.L`. |
| `tests/` | Test suite; see [TESTING.md](TESTING.md). |
| `install.bat`, `copy_previous_install.py` | Installing on the boat PC: Flask from the zip's `wheels/`, then settings, marks and course copied from the previous version's folder. |
| `autostart.py`, `autostart.bat` | Starting at Windows sign-in: one minimised shortcut in the Startup folder to this version's `start_app.bat`, made with WScript.Shell through PowerShell. `install.bat` runs `autostart.py --install` (asks, or moves an existing one to the new version, replacing any hand-made shortcut to a copy of the app). |
| `tools/release.py`, `make_release.bat` | Building and publishing a release; see [RELEASING.md](RELEASING.md). In git, not in the zip. |
| `LICENSE` | MIT, the standard text so GitHub recognises it. The fonts are not covered: they are under the SIL OFL (`static/fonts/OFL.txt`, and the README's Licence section). |
| `runtime/` | State the app rewrites while running. Not in git. |
| `marks.example.json`, `course.example.json` | Starting marks and course, copied into `runtime/` when missing. |

## Files and folders

Configuration stays in the app folder: `settings.json`, the sail chart, the polar
and `marks.xml`. `settings.json` is each install's own: it is written when
settings are first saved, is not in git or the release zip, and until then
`storage.DEFAULT_SETTINGS` apply (the tests start from them too). Relative paths in `settings.json` are resolved against the app
folder (`storage.resolve_user_path()`); full Windows paths also work.

Everything the app rewrites while running is in `runtime/`, reached through
`storage.runtime_file(name)`. Other modules always call these as
`storage.app_file(...)`, so the tests can point the whole app at a temporary
folder by patching that one function. JSON state is written with
`storage.write_json()`: to a temporary file, then swapped in, so a crash cannot
leave a half-written file (retried briefly if Windows reports the file in use).

| File | Written by |
| --- | --- |
| `marks.json` | Mark editor, Expedition marks import, Race Officer import. |
| `course.json` | Course editor, Race Officer import (or clear when no course is set). |
| `current_leg.json` | Prev/Next leg on any page; reset or kept by a Race Officer import. |
| `display_wind.json` | The main page, every second (fallback TWD for `/api/wind` and `/api/twd`). |
| `wind_history.jsonl` | The server's wind sampler, once a second, last hour kept. |
| `race_officer_poll_state.json` | The Race Officer poller: signatures, last check, race and start info. |
| `tiles/<layer>/<z>/<x>/<y>.png` | `server/tiles.py`, as the course chart shows each map tile (`.none` where the server has no tile). |
| `manual_wind.json` | The manual TWD/TWS typed on the Wind & Course page (used when the source is `manual`). |

At startup `storage.prepare_runtime_dir()` moves any of these left in the app folder by
v60 or earlier into `runtime/`, then copies the example marks and course in if
they are missing.

## Main page

The sections are tabs (`<nav class="tabs">`); `showView(name)` in
`static/index.js` shows one view and marks its tab active. The tab row is sticky
at the top of the screen, above the chart's Leaflet controls.

`static/index.css` is the Pwllheli Race Officer's race-document theme (colour
tokens at the top: paper, ink, rules, signal-flag colours, instrument panels),
applied to this page's markup: square corners, hairline rules, condensed
uppercase labels and buttons, monospaced figures. The wind strip and the start
bar are dark instrument panels; the start bar is attached with
`theme: "dark"` and `index.css` restyles `race_start.js`'s colours (its rules
are prefixed `body` to win over the ones the script injects). Port and
starboard use the flag red and green throughout.

The page title and version are in `<header class="appHeader">`; templates get
`app_version` from a context processor in `app.py`.

## Course and roundings

`course.json` holds the route as mark IDs separated by spaces, and a roundings
map keyed `"<leg index>:<from>-<to>"`:

| Code | Meaning | Set by |
| --- | --- | --- |
| `P` | Leave the mark to port | Course editor, Race Officer import |
| `S` | Leave the mark to starboard | Course editor, Race Officer import |
| `V` | Via a waypoint, not rounded | Race Officer import |
| `F` | Run to the finish (mark `FIN`) | Race Officer import of a shortened course |

The leg index is part of the key because courses repeat legs (`O 1 O 1`).

## Leg calculations: `static/legs.js`

Range, bearing, TWA, tack, sail choice and target speed are worked out in the
browser by `static/legs.js` (`MojitoLegs`), which all three pages load before
their own script (for the main page, `static/index.js`). Its functions take their data as arguments (marks, sail
chart, polar rows) and never read page globals or the DOM. It is ES5 so the MFD
can run it.

Each page keeps its old function names (`sailFor`, `targetSpeedInfoFor` /
`targetSpeedInfo`, `side`, `parseCourse`, ...) as one-line calls into
`MojitoLegs`, so the rest of the page code is unchanged. Display formatting
(`formatTargetBsp`, leg times, tack as `Port`/`P`) stays in each page.

Until v63 each page had its own copy of this code, and the copies drifted (v57,
and the sail chart heading bug in v61). `tests/test_js.py` still runs each
page's script and checks the three agree, and tests `legs.js` directly.

Target speed: inside the polar's range the speed is interpolated by TWA and TWS.
Tighter than the best upwind VMG angle, or deeper than the best downwind VMG
angle, the page shows the VMG target instead (`7.0 kt @ 41°`) and the leg time
uses the speed made good along the leg.

Sail choice: nearest TWS row and nearest TWA column of the sail chart. When a
heading repeats, the first matching row or column is used.

## Race Officer import

See [RACE_OFFICER_INTEGRATION.md](RACE_OFFICER_INTEGRATION.md) for the behaviour.
Code path:

```text
server/race_officer.py
start_poller()                                 background thread, every N seconds
  -> _poller_loop()
    -> import_current_if_changed()             also: Check now, Import (force=True)
      -> fetch_state_signature()               GET /public/race/state (cheap)
         unchanged and full check < 60 s old -> done
      -> get_json(/api/current_race_course)
      -> race_info()                           race, start, postponement, course_set
      -> course not set: clear_course() once per race, save state, done
      -> parse_current_payload()               marks, route, roundings from course.sailed
      -> course_signature()                    race id + route + roundings + route mark positions
         changed -> write_course()             keeps current leg on a shortening
      -> update_state()                        merge into race_officer_poll_state.json
```

Errors are merged into the saved state with `record_error()`, which keeps the
saved signature. Overwriting it would make the next good poll re-import and
reset the current leg.

`/api/race_officer/current_preview` parses without writing anything.

## Start bar

```text
/api/race_start            from race_officer_poll_state.json
  -> static/race_start.js  polls every 5 s, counts down every 1 s
```

The server sends `seconds_to_start`, so the page never parses a date (older MFD
browsers handle ISO dates inconsistently). `live` is false when auto-import is
off or the last good check is stale; the bar is then hidden. On the phone and
MFD the bar is attached with `frame: "phoneBar"` / `frame: "mfdBar"`, which
colours the whole bar and keeps it visible so it can also carry the bearings.

## Bearing bar (phone and MFD)

Both pages read the boat position from `/api/position` every second.
`MojitoLegs.bearingBar()` gives the text for two cells: the bearing and range
from the boat to the mark at the end of the current leg, and the bearing and
length of the leg after it. Each page's `renderBearings()` just writes it out.

## MFD page

`/mfd` must run in the MFD's embedded browser: no `let`/`const`, arrow
functions, template literals, `fetch`, `async`/`await`, spread or newer built-ins.
`tests/test_js.py` checks `mfd.html` and every `/static/` script it loads for these.

The bar under the leg controls shows the start status and the bearings (see
*Bearing bar* above).

MFD discovery:

```text
start_mfd_advertiser()
  -> advertiser_loop()
    -> build_mfd_payload()
    -> UDP multicast to 239.2.1.1:2053
```

See [MFD_AND_ZEUS.md](MFD_AND_ZEUS.md).

## Course chart

```text
Wind & Course tab, or any course edit
  -> renderCourseChart()          skipped while the tab is hidden
    -> renderCourseChartLeaflet() if Leaflet is available
    -> renderCourseChartSvg()     otherwise

Leaflet tile request /tiles/osm/{z}/{x}/{y}.png (and seamark)
  -> server/tiles.py tile()       saved copy under a week old -> served
    -> fetch_tile()               else from the tile server, saved in runtime/tiles/
    -> no internet                any saved copy, however old; else 404
```

The chart is framed on the course, or on every mark while there is no course.

See [COURSE_CHART.md](COURSE_CHART.md).

## Course state watcher

Race Officer auto-import changes files on the server while browser pages hold
their own copies of marks, course and current leg. `index.html` runs
`startCourseStateWatcher()` (in `static/index.js`), which polls `/api/marks`, `/api/course` and
`/api/current_leg` every 3 seconds and re-renders when they change. The phone
and MFD pages reload the course every 5–10 seconds and the current leg every
1–2 seconds.

## Instrument sources

`instruments.read_var(var)` reads a channel from the source chosen in
`settings.json` (`instrument_source`). For the H5000 and NMEA 0183,
`selected_source()` starts a `LiveSource` reader thread for the configured
address and stops it when the source or address changes; values older than
5 seconds count as missing. See [INSTRUMENTS.md](INSTRUMENTS.md).

## Expedition channels

`server/expedition_dll.py`'s `Var` holds the channel numbers. Lat, Lon, COG and SOG are 48,
49, 50 and 51: the Expedition-Python `enums.py` values these were taken from are
one low, which showed longitude as COG before v61. The DLL's age output always
equals the channel number, so the app ignores it.
