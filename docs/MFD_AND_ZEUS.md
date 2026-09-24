# B&G / Navico MFD integration

## Purpose

The app advertises itself as a browser panel so it appears as a tile on B&G/Navico
MFDs such as the Zeus 3S. The tile opens `/mfd`.

## Advertisement

The advertiser sends a UDP multicast JSON payload every 10 seconds, from each of
the PC's IPv4 addresses, to:

```text
239.2.1.1:2053
```

The payload mirrors the Signal K MFD plugin structure closely, but uses:

- name: `Mojito RTC`
- icon: `/static/mfd-icon.png`
- URL: `/mfd`

`/api/mfd_status` shows the payloads being sent.

## The `/mfd` page

From the top:

1. **Leg controls** (◀ Prev, current leg, Next ▶) with TWD/TWS on the right
   (*MANUAL* beside them with manual wind), and under them the app version and
   the time of the last update. There is no page heading, to leave room for the
   table.
2. **Bar**, in three parts:
   - **Start status**: race and course, then the countdown, racing time, AP flag,
     shortened course or *Course not set yet* (see
     [RACE_OFFICER_INTEGRATION.md](RACE_OFFICER_INTEGRATION.md#start-bar)).
     Empty when Race Officer auto-import is off.
   - **To mark**: bearing and range from the boat to the mark at the end of the
     current leg, from the instruments' GPS position (`/api/position`). *No GPS
     position* without a fix, or with manual wind.
   - **Next leg**: bearing and length of the leg after that mark. *Last leg* on
     the final leg.
3. **Course table**: every leg, with the current leg highlighted. It scrolls
   vertically, so long courses fit.

## Older browsers

Some MFD embedded browsers do not support modern JavaScript. The `/mfd` page and
the shared scripts it loads (`static/legs.js`, `static/race_start.js`) avoid:

- `fetch` (they use `XMLHttpRequest`)
- `async` / `await`
- arrow functions
- template literals
- `let` / `const`
- spread, optional chaining and newer built-ins such as `Array.find`

`tests/test_js.py` fails if any of these appear. Dates are never parsed in the
browser: the server sends the seconds to the start.

## Cache behaviour

Some MFD browsers cache API responses aggressively. The app handles this by:

- adding no-cache headers to every Flask response
- adding timestamp query strings to MFD API calls

## Calculation alignment

The MFD page mirrors the main Course legs page for:

- wind: `/api/wind`, like the other pages (manual wind, or the instruments'
  TWD and TWS, falling back to the TWD last shown on the Course legs page if the
  instruments have none)
- port/starboard side
- sail chart lookup, including which column is used when a TWA heading repeats
- upwind/downwind VMG target speed

The calculations themselves are shared: all three pages use `static/legs.js`.
`tests/test_js.py` checks all three pages give the same answers.

## Other plotter brands

Only B&G/Navico plotters get the tile. How Garmin plotters could be added, and
why Raymarine plotters cannot be done the same way: [OTHER_PLOTTERS.md](OTHER_PLOTTERS.md).
