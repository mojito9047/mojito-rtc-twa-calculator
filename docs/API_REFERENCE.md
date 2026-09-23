# API reference

All endpoints are served on port 8765 by `app.py` and the modules in `server/`
(named under each heading). Responses are JSON with
`ok` and, on failure, `error`; every response carries no-cache headers.

## Pages

| Path | Page |
| --- | --- |
| `/` | Main app, a tab for each section: Wind & Course (with the course chart), Course legs, Edit marks, Import Expedition marks, Race Officer import, Settings. |
| `/phone` | Phone/tablet view. |
| `/mfd` | Legacy-compatible MFD view. |

Each page shows the app version (`VERSION` in `server/__init__.py`).

## Course and marks

`server/course_data.py`

### `GET /api/course` · `POST /api/course`

The active course: `course` (mark IDs separated by spaces) and `roundings`
(`{"<leg index>:<from>-<to>": "P"|"S"|"V"|"F"}`; see
[DEVELOPER_NOTES.md](DEVELOPER_NOTES.md#course-and-roundings)). POST takes the
same fields; other rounding values are dropped. An empty course stays empty.

### `GET /api/marks` · `POST /api/marks`

The marks: a list of `{id, name, lat, lon}`. Positions are strings in
decimal degrees or degrees and minutes (`50 39.330N`, `50° 39.33'N`); the Edit
marks page saves degrees and decimal minutes, Race Officer imports decimal degrees. POST takes `{"marks": [...]}`:
IDs are upper-cased, must be unique, and at least two marks are required.

### `GET /api/current_leg` · `POST /api/current_leg`

The current leg index shared by all displays, `{"current_leg": 0}`. Negative
values are stored as 0.

## Instruments and wind

`server/instruments.py`

Values come from the selected instrument source (see [INSTRUMENTS.md](INSTRUMENTS.md)).

### `GET /api/instruments`

The selected source: `kind` (`expedition`, `h5000`, `nmea0183`, `manual`), `label`,
`connected`, `error`, and for the H5000 and NMEA sources `host`, `port`,
`last_message_age` and `channel_ages` (seconds since each channel last arrived);
for NMEA 0183 also `channel_origins`, the talker + sentence each channel is taken
from (e.g. `"Hdg": "SDVHW"`).

### `GET /api/expedition`

`data` with `Bsp`, `Twd`, `Tws`, `Hdg`, `Cog`, `Sog` from the selected source
(the name is historical); `errors` per channel. `ok` is false if any channel
errors, but valid channels are still returned.

### `GET /api/wind` · `POST /api/wind`

GET: the wind every display uses: `twd`, `tws`, `ok`, `manual` (true when the
source is manual wind), `source` (the instrument source, `manual`, or
`display_fallback` when the source had no TWD and the TWD last shown on the
Course legs page is used), `warning`, `error`, and `manual_wind`, the saved
manual `{twd, tws}`.

POST: sets the manual wind, `{"twd": 0-360, "tws": 0-80}` (either or both).
Used while the instrument source is `manual`.

### `GET /api/twd`

TWD from the selected source (`source` is the `instrument_source` setting).
If it is unavailable, the TWD last shown on the Course legs page
(`/api/display_wind`), with `warning`. The pages use `/api/wind` instead.

### `GET /api/position`

Boat position from the selected source in decimal degrees: `lat`, `lon`. `ok` is
false, with `lat`/`lon` null, when there is no valid position (none, out of range,
or 0,0).

### `GET /api/display_wind` · `POST /api/display_wind`

The TWD/TWS last shown on the Course legs page, which posts it every second.
Used as the fallback for `/api/wind` and `/api/twd`.

### `GET /api/wind_history?minutes=5`

TWD/TWS samples (`t`, `twd`, `tws`), one a second, for the last 1–60 minutes
(default 5), plus `current`, the latest sample.

### `GET /api/health`

Whether the selected source is connected: `ok`, `source`, `connected`, `error`;
`expedition_connected` says whether the Expedition DLL has been loaded.

## Sail chart and polar

`server/course_data.py`

### `GET /api/sailchart`

The sail chart from the settings: `twas` (column headings) and `rows`
(`{tws, sails: [...]}`, one sail per heading, blank where the chart is blank).

### `GET /api/polar`

The polar from the settings: `rows` of `{tws, points: [{twa, bsp}, ...]}`,
sorted by TWS.

## Settings and files

`server/course_data.py`

### `GET /api/settings` · `POST /api/settings`

`sailchart_file`, `expedition_marks_file`, `polar_file`,
`race_officer_api_base`, `race_officer_poll_enabled`,
`race_officer_poll_interval_seconds` (5–300), `instrument_source` (`expedition`,
`h5000`, `nmea0183`, `manual`), `h5000_host`, `h5000_port`, `nmea_host`, `nmea_port`
(1–65535). File names are relative to the app folder or full paths; none may be
blank, nor the address of the selected network source. `race_officer_api_base`
must start with `http://` or `https://`; a trailing `/` is removed.
Without a `settings.json` (a fresh install) the defaults apply: Expedition, the
club's Race Officer server `https://pro.pwllhelisailingclub.org` with
auto-import off, and the sail chart, polar and marks XML in the app folder.

### `GET /api/file_status`

Full paths of the sail chart, marks XML and polar files, and whether each exists.

### `POST /api/upload_file`

Multipart form: `type` (`sailchart`, `polar` or `marks`) and `file`. Saves the
file in the app folder under a cleaned name and selects it in the settings.
Marks files must be `.xml`.

### `GET /api/expedition_marks/groups`

Mark groups in the Expedition marks XML, with counts. Marks with no group are
listed as `(no group)`.

### `POST /api/expedition_marks/import`

`{"group": "...", "replace": true|false, "prefix": ""}`. Imports that group's
marks, IDs made from the mark names (upper-case, letters and digits, up to 10,
plus the optional prefix). `replace: false` adds them to the existing marks,
renaming any ID already in use.

## Race Officer

`server/race_officer.py`. See [RACE_OFFICER_INTEGRATION.md](RACE_OFFICER_INTEGRATION.md).

### `GET /api/race_officer/base` · `POST /api/race_officer/base`

The Race Officer address, `{"base": "https://..."}` (the same setting as
`race_officer_api_base` in `/api/settings`; the pages set it through `/api/settings`). Must start with
`http://` or `https://`.

### `GET /api/race_officer/current_preview`

Reads and parses the current Race Officer course and returns `course_name`,
`marks_count`, `course`, `roundings`, `race` and `course_set`. Changes nothing.

### `POST /api/race_officer/import_current`

Imports the current course now, even if unchanged. `400` while the race officer
has not set a course.

### `POST /api/race_officer/poll_once`

One poll: imports only if the course changed. Returns `changed`, `course_set`,
`course`, `race`. On a network error the saved course signature is kept.

### `POST /api/race_officer/poll_config`

`{"enabled": true, "interval_seconds": 10, "base": "..."}`. Turns auto-import on
or off, starting the server poller and running a first check when enabled.

### `GET /api/race_officer/poll_status`

`enabled`, `interval_seconds` and `state`, the saved poll state (last check,
error, imported course, race and start info, whether a course is awaited).

### `GET /api/race_start`

The start bar's data, from the last poll:

| Field | Meaning |
| --- | --- |
| `live` | False when auto-import is off, nothing has been polled, or the last good check is stale. The bar is hidden. |
| `race` | `race_name`, `course_set`, `course_no`, `course_label`, `first_warning_time`, `first_start_time`, `postponed`, `postponement_flag`, `postponement_ends_at`, `shortened`, `shortened_label`, `race_finished`. |
| `seconds_to_start` | Seconds to the first start, negative once started, `null` with no start time. |
| `start_clock` | First start as `HH:MM:SS`, or `""`. |
| `postponement_ends_clock` | When AP comes down as `HH:MM`, or `""`. |
| `age_seconds`, `server_now`, `error` | For diagnostics. |

## MFD

`app.py`

### `GET /api/mfd_status`

The PC's IPv4 addresses and the MFD advertisement payloads multicast to
`239.2.1.1:2053`.
