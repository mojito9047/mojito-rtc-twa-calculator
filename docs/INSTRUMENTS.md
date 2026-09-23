# Instrument sources

Live wind and position (and boat speed, heading, COG and SOG) can come from any
one of four sources, chosen under **Settings → Instruments**:

| Source | Setting | Connection |
| --- | --- | --- |
| Expedition on this PC | `expedition` (default) | Expedition's `ExpDLL.dll` (`server/expedition_dll.py`) |
| B&G H5000 | `h5000` | Websocket, default `192.168.15.149:2053` (`server/h5000.py`) |
| NMEA 0183 over IP from a plotter | `nmea0183` | TCP, default `192.168.15.166:10110` (`server/nmea0183.py`) |
| Manual wind (no instruments) | `manual` | TWD and TWS typed in on the Wind & Course page |

Whichever is chosen, the app uses directions in **degrees true** and speeds in
**knots**, so leg TWAs are right whether the displays are set to true or
magnetic.

The Settings page shows whether the source is connected and which values are
arriving. The same is available from `/api/instruments`.

## Channels

| Channel | Used for | Expedition | H5000 item | NMEA 0183 |
| --- | --- | --- | --- | --- |
| TWD | Leg TWA, tack | channel 6 | 142 True Wind Direction | `MWD`; else true `MWV` + true heading |
| TWS | Sail, target speed | 5 | 47 True Wind Speed | `MWD`; else true `MWV` |
| BSP | Reported only | 1 | 42 Boat Speed | `VHW` |
| HDG | TWD from `MWV` (NMEA 0183) | 13 | 37 Heading | `HDT`; `VHW` true; `HDG` + variation |
| Lat, Lon | Bearing to next mark (phone, MFD) | 48, 49 | 421, 422 GPS Position | `RMC`, `GLL`, `GGA` |
| COG, SOG | Reported only | 50, 51 | 9, 41 | `RMC`, `VTG` |

*Reported only*: read and listed in the Settings status and `/api/expedition`,
but not used in the leg figures (leg times come from the polar's target speed).

## How each source works

### Expedition

Read directly from the running Expedition through its DLL. There is no
connection to set up. The DLL's "age" output always equals the channel number,
so it is not used.

### B&G H5000 (websocket)

The H5000 speaks Navico's GoFree websocket protocol. The app connects to
`ws://<address>:2053/` and subscribes to the items above:

```json
{"DataReq": [{"id": 142, "repeat": true, "inst": 0}, ...]}
```

The H5000 then sends a message about once a second:

```json
{"Data": [{"id": 142, "valid": true, "val": 353.7, "sysVal": 6.1656, "valStr": "353.7", ...}]}
```

Each item has two values:

- `val` is in the **display's** units and reference: on Mojito the displays
  show magnetic, so `val` for TWD was 353.7 (magnetic).
- `sysVal` is the underlying value: angles and positions in **radians**,
  referenced to **true**; speeds in knots. 6.1656 rad = 353.3°, matching the
  plotter's true TWD in `MWD` at the same moment.

The app uses `sysVal`, so changing the display units or reference does not
change what it reads. Items marked `"valid": false` are ignored.

The app has its own small websocket client (`server/websocket_client.py`), so
nothing extra has to be installed.

### NMEA 0183 over IP

The plotter serves NMEA 0183 sentences on a TCP port. The app connects, reads
lines, checks each checksum, and uses the sentences in the table above (any
talker ID; others such as AIS, GSV and depth are ignored). Magnetic headings are
turned into true with the variation from `HDG` or `RMC`; without a variation a
magnetic-only heading is not used.

### When several sentences or devices carry the same value

The plotter's stream carries some values more than once: heading in `HDG`
(about ten times a second) and `VHW` (once a second), position in `RMC`, `GGA`
and `GLL`, COG and SOG in `RMC` and `VTG`. On Mojito these come from the same
sensor and agree. A plotter can also pass on more than one device, such as two
compasses, each with its own talker ID.

So a value cannot flip between them, each channel is taken from one origin
(talker + sentence), in this order of preference:

| Channel | Sentences, most preferred first |
| --- | --- |
| TWD, TWS | `MWD`, `MWV` (true) |
| Heading | `HDT`, `VHW`, `HDG` |
| Boat speed | `VHW` |
| Position | `RMC`, `GGA`, `GLL` |
| COG, SOG | `RMC`, `VTG` |

A more preferred sentence takes over as soon as it arrives. Anything else, a
less preferred sentence or another talker sending the same sentence, is used
only once the origin in use has sent nothing for 3 seconds. TWD worked out from
`MWV` uses the heading from the chosen origin only. `/api/instruments` lists the
origin in use for each channel (`channel_origins`), e.g. heading from `SDVHW`.

On the H5000 there is nothing to choose: its websocket gives one value per
item, from the device selected in the H5000's own data source settings. (Its
data list shows two NMEA 2000 devices behind position, COG and SOG, two behind
boat speed and three behind apparent wind; every instance number returns the
same value.)

### Manual wind

For when no instruments are available. The TWD and TWS boxes on the **Wind &
Course** page become editable; a change is saved half a second after typing
stops (`POST /api/wind`, kept in `runtime/manual_wind.json`) and used at once by
every display. The Course legs page shows *Manual wind*, and the phone and MFD
show *MANUAL* beside the wind. When the source is first switched to manual, the
boxes start from the wind in use at that moment.

Boat speed, heading and position are unavailable with manual wind, so the
phone and MFD show *No GPS position* for the bearing to the next mark. The
manual values are kept when switching back to an instrument source, ready for
next time.

## The wind the displays use

`/api/wind` gives the TWD/TWS every display uses and where it came from:
the instrument source, `manual`, or `display_fallback` when the source has no
TWD and the TWD last shown on the Course legs page is used instead. The
Course legs, phone and MFD pages all read it.

## Dropouts

The H5000 and NMEA readers run in the background. A value older than
**5 seconds** counts as no data, as if Expedition had reported nothing. If the
connection drops, the reader reconnects after 1, 2, 5, then every 10 seconds.
Switching source, or changing an address, stops the old reader and starts the
new one straight away.

While no TWD is arriving, `/api/wind` (and `/api/twd`) fall back to the TWD
last shown on the Course legs page, so the MFD does not drop to 0°.

## Checking a source

- **Settings → Instruments**: shows `connected; receiving Bsp, Cog, Hdg, ...` or
  the error, refreshed every 2 seconds.
- `http://<PC>:8765/api/instruments`: the same, with the age of each channel.
- `http://<PC>:8765/api/expedition`: the values the app is using now.
