# Course chart

## Purpose

The course chart is on the **Wind & Course** page, under the course editor, so
the course can be seen as it is built. It uses the same data as the leg
calculator: `runtime/marks.json` and `runtime/course.json`.

## Rendering modes

The chart tries to use Leaflet first:

- OpenStreetMap base tiles
- OpenSeaMap seamark overlay

Leaflet 1.9.4 is served by the app (`static/leaflet/`). If it cannot be loaded,
the app draws a simple SVG chart instead. It still shows:

- route marks
- course lines
- leg direction arrows
- port/starboard colours

## Map tiles without the internet

The chart does not load tiles from the tile servers itself: it asks the app
(`/tiles/osm/{z}/{x}/{y}.png`, `/tiles/seamark/{z}/{x}/{y}.png`, in
`server/tiles.py`). The first time a tile is shown with an internet connection,
the app fetches it from OpenStreetMap or OpenSeaMap and saves it in
`runtime/tiles/`; from then on the saved copy is served, refreshed once a week
when the internet is there. Without the internet any saved copy is served,
however old. So the map is there on the water wherever it was viewed before,
at the zoom levels viewed; anywhere else is blank, with the marks and legs still
drawn.

OpenSeaMap has no tile where there are no seamarks; that is remembered for a
week too. After a failed connection the app leaves the tile servers alone for a
minute, so an offline chart does not wait on each tile. Tiles are only fetched
as they are viewed, never downloaded in bulk, as OpenStreetMap's tile usage
policy asks, and the requests identify the app.

The saved tiles are copied to a new version by `install.bat`, and can be
deleted at any time.

## Colours and lines

| Line | Meaning |
| --- | --- |
| Red | Leg leads to a port rounding. |
| Green | Leg leads to a starboard rounding. |
| Dark | Start, via a waypoint, or unspecified rounding. |
| Dashed | Run to the finish (mark `FIN`) after a shortened course. |

## Marks and leg numbers

Mark IDs and leg numbers are drawn differently, because both are often
numbers (mark 3 is not leg 3):

| On the chart | Meaning |
| --- | --- |
| Dot with a dark label, e.g. `3` | A mark on the course, at the dot's exact position. Each mark is labelled once, however often it is rounded; the first is also marked *Start* and the last *Finish*. The dot is red if the mark is always left to port, green if always to starboard, dark otherwise. |
| Number in a circle, e.g. `4` or `4, 7` | The leg number(s), in course order, beside the leg and to the right of its direction of travel. A leg sailed more than once the same way shows all its numbers in one circle; the same two marks sailed the other way have their own circle on the other side. |
| Small grey dot and ID | A mark in the list but not on the current course. |

Clicking a mark shows its name, position, and for a course mark each leg that
ends there and how it is rounded.

`courseChartModel()` in `static/index.js` works out the marks, legs and
circles once; the Leaflet and SVG charts both draw from it.

## Direction arrows

Each leg has an arrow 70% of the way along it, pointing along the leg, and its
number 40% along, so on a leg sailed both ways none of them overlap.

## Refresh behaviour

The chart redraws when:

- the Wind & Course page is opened
- a mark is added, a rounding chosen, or the course typed, undone or cleared
- marks or the course are loaded or change on the server (for example after a
  Race Officer import)
- the **Refresh chart** button is pressed

It is not drawn while its tab is hidden. Leaflet cannot size a hidden map, so
drawing then left the chart zoomed in on one mark with no tiles (fixed in v60).
Opening the tab draws it at the right size, framed on the whole course.

With no course yet (fewer than two route marks with positions) the chart is
framed on **every mark** instead, so the whole race area is in view while the
course is announced and built; it zooms in to the course once the second mark
is added. Only when there are no marks with positions at all does it show *No
marks with positions yet* instead.
