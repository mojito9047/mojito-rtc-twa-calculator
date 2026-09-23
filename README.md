# Mojito RTC TWA Calculator

Race-day tactics for **Mojito**, a J/122 racing round the cans at Pwllheli.

A round-the-cans course is announced only minutes before the start, and the crew then has to work out the race: where the course goes, what wind angle each leg will be sailed at, which sail each leg needs, and so where the sail changes come. This app works all of that out as soon as the course is known, and keeps it up to date as the wind shifts.

- **The course in quickly.** Tap in the marks as the course is announced, choosing a port or starboard rounding for each. When the race committee is using the Pwllheli Race Officer app, the course arrives by itself the moment they set it, along with the start time, postponements and any shortening.
- **Every leg worked out.** Bearing, range, true wind angle and tack, the sail from Mojito's sail chart, the target boat speed from the polar, and the expected time for each leg. Before the course is known, **Show all legs** gives the same figures for every pair of marks.
- **Whatever instruments are working.** Live wind and position from Expedition, the B&G H5000 or a plotter's NMEA 0183 feed, or the wind typed in by hand when there are no instruments.
- **On every screen aboard.** The Expedition PC, a tablet or phone, and the B&G chart plotter, where the app has its own tile. The displays share the current leg, so stepping on at a mark updates them all. The phone and plotter also show the bearing to the next mark and the bearing of the leg after it.
- **Marks ready before going afloat.** Type them in, in degrees and minutes as they appear on the chart, or import them from an Expedition marks XML file. A Race Officer course brings its own mark positions.

The app runs on the Expedition PC and the other screens open it over the boat network. Nothing needs the internet except the Race Officer app (when it is reached over the internet) and the course chart's map tiles the first time an area is viewed: the app keeps every tile it shows, so an area looked at before going afloat is on the chart without a connection.

## Race day

1. **Before going out.** Start the app (see [Installing](#installing)). Check that **Settings → Instruments** shows the instruments connected, and that **Edit marks** has the day's marks, importing them from Expedition if needed. If the committee is using the Race Officer app, turn on auto-import on the **Race Officer import** page. While there is still internet, look over the race area on the **Wind & Course** chart, zooming in as far as you will want on the water, so its map is saved.
2. **When the course is announced.** With auto-import on, it appears by itself. Otherwise enter it on **Wind & Course**, using the P and S buttons beside each mark, and check it on the chart below.
3. **Before the start.** **Course legs** shows the sail for every leg, so the crew can plan the sail changes. The start bar counts down to the first start.
4. **Racing.** At each mark, press **Next leg** on any display. The phone and plotter show the bearing to the next mark, and all the figures follow the wind as it shifts.

## Installing

Download `mojito_rtc_twa_calculator_vNN.zip` from the [latest release](https://github.com/mojito9047/mojito-rtc-twa-calculator/releases/latest) before going to the boat. Nothing in the installation needs the internet: the zip carries its own copy of Flask. The Expedition PC needs Python 3.11 or later ([python.org](https://www.python.org/downloads/windows/)).

1. Unzip it on the Expedition PC, into the folder that holds any earlier version, so the versions sit side by side (for example `Documents\Mojito\mojito_rtc_twa_calculator_v71`).
2. Double-click `install.bat` in the new folder. It sets up Python's environment, then looks for the most recently used earlier version beside it and offers to copy its settings, marks and course across. Answer `Y` to carry on where the last version left off. It then asks whether to start the app automatically when you sign in to Windows (see [Starting automatically](#starting-automatically)); if that is already on, it moves it to the new version without asking.
3. Close the earlier version's `start_app.bat` window if it is running (both use port 8765; the new one will not start beside it).
4. Double-click `start_app.bat` in the new folder. Its window shows the addresses to open, on this PC and from other devices, and must stay open while the app is in use.
5. Open the app, and check the version at the top right of the page:

```text
http://localhost:8765
```

From another device on the same network:

```text
http://<Expedition-PC-IP-address>:8765
```

You may need to allow Python through Windows Firewall the first time.

### Starting automatically

With auto-start on, signing in to Windows starts the app, minimised on the taskbar (open its window for the version and addresses). It does not matter whether Expedition starts before or after it. `install.bat` offers it, and keeps it on the newest version at each upgrade; to turn it on or off later, double-click `autostart.bat` in the version you want. It is a shortcut in your Windows Startup folder; it starts at sign-in, not at power-on, so a PC with a password starts the app once someone signs in.

To check a new version on the PC before racing, double-click `run_tests.bat` (see [Testing](#testing)). Once the new version is working, the earlier version's folder can be deleted.

With `Y`, the installer copies `settings.json`, the `runtime` folder (marks, course, current leg, manual wind, Race Officer state, saved map tiles) and any sail chart, polar or marks file chosen in Settings that the new version does not have. If the earlier folder's sail chart or polar has been edited, the installer says so; copy it across by hand to keep the edits.

## Pages

The main page (`/`) has a tab for each section:

| Tab | For |
| --- | --- |
| **Wind & Course** | The wind in one strip (typed in here when the source is *Manual wind*); the course editor, with a P and an S button beside each mark; and the course chart, which redraws as the course is built. |
| **Course legs** | The main race page: the wind, the start bar, and each leg's rounding, range, bearing, TWA, sail, target boat speed, leg time, tack and point of sail, with the current leg highlighted. **Show all legs** switches to a grid of every mark-to-mark leg. |
| **Edit marks** | The marks. Positions are shown and saved in degrees and decimal minutes, e.g. `50 39.330N` and `01 55.170W`. |
| **Import Expedition marks** | Imports a group of marks from an Expedition `marks.xml` file, replacing the marks or adding to them. |
| **Race Officer import** | Previews or imports the Race Officer course, and turns auto-import on or off. |
| **Settings** | In three sections, **Instruments** (source and addresses), **Race Officer** (address) and **Files** (sail chart, polar, marks XML), with a save bar that stays on screen and flags unsaved changes. |

Two more pages for the other screens:

| Page | For |
| --- | --- |
| **Phone** (`/phone`, or **Open phone view** on Course legs) | Phones and tablets: start bar, bearing to the next mark and of the next leg, course table, and a wind history graph (in portrait). |
| **MFD** (`/mfd`, the *Mojito RTC* tile on the plotter) | B&G/Navico chart plotters: start bar, bearing to the next mark and of the next leg, course table. |

The main page follows the look of the Pwllheli Race Officer app. The phone and MFD pages are dark, for use on deck.

Every page shows the app version: at the top right of the main page, beside the title on the phone, and in the top corner of the MFD next to the time of the last update.

## Start bar

The Course legs, phone and MFD pages show the Race Officer's start information while auto-import is on:

- `Start in 4:59` counting down to the first start (amber in the last minute), then `Racing +12:34`
- `No start time set`, `Course not set yet`
- `AP over H — start postponed` and `AP down at 14:30`
- `Course shortened at 4 (rounding 1)`
- `Race finished`

The countdown is to the **first** start; on a day with several starts, Mojito's own start may be later. On the phone and MFD the bar also shows the bearing and range from the boat to the next mark, and the bearing of the leg after it.

## Files

Configuration, in the app folder:

| File | Purpose |
| --- | --- |
| `settings.json` | Instrument source, Race Officer address and polling, file paths. Written when settings are first saved; not in git or the release zip. A fresh install starts from the defaults (Expedition, the club's Race Officer server, the files below); `install.bat` copies the previous version's. |
| `SailChart J122 North.txt` | Sail selection grid. |
| `J122.txt` | Polar. |
| `marks.xml` | Expedition marks export, for **Import Expedition marks**. |
| `marks.example.json`, `course.example.json` | Starting marks and course for a fresh install. |

State the app rewrites while running, in `runtime/` (not tracked in git; created at startup):

| File | Purpose |
| --- | --- |
| `runtime/marks.json` | Active marks. |
| `runtime/course.json` | Active course and roundings. |
| `runtime/current_leg.json` | Current leg, shared by all displays. |
| `runtime/manual_wind.json` | The TWD and TWS typed in for *Manual wind*. |
| `runtime/display_wind.json` | TWD/TWS last shown on the Course legs page (fallback when the instruments have no TWD). |
| `runtime/wind_history.jsonl` | Rolling one-hour TWD/TWS history. |
| `runtime/race_officer_poll_state.json` | Last Race Officer poll: status, course signature, race and start info. |
| `runtime/tiles/` | Course chart map tiles, saved as they are shown, for use with no internet. Safe to delete (they are fetched again when next viewed online). |

`marks.json` and `course.json` are copied from the example files when missing. Files left in the app folder by v60 or earlier are moved into `runtime/` automatically.

## Instruments

Live wind and position come from one of four sources, chosen under **Settings → Instruments**:

| Source | Connection |
| --- | --- |
| **Expedition** on this PC (default) | Expedition's `ExpDLL.dll`, no setup |
| **B&G H5000** | Websocket, default `192.168.15.149` port `2053` |
| **NMEA 0183 over IP** from a plotter | TCP, default `192.168.15.166` port `10110` |
| **Manual wind** | No instruments: TWD and TWS are typed in on the **Wind & Course** page and used by every display, which marks the wind as manual. There is then no boat position, so no bearing to the next mark. |

Directions are used as degrees true and speeds as knots from every source, whether the displays are set to true or magnetic. The Settings page shows whether the source is connected and which values are arriving. If a source stops sending, its values count as missing after 5 seconds and the app reconnects by itself.

If the source's TWD is unavailable, the TWD last shown on the Course legs page is used, so the MFD does not drop to 0°.

Details, including which H5000 items and NMEA sentences are used: [docs/INSTRUMENTS.md](docs/INSTRUMENTS.md).

## Sail chart

The sail chart is a tab-separated text file:

```text
<TAB>36<TAB>39<TAB>42<TAB>50
12<TAB>J2<TAB>J2<TAB>J1<TAB>J1
11<TAB>J2<TAB>J1<TAB>J1<TAB>J1
```

- the first row holds the TWA headings
- the first column holds the TWS values
- each cell holds a sail name, for example `J1`, `J2`, `A0`, `A2`; blank cells are allowed and show `—`
- the nearest TWS row and nearest TWA column are used; if a heading repeats, the first one is used
- after editing the file, refresh the page

`SailChart J122 North.txt` currently has two columns headed 36°, which differ only at 16 kt (J3 and J2). The first is probably meant to be a lower angle.

## Polar

The polar file is Expedition-style: the first column is TWS, followed by TWA / target boat-speed pairs. Target speed is interpolated by TWS and TWA. Tighter than the best upwind VMG angle, or deeper than the best downwind VMG angle, the page shows the VMG target instead (for example `7.0 kt @ 41°`), and the leg time uses the speed made good along the leg.

## Race Officer import

The app reads the Race Officer public API (Race Officer v1.011 and later; see its `docs/PUBLIC_API.md`). No login is needed. Set its address under **Settings → Race Officer**, for example:

```text
https://pro.pwllhelisailingclub.org
```

- **Nothing is imported until the race officer sets a course.** A new race carries a placeholder course number; while no course is set, the course showing here is cleared once and the pages show *No course set*.
- The route imported is the course **as it is being sailed**. After a shortening it ends with a run to the middle of the finish line, added as mark `FIN`, and the boat keeps its current leg.
- Waypoints are kept as route points, shown as **Via** legs.
- Repeated marks and port/starboard roundings are kept; compound marks are imported as their corners.
- Auto-import checks the Race Officer's cheap state signature every few seconds and fetches the full course only when it changes, and at least once a minute.

The page buttons:

- **Preview current course** — reads the current course without changing anything here
- **Import current course** — imports it now (refused while no course is set)
- **Auto-import when Race Officer course changes** — turns polling on or off
- **Poll every** — interval in seconds, 5 to 300
- **Check now** — one poll, importing only if changed

Details: [docs/RACE_OFFICER_INTEGRATION.md](docs/RACE_OFFICER_INTEGRATION.md).

## Course chart

On the **Wind & Course** page, under the course editor; it redraws as marks are added, roundings chosen, or the course typed, undone or cleared. With no course yet it shows every mark, then zooms in to the course as it is built.

- each mark on the course is a dot with its ID, labelled once however often it is rounded, with *Start* and *Finish*; marks not on the course are small grey dots
- the legs are numbered in circles, so a leg number cannot be taken for a mark; a leg sailed twice shows both numbers (`4, 7`)
- each leg is coloured by the rounding at its end: red port, green starboard, dark for start, via or unspecified
- the run to the finish of a shortened course is dashed
- arrows show the direction of each leg
- on OpenStreetMap with the OpenSeaMap seamarks; each map tile shown is saved, so without an internet connection the map is still there wherever it has been viewed before (anywhere else is blank)

Details: [docs/COURSE_CHART.md](docs/COURSE_CHART.md).

## B&G / Navico MFD integration

The app advertises itself as an MFD browser panel by UDP multicast to `239.2.1.1:2053`, so it appears on the plotter as the *Mojito RTC* tile. The tile opens `/mfd`, which uses only older JavaScript so the MFD's embedded browser can run it.

Details: [docs/MFD_AND_ZEUS.md](docs/MFD_AND_ZEUS.md).

## API endpoints

The main ones:

| Endpoint | Purpose |
| --- | --- |
| `/api/course` | Read/save the active course and roundings. |
| `/api/marks` | Read/save the marks. |
| `/api/current_leg` | Read/save the shared current leg. |
| `/api/wind` | The wind every display uses (instruments or manual), and the manual wind (POST to set it). |
| `/api/expedition` | Current instrument values (from whichever source is selected; the name is historical). |
| `/api/twd` | TWD, with the displayed-wind fallback. |
| `/api/position` | Boat position from the instruments. |
| `/api/instruments` | Which instrument source is in use and whether data is arriving. |
| `/api/wind_history` | Rolling TWD/TWS history. |
| `/api/sailchart`, `/api/polar` | The parsed sail chart and polar. |
| `/api/settings` | Read/save settings. |
| `/api/race_start` | Start bar data from the last Race Officer poll. |
| `/api/race_officer/current_preview` | Preview the Race Officer course. |
| `/api/race_officer/import_current` | Import the Race Officer course now. |
| `/api/race_officer/poll_config` | Turn auto-import on or off. |
| `/api/race_officer/poll_status` | Polling status. |
| `/api/race_officer/poll_once` | Run one poll. |
| `/api/mfd_status` | MFD advertisement payloads. |
| `/api/health` | Whether the instrument source is connected. |
| `/tiles/<layer>/<z>/<x>/<y>.png` | Course chart map tiles (`osm`, `seamark`), from the saved copy or the internet. |

All endpoints, with their fields: [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Testing

Double-click `run_tests.bat`, or:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

The tests use fakes for Expedition and the Race Officer app, and a temporary copy of the app folder, so they can run at any time without touching the live course. The page JavaScript tests need Node.js and are skipped without it. Details: [docs/TESTING.md](docs/TESTING.md).

## Troubleshooting

### Which version is running?

The version is at the top right of the main page, beside the title on the phone, and in the top corner of the MFD. If a screen shows an older version than the main page, reload it.

### The pages show *No course set*

The race officer has not set a course for the current race yet (the start bar says *Course not set yet*). It appears as soon as they do. A course can still be entered by hand on **Wind & Course**.

### Race Officer preview or import does nothing

Check the address under **Settings → Race Officer**: with auto-import on, the status line there says whether the last check worked. Then click **Preview current course** on the Race Officer import page; the status box should show the race and course, or say that no course is set yet.

### The start bar is missing

It only shows while Race Officer auto-import is on and the Race Officer app has answered in the last minute or two.

### The phone or MFD shows *No GPS position*

The instrument source has no position (or the source is *Manual wind*). Check its GPS input.

### No wind, or *Live TWD unavailable*

Open **Settings → Instruments**: the status line says whether the source is connected and what it is receiving. For the H5000 or a plotter, check the address and port, and that this PC is on the boat network. Switch to another source if one is down, or to *Manual wind* if none is working.

### The course chart map is blank

Without the internet the chart only has the map where it has been viewed before, at the zoom levels viewed; elsewhere it is blank, but the marks, legs and roundings are still shown. Before going afloat, look over the race area on the chart at the zooms you will want. The saved tiles are in `runtime/tiles/`.

### `start_app.bat` says *Is the app already running?*, or the page is still the old version

Another version (or another copy) is still running on port 8765. Close its `start_app.bat` window (look on the taskbar: with auto-start it starts minimised), then start the new one again. If an old version keeps starting when you sign in, double-click `autostart.bat` in the new version.

### The MFD shows an old course

The app tells the MFD not to cache anything (since v47). If it still shows an old course or an old version number, close the tile and open it again.

## Developer notes

1. `app.py` starts the app; the `/api/...` endpoints are in `server/`: storage, instruments (with the H5000 and NMEA 0183 readers), course data and the Race Officer import. The pages read and write through them.
2. Leg calculations run in the browser, in `static/legs.js`, which all three pages share. It is ES5 so the MFD can run it.
3. Server threads sample the wind once a second, poll the Race Officer app and advertise the MFD panel.
4. Race Officer imports write `runtime/marks.json` and `runtime/course.json`, and keep or reset `runtime/current_leg.json`.
5. The version shown on the pages is `VERSION` in `server/__init__.py`. Bump it, and add a section below, with each tagged version; a test checks the two match.
6. Releases are built and published with `make_release.bat`: [docs/RELEASING.md](docs/RELEASING.md).

More: [docs/DEVELOPER_NOTES.md](docs/DEVELOPER_NOTES.md).

## Licence

MIT: see [LICENSE](LICENSE). The bundled fonts (Archivo, Archivo Narrow, IBM Plex Mono) are not covered by it: they are under the SIL Open Font Licence ([static/fonts/OFL.txt](static/fonts/OFL.txt)). The main page's styling comes from the Pwllheli Race Officer app by CapeNet Ltd. The course chart uses [Leaflet](https://leafletjs.com) 1.9.4 (BSD 2-clause, [static/leaflet/LICENSE](static/leaflet/LICENSE)); the map is © OpenStreetMap contributors and the seamarks © OpenSeaMap contributors. The release zip also carries Flask (BSD 3-clause) and Waitress (ZPL 2.1) as wheels.

## Version history

Each version from v71 on is a [release on GitHub](https://github.com/mojito9047/mojito-rtc-twa-calculator/releases), with its zip. Earlier versions, from before the app was published: [docs/EARLIER_VERSIONS.md](docs/EARLIER_VERSIONS.md).

### v71

- Releases: `make_release.bat` builds `mojito_rtc_twa_calculator_vNN.zip` from the tagged version, runs the tests on exactly what will ship, and publishes it on GitHub ([docs/RELEASING.md](docs/RELEASING.md)).
- Published at [github.com/mojito9047/mojito-rtc-twa-calculator](https://github.com/mojito9047/mojito-rtc-twa-calculator) under the MIT licence, with each version's zip on the Releases page.
- The zip carries Flask and its dependencies (`wheels`), so `install.bat` needs no internet. It then offers to copy the settings, marks and course from the most recently used earlier version beside it (`copy_previous_install.py`).
- `settings.json` is no longer in git or the zip: it belongs to each install. A fresh install starts from the defaults, now with the club's Race Officer server (`https://pro.pwllhelisailingclub.org`) as the address.

### v72

- `LICENSE` is the standard MIT text, so GitHub shows the repository as MIT licensed. The note that the bundled fonts are under the SIL Open Font Licence is in the README's Licence section and `static/fonts/OFL.txt`.

### v73

- Course chart: with no course set, it now shows every mark, framed to fit them all, instead of the message *Enter or import a course with at least two valid marks*. It zooms in to the course once the second mark is added.
- Course chart labels: each mark on the course is labelled once with its ID (plus *Start* / *Finish*) beside a dot on its exact position, and the legs are numbered in circles. Before, a label such as `6. 3` (the sixth point, mark 3) read as two mark numbers, and a mark rounded twice showed only its last label. Clicking a mark lists the legs that end there and how it is rounded.
- Course chart without the internet: Leaflet is now part of the app (`static/leaflet/`), and the app keeps every map tile the chart shows (`runtime/tiles/`), so the map is there on the water wherever it was viewed with a connection. Tiles are refreshed weekly when online; `install.bat` brings them across to a new version.
- The app is served by Waitress instead of Flask's own development server, so it no longer starts with *WARNING: This is a development server*. The `start_app.bat` window shows the version and the addresses to open. A second copy, or a new version started while an earlier one is still running, now stops with *Is the app already running?* instead of sharing the port.
- Waitress is a new requirement: installing from the zip includes it, but a git checkout's `.venv` needs `install.bat` run again.

### v74

- The version history in this README starts at v71, the first release published on GitHub, so it matches the Releases page. The notes for earlier versions are in [docs/EARLIER_VERSIONS.md](docs/EARLIER_VERSIONS.md).

### v75

- The app can start automatically when you sign in to Windows. `install.bat` asks, and at each upgrade moves auto-start to the new version without asking, so the old version is never the one that starts; a shortcut made by hand to an earlier version is replaced. `autostart.bat` turns it on or off later. See [Starting automatically](#starting-automatically).
