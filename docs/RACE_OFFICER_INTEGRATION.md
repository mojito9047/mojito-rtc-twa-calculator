# Race Officer integration

## Purpose

The Pwllheli Race Officer app is the source of truth for the current race. This
app imports its course so the Course legs, phone and MFD displays match what the
race officer has set, and shows its start time and postponement on the start bar.

It uses the Race Officer **public** API, documented in the Race Officer app's
`docs/PUBLIC_API.md` (v1.011 and later). No login is needed.

## Address

Set under **Settings → Race Officer** (the Race Officer import page shows it,
with a link to change it). Just the host, starting `http://` or `https://`:

```text
https://pro.pwllhelisailingclub.org
```

or, for a copy running on this PC, `http://localhost:5050`.

## Endpoints used

| Endpoint | Used for |
| --- | --- |
| `/public/race/state` | Cheap change check. Its `signature` moves when the course is set, changed or shortened, AP goes up or down, the start time changes, or the current race moves on. |
| `/api/current_race_course` | The race, the course as set and as sailed, and every mark's position. |

An older Race Officer without `/public/race/state` still works: every poll then
fetches the full course.

## What is imported

| Race Officer | This app |
| --- | --- |
| `marks` (every club mark with a position) | `runtime/marks.json`. Compound parent marks (`Y`, `A`) have no position and are skipped; their corners are kept. |
| `course.sailed.expanded_marks` | The route in `runtime/course.json`. Repeated marks are kept. |
| `rounding` of each mark | The rounding of the leg ending there: `P`, `S`, or `V` for a waypoint (`via`). |
| `course.sailed.finish` (shortened course) | Mark `FIN`, the middle of the finish line, added as the last route point with rounding `F`. |

`course.sailed` is the course as the fleet is sailing it: the same as the course
as set until the race officer shortens it, then cut at the shorten mark and
ending with the run to the finish. Payloads without `sailed` fall back to
`course.expanded_marks`, then `course.marks`.

## When a course is imported

1. **Course not set** (`race.course_set` false). A new race is created with a
   placeholder course number, so nothing is imported. The course showing here
   (the placeholder, or the previous race's course) is cleared once for that
   race, so the pages show *No course set*. A course typed in by hand while
   waiting is left alone. **Import current course** refuses with a message.
2. **Course set.** The route, roundings, route mark positions and race id make a
   signature. The course is imported when it differs from the last import:
   a new course, a shortening, a moved mark, or the next race (even on the same
   course).

Older Race Officer versions without `course_set` are treated as set.

## Current leg

| Change | Current leg |
| --- | --- |
| Shortened (route up to the boat's leg unchanged) | Kept |
| Next race, or a different course | Reset to 0 |
| Course unchanged (e.g. only a finish recorded) | Kept; nothing is rewritten |
| Network error, then recovery | Kept |

## Auto-import polling

Turned on and off from the **Race Officer import** page; with it on,
**Settings → Race Officer** shows whether the last check worked. Settings are saved in
`settings.json`; a server-side thread polls every *N* seconds (5–300, default 10):

1. Poll `/public/race/state`. Unchanged, and a full check in the last 60 seconds:
   nothing more to do.
2. Otherwise fetch `/api/current_race_course`, save the race and start info, and
   import as above.

A full fetch happens at least once a minute, so a re-laid mark is picked up even
though it does not move the state signature. The Race Officer page also runs a
backup poll while it is open. Status is kept in
`runtime/race_officer_poll_state.json`.

## Start bar

The start bar on the Course legs, phone and MFD pages comes from the last poll,
via `/api/race_start`:

| Race Officer | Start bar |
| --- | --- |
| `first_start_time` in the future | `Start in 4:59`, amber in the last minute |
| `first_start_time` passed | `Racing +12:34` |
| `first_start_time` blank | `No start time set` |
| `postponed` | `AP over H — start postponed`, and `AP down at 14:30` when given |
| `course.shortened` | `Course shortened at 4 (rounding 1)` |
| `course_set` false | `Course not set yet` |
| `race_finished` | `Race finished` |

The countdown is to the **first** start. On a day with several starts, Mojito's
own start may be later. Times are the Race Officer hut's local time, counted
against this PC's clock.

The bar is hidden when auto-import is off or the last good check is older than
about three poll intervals.

## Page buttons

| Button | Does |
| --- | --- |
| **Preview current course** | Reads and parses the current course. Changes nothing here. |
| **Import current course** | Imports now, even if unchanged. Refused while no course is set. |
| **Auto-import…** | Turns the server poller on or off. |
| **Check now** | One poll, importing only if changed. |
