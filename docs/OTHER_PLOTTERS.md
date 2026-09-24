# Garmin and Raymarine plotters

Only B&G/Navico plotters show the app as a tile so far (see
[MFD_AND_ZEUS.md](MFD_AND_ZEUS.md)). This note records what was found in
September 2026 about the other brands: how Garmin support could be added, and
why Raymarine cannot be done the same way. Nothing here is implemented yet.

| Plotters | Tile? | How the plotter finds web apps | Open to this app? |
| --- | --- | --- | --- |
| B&G, Simrad, Lowrance (Navico) | Yes, since v41 | JSON announcement by UDP multicast to `239.2.1.1:2053` (`server/mfd_advertiser.py`) | Yes |
| Garmin | Not yet | mDNS service `_garmin-mrn-html._tcp` pointing at a JSON manifest, possibly with a UPnP reply | Undocumented, but used by non-partners |
| Raymarine Axiom | No | The plotter recognises approved partners' devices | No public mechanism |

## Plotter browsers

Whatever the brand, the page is shown in an old embedded browser. Victron,
whose app runs on all of them, says plotter browsers are based on
`AppleWebKit/537` or `AppleWebKit/601` (about Chrome 49), and describes the
Raymarine and Garmin ones as "older mobile WebViews". Victron tests Raymarine
screens at 800×480, 1280×720, 1280×800, 1920×1080 and 1920×1200. `/mfd` is
already written for such browsers (ES5, no `fetch`; see MFD_AND_ZEUS.md), so it
is the page to offer on any of them.

## Garmin: how to add it

### What the plotter does

From people who have put their own apps on Garmin plotters (none of this is
documented by Garmin, which does not support individual developers):

1. **mDNS.** The plotter looks for the service type `_garmin-mrn-html._tcp`
   (Garmin's "on-device HTML/web UI" service). The app publishes an instance,
   e.g. `Mojito RTC._garmin-mrn-html._tcp.local`, on port 8765, with the TXT
   records `protovers=1` and `path=/garmin.json`.
2. **Manifest.** The plotter fetches that path. It is JSON with four fields:

   ```json
   {"id": "<uuid>", "title": "Mojito RTC", "icon": "/static/garmin-icon.png", "path": "/mfd"}
   ```

   The plotter then shows the icon and title, and opens `path` when it is
   tapped.
3. **UPnP (may be needed).** The plotter also sends an SSDP search for
   `upnp:rootdevice` to `239.255.255.250:1900` every 5 seconds. A device
   answers with a `LOCATION` header giving the address of a UPnP device
   description, whose `<UDN>` UUID **must match** the manifest's `id`. One
   working open-source implementation (erh/verhboat) does only steps 1 and 2,
   so this step may depend on the plotter's firmware. Do both, then find out on
   a real plotter which is needed.

### Implementation plan

- **`server/garmin_onehelm.py`**, started from `app.main()` beside
  `start_mfd_advertiser()`:
  - A stable app UUID: the same across restarts and upgrades, e.g.
    `uuid.uuid5(<fixed namespace>, socket.gethostname())`, so the plotter
    does not see a new app each time.
  - Routes `/garmin.json` (the manifest above) and `/upnp.xml` (a minimal UPnP
    device description: `deviceType urn:schemas-upnp-org:device:Basic:1`,
    `friendlyName`, `manufacturer` CapeNet Ltd, `modelName` Mojito RTC,
    `presentationURL /mfd`, `UDN uuid:<the same UUID>`).
  - mDNS: publish the service on each local IPv4 address
    (`get_local_ipv4_addresses()`), and again when the addresses change.
    Python has no mDNS in its standard library; the
    [`zeroconf`](https://pypi.org/project/zeroconf/) package is pure Python,
    so it can ship as a wheel in the release zip like Flask and Waitress (add
    it to `requirements.txt`; `tools/release.py` will then check for it).
  - SSDP: a thread listening on UDP `1900` in the group `239.255.255.250`
    that answers `M-SEARCH` for `upnp:rootdevice` or `ssdp:all` with a unicast
    `HTTP/1.1 200 OK` carrying `ST`, `USN: uuid:<uuid>::upnp:rootdevice`,
    `LOCATION: http://<ip>:8765/upnp.xml` and `CACHE-CONTROL: max-age=1800`.
    Windows' own SSDP Discovery service also uses port 1900 and Windows' own
    mDNS uses 5353: open both sockets with `SO_REUSEADDR` so they share, and
    check both still receive.
- **Icon:** a small square PNG (256×256 or less), not the 1 MB
  `static/mfd-icon.png`. Garmin's preferred size is unknown.
- **Setting:** *Announce to Garmin plotters*, under Settings → Instruments or
  a new Displays section, off by default until it has been seen working.
- **Tests:** the manifest and UPnP description match (same UUID), the SSDP
  reply's headers, the UUID is stable, and the setting turns it all off.
  Discovery itself can only be tested on a plotter.
- **Docs:** this file, MFD_AND_ZEUS.md, the README's MFD section and its
  version history.

### On the boat

- The PC must be on the **wired Garmin Marine Network**, which uses Garmin's
  own connectors, so it needs Garmin's network adapter cable to an ordinary
  RJ45 socket. Not Wi-Fi. The plotter hands out addresses (DHCP).
- Windows Firewall must let in UDP 5353 (mDNS), UDP 1900 (SSDP) and TCP 8765.
- To see what happens, capture with Wireshark on the PC
  (`udp port 5353 or udp port 1900 or tcp port 8765`): the plotter should ask
  for `_garmin-mrn-html._tcp`, fetch `/garmin.json`, then the icon, then
  `/mfd` when the icon is tapped. Waitress keeps no access log, so log requests
  to `/garmin.json` while trying it.

## Raymarine: the limitations

- **What Raymarine offers.** Axiom, Axiom+, Axiom Pro and Axiom XL plotters on
  LightHouse 3.11 or later, and LightHouse 4, show HTML5 "LightHouse Apps"
  served by other devices on the boat network, over **wired Ethernet only**
  (RayNet). The older eS and gS series are left out even with LightHouse 3.
- **Only for partners.** The apps shown are Raymarine's integration partners
  (Victron, mazu and others). No discovery method is published for anyone
  else.
- **Victron's open-source code shows the recognition is on Raymarine's side.**
  Venus OS contains no Raymarine (or Navico) announcement at all. It only
  announces itself as a Victron device, generically, over UPnP
  (`simple-upnpd`: manufacturer *Victron Energy*, UDN
  `uuid:com.victronenergy.ccgx...`, `presentationURL /`, but no app name, icon
  or page), and serves its app as a plain page at `/app`. So the plotter's own
  software must recognise a Victron device and open its `/app` page.
- **No general web browser.** Axiom has no browser to type an address into
  (owners have asked Raymarine for one), so `/mfd` cannot be opened by hand.
- **Not an option: imitating a Victron device** (copying its UPnP
  announcement and serving the page at `/app`). It would pass the app off as
  another company's product, show up as Victron, break with a firmware
  change, and clash with real Victron equipment on the boat.
- **The routes open:** apply to Raymarine's partner programme (as CapeNet) for
  an HTML5 integration; or, on a Raymarine boat, use `/phone` on a tablet at
  the helm, which shows the same start bar, bearing to the next mark and
  course table.

## Sources

- Victron, Marine MFD integration by App (Raymarine, Navico, Garmin and Furuno
  requirements): <https://www.victronenergy.com/media/pg/Cerbo_GX/en/marine-mfd-integration-by-app.html>
- Victron community, Garmin OneHelm details (mDNS, manifest, UPnP):
  <https://communityarchive.victronenergy.com/questions/118708/garmin-onehelm-details.html>
- Victron community, HTML 5 app on Garmin 922 with a Raspberry Pi:
  <https://communityarchive.victronenergy.com/questions/185982/html-5-app-on-garmin-922-with-rpi.html>
- erh/verhboat, a working Garmin announcer (`utils/onehelm.go`):
  <https://github.com/erh/verhboat>
- matztam/Remote-Helm, the Garmin mDNS service types (`lib/helm/discovery.dart`):
  <https://github.com/matztam/Remote-Helm>
- Victron Venus OS layer (`simple-upnpd`, the HTML5 app recipe):
  <https://github.com/victronenergy/meta-victronenergy>
- Victron HTML5 app (plotter browser versions, Raymarine screen sizes):
  <https://github.com/victronenergy/venus-html5-app>
- Signal K MFD plugin, the source of this app's Navico announcement (Navico
  only): <https://github.com/hoeken/signalk-mfd-plugin>
- Raymarine, LightHouse Apps: <https://www.raymarine.com/en-us/learning/online-guides/connecting-lighthouse-apps>
- Raymarine forum, request for a browser on Axiom:
  <https://forum.raymarine.com/showthread.php?tid=7667>
