# Testing

## Running the tests

Double-click `run_tests.bat`, or from the app folder:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

Useful options: `-v` lists each test, `-k shortening` runs only tests whose
names contain *shortening*, `-f` stops at the first failure.

The suite uses Python's built-in `unittest`, so nothing extra is installed. The
page JavaScript tests need Node.js; without it they are skipped (reported as
`s`) and the rest still run.

Run the tests before copying a new version to the boat. `make_release.bat`
runs them on the exported release before it builds the zip.

## What the tests cover

| File | Covers |
| --- | --- |
| `test_ro_parse.py` | Turning Race Officer `/api/current_race_course` into marks, route and roundings: fixed course, repeated marks, compound marks, shortened course and `FIN`, waypoints, older Race Officer versions. |
| `test_ro_sync.py` | Polling: no import while the course is not set, clearing once per race, cheap signature checks, the once-a-minute full check, moved marks, keeping or resetting the current leg, network errors, preview not writing. |
| `test_api.py` | Starting with Waitress (and a second copy refused the port); the app's own API: course, marks, current leg, race start bar data, Expedition values and position, TWD fallback, sail chart and polar parsing, uploads, Expedition marks import, settings, the runtime folder and safe file writes, every URL still served, pages rendering: the main page's tabs and sections, the version on every page matching the README, the bundled fonts and the transparent logo. |
| `test_instruments.py` | Instrument sources: NMEA 0183 sentences and H5000 messages captured from the boat, the websocket client, the network readers against local fake plotter and H5000 servers (including reconnecting and stale data), choosing the source, and its settings. |
| `test_install.py` | `copy_previous_install.py`: finding the most recently used earlier version, copying settings, state and uploaded files, saved map tiles, v60-style state in the app folder, not copying over a version used since, answering no. |
| `test_tiles.py` | Course chart map tiles: fetched once and saved, served from the saved copy (however old) with no internet, refreshed after a week, remembered missing seamark tiles, leaving the servers alone for a minute after a failure, the User-Agent, cache headers, the page using the local Leaflet and the app's tile URLs. |
| `test_release.py` | `tools/release.py`: version and names, release notes from the README, what the zip must and must not hold. Skipped on an installed copy, which has no `tools/`. |
| `test_js.py` | Page JavaScript in Node: the Course legs, phone and MFD pages agree on sail, target speed and tack over a grid of TWA/TWS; bearings and distances match the Race Officer app's own leg figures; position formats; every start bar state; the phone and MFD bearings bars, and that they agree; the shared `legs.js` directly; the MFD page and the scripts it loads use only JavaScript older MFD browsers support; the course chart framed on the course, or on every mark with no course, each mark labelled once, legs numbered in circles (shared when sailed twice), and their numbers to the right of travel. |

## How the tests are isolated

`tests/helpers.py` gives each test (`AppTestCase`) its own temporary copy of the
app folder (by patching `server.storage.app_file`), so `runtime/` and
`settings.json` are never touched. Its settings start from
`storage.DEFAULT_SETTINGS`, with the fake Race Officer's address. Expedition and the Race Officer app are
replaced by fakes (patching `server.instruments.read_var` and
`server.race_officer.get_json`):

- `FakeExpedition.values` holds the channel values; set one to `None` for "no data".
- `FakeRaceOfficer.make(...)` builds a Race Officer reply from
  `tests/fixtures/ro_current_race_course.json` (a real reply from Race Officer
  v1.010), with options for course set, start time, postponement, shortening,
  waypoint and race id. Set `.signature` to change what `/public/race/state`
  reports, and `.fail = True` to simulate the network being down.

`tests/js/harness.js` runs a page's scripts in Node with a stub browser: no
network and no timers, so page start-up code cannot interfere. `run_js()` in
`helpers.py` runs a page and returns the value of an expression.

## Adding a test

- A bug fix: add a test that fails without the fix first.
- A change to the leg calculations: make it in `static/legs.js`, in ES5, and add
  a test to `SharedLegsTests`.
- A new Race Officer field: add it to `FakeRaceOfficer.make()` if a test needs it.
- If the Race Officer reply format changes, save a fresh reply over the fixture
  and rerun the tests.
