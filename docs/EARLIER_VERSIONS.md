# Earlier versions

The versions before v71, from before the app was published on GitHub. v71 was
the first public release; it and every later version are in the README's
[version history](../README.md#version-history) and on the
[Releases page](https://github.com/mojito9047/mojito-rtc-twa-calculator/releases).

## Before v60

- v40 removed Expedition route/mark sending.
- v41–v44 added B&G/Navico MFD advertisement; v45 the legacy `/mfd` page.
- v47 fixed the MFD showing a stale course; v48 made long MFD courses scroll.
- v49–v51 added Race Officer current-course import; v52 the Course chart; v53 auto-import polling and chart arrows; v54 fixed polling settings being lost.
- v56 made the Course legs page refresh after an auto-import.
- v57 made `/mfd` use the same TWD, partial Expedition data and VMG logic as the main page.
- v59 rolled back v58, and `/api/twd` falls back to the TWD shown on the Course legs page.

## v60

Uses the Race Officer public API from Race Officer v1.011.

- No import until the race officer has set a course; **Import current course** refuses while none is set.
- Shortened courses: imports the course as sailed, ending at mark `FIN` (dashed on the chart), keeping the current leg.
- Waypoints shown as **Via** legs.
- Polling checks `/public/race/state` and fetches the full course only when it changes, and at least every 60 seconds.
- Start bar on the Course legs, phone and MFD pages.
- Fixed: a failed poll reset the current leg to 0 on the next good poll.
- Fixed: **Preview current course** imported the course.
- Fixed: the Course chart opened zoomed in on one mark with no map tiles, under a stale "no course" message.
- `marks.json`, `course.json` and `current_leg.json` no longer tracked in git; example files added.

## v61

- No course shown while the race officer has not set one: the course showing is cleared once per race.
- MFD: heading removed; the bar shows the bearing and range to the next mark (`/api/position`) and the bearing of the next leg.
- Runtime state moved to `runtime/`.
- Test suite (`tests/`, `run_tests.bat`, [docs/TESTING.md](TESTING.md)).
- Fixed: Lat, Lon, COG and SOG read from the wrong Expedition channels, so COG showed longitude and SOG showed COG.
- Fixed: the next race over the same course kept the previous race's current leg.
- Fixed: the MFD chose a different sail from the other pages where the sail chart repeats a TWA heading.
- Fixed: uploading a sail chart, polar or marks file failed after saving the file, leaving the setting unchanged.
- Fixed: re-saving an imported course dropped its Via and Finish legs.

## v62

- Phone: the bar now shows the bearing and range to the next mark and the bearing of the next leg, as on the MFD. On a narrow portrait screen the start status takes the top row and the two bearings sit side by side below it.

## v63

- Refactor: the leg calculations, copied into each of the three pages until now, are in one shared script, `static/legs.js`. No calculation changed: every page gives the same answers as before across the whole test grid.

## v64

- Refactor: `app.py` split into `server/`: `storage.py` (paths, settings, JSON files), `instruments.py` (Expedition), `course_data.py` (course, marks, sail chart, polar, settings, uploads) and `race_officer.py`. `expedition_local.py` and `mfd_advertiser.py` moved there as `server/expedition_dll.py` and `server/mfd_advertiser.py`. Every URL is unchanged.
- State files are written safely (to a temporary file, then swapped in), so a crash cannot leave a half-written course.

## v65

- Refactor: the main page's inline JavaScript and CSS moved out of `templates/index.html` (now HTML only) into `static/index.js` and `static/index.css`. No behaviour change.

## v66

- Refactor: the phone page's inline JavaScript and CSS moved into `static/phone.js` and `static/phone.css`; `templates/phone.html` is now HTML only. No behaviour change.

## v67

- Instrument source is configurable on the Settings page: Expedition, the B&G H5000 websocket, or NMEA 0183 over IP from a plotter ([docs/INSTRUMENTS.md](INSTRUMENTS.md)). New `/api/instruments` status endpoint.
- NMEA 0183: each value comes from one sentence and talker in a fixed order of preference (e.g. heading from `HDT`, then `VHW`, then `HDG`), falling back only when the one in use goes quiet for 3 seconds, so a value cannot flip between two devices.
- Fixed: two saves of the same file at the same moment could make one fail (seen as an occasional 400 from `/api/display_wind`). Each save now has its own temporary file.

## v68

- One Race Officer address, set under **Settings → Race Officer** (with a connection status line); the Race Officer import page shows it. Previously the import page had its own copy of the setting and saved it before every preview, import and 10-second check.
- Settings page in three sections (Instruments, Race Officer, Files) with a save bar that stays on screen, an *Unsaved changes* note, and *Discard changes*; switching tabs no longer loses unsaved edits.

## v69

- **Manual wind** is a fourth instrument source (**Settings → Instruments**), for when no instruments are available. The TWD and TWS are then typed in on the **Wind & Course** page, saved straight away, and used by the Course legs, phone and MFD pages, which show *Manual wind* / *MANUAL*. This replaces the old "Use live TWD" checkbox; TWS can now be entered by hand too.
- The course chart is on the **Wind & Course** page, under the course editor, and redraws as the course is built. The separate Course chart tab is gone.
- The list of marks under the course editor is gone (the mark buttons stay), and so is the Marks card on the Course legs page.
- Wind & Course: the wind is one compact strip and the course editor is full width, so the chart below is in view.
- Edit marks shows and saves positions in degrees and decimal minutes, as sailors write them (`50 39.330N`, `01 55.170W`), to three decimals of a minute so Race Officer positions stay exact. Other formats (`50° 39.33'N`, decimal degrees) are still accepted when typed; a position that cannot be read is named in the error. The course chart's mark popups use the same format.
- The phone and MFD take their wind from the new `/api/wind`, like the Course legs page.
- The main page's title is now *RTC TWA Calculator*, without the description paragraph under it.

## v70

- The main page uses the Pwllheli Race Officer's look: paper background, ruled headings and tables, square condensed buttons, monospaced figures, and dark instrument panels for the wind strip and start bar. Port and starboard use the signal-flag red and green.
- Sections are tabs (Wind & Course, Course legs, Edit marks, imports, Race Officer, Settings) instead of a row of buttons. The tab row stays at the top of the screen when the page scrolls.
- The fonts are part of the app, so the page looks the same on the boat with no internet connection.
- The Mojito logo has a transparent background (`static/mojito-logo.png`), so it sits on the page instead of in a white box.
- Wind & Course: the line of instrument readings under the wind (TWD, TWS, BSP, HDG, COG, SOG) is gone, so the wind strip is one row.
- Every page shows the app version: the main page in its header, the phone beside its title, the MFD in the top corner next to the update time.
