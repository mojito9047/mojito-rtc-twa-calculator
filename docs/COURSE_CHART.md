# Course chart

## Purpose

The course chart is on the **Wind & Course** page, under the course editor, so
the course can be seen as it is built. It uses the same data as the leg
calculator: `runtime/marks.json` and `runtime/course.json`.

## Rendering modes

The chart tries to use Leaflet first:

- OpenStreetMap base tiles
- OpenSeaMap seamark overlay

Leaflet (from unpkg.com) and the tiles come from the internet. If Leaflet cannot
be loaded, as on the water with no connection, the app draws a simple SVG chart
instead. It still shows:

- route marks
- course lines
- leg direction arrows
- port/starboard colours

## Colours and lines

| Line | Meaning |
| --- | --- |
| Red | Leg leads to a port rounding. |
| Green | Leg leads to a starboard rounding. |
| Dark | Start, via a waypoint, or unspecified rounding. |
| Dashed | Run to the finish (mark `FIN`) after a shortened course. |
| Grey label | A mark in the database but not on the current course. |

Route marks have numbered labels, so a mark rounded twice shows both numbers.

## Direction arrows

Leaflet mode adds an arrow marker at the midpoint of each leg, rotated to the
leg's bearing. SVG mode adds an arrowhead to the end of each leg line.

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

With fewer than two valid marks the chart shows *Enter or import a course with at
least two valid marks* instead.
