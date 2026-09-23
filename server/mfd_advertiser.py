"""B&G/Navico MFD discovery advertiser.

This module sends the UDP multicast payload that makes the app appear as a tile
on compatible B&G/Navico displays. The payload mirrors the Signal K MFD plugin
shape, but points at this app's legacy-compatible `/mfd` page.
"""

import json
import socket
import threading
import time

MFD_MULTICAST_GROUP = "239.2.1.1"
MFD_MULTICAST_PORT = 2053
SEND_FROM_PORT = 34232


def get_local_ipv4_addresses():
    addresses = set()

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = info[4][0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            addresses.add(ip)
    except Exception:
        pass

    return sorted(addresses)


def build_mfd_payload(base_url, ip):
    """Build one MFD browser-panel advertisement for a specific local IP.

    MFDs often open the URL from the same interface that sent the multicast, so
    the payload is generated per local IPv4 address.
    """
    # This intentionally mirrors hoeken/signalk-mfd-plugin getPublishMessage()
    # as closely as possible. Only the tile name, icon and URL are changed.
    return {
        "Version": "1",
        "Source": "Mojito RTC",
        "IP": ip,
        "FeatureName": "Mojito RTC",
        "Text": [
            {
                "Language": "en",
                "Name": "Mojito RTC",
                "Description": "Mojito RTC"
            }
        ],
        "Icon": f"{base_url}/static/mfd-icon.png",
        "URL": f"{base_url}/mfd",
        "OnlyShowOnClientIP": "true",
        "BrowserPanel": {
            "Enable": True,
            "ProgressBarEnable": True,
            "MenuText": [
                {
                    "Language": "en",
                    "Name": "Home"
                }
            ]
        }
    }


def send_payload(payload, from_address):
    msg = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((from_address, SEND_FROM_PORT))
        sock.sendto(msg, (MFD_MULTICAST_GROUP, MFD_MULTICAST_PORT))
    finally:
        sock.close()


def advertiser_loop(port=8765, interval_seconds=10):
    while True:
        for ip in get_local_ipv4_addresses():
            try:
                base_url = f"http://{ip}:{port}"
                payload = build_mfd_payload(base_url, ip)
                send_payload(payload, ip)
            except Exception:
                pass
        time.sleep(interval_seconds)


_started = False


def start_mfd_advertiser(port=8765):
    global _started
    if _started:
        return
    _started = True
    thread = threading.Thread(target=advertiser_loop, kwargs={"port": port}, daemon=True)
    thread.start()
