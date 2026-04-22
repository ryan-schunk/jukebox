#!/usr/bin/env python3
"""Blank the Pi display via X11 DPMS after a period of inactivity.

Runs on the Pi kiosk itself (not the jukebox server). Watches /dev/input
for any activity and polls the jukebox server to see if music is playing.
If the Pi has been untouched AND no music is playing for IDLE_TIMEOUT
seconds, the display is blanked with `xset dpms force off`. Any further
input event (arcade button press is fine — CY-2201 enumerates as HID,
which produces evdev events) immediately brings the display back on.

Config via env vars:
  JUKEBOX_STATE_URL   default "http://10.10.10.17:8080/state"
  JUKEBOX_IDLE_TIMEOUT  seconds, default 900 (15 min)
  JUKEBOX_POLL_INTERVAL  seconds between state polls, default 10
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


STATE_URL = os.environ.get("JUKEBOX_STATE_URL", "http://10.10.10.17:8080/state")
IDLE_TIMEOUT = int(os.environ.get("JUKEBOX_IDLE_TIMEOUT", "900"))
POLL_INTERVAL = int(os.environ.get("JUKEBOX_POLL_INTERVAL", "10"))


def xset(*args: str) -> None:
    env = {**os.environ}
    env.setdefault("DISPLAY", ":0")
    try:
        subprocess.run(["xset", *args], check=False, env=env)
    except FileNotFoundError:
        print("xset not found — install x11-xserver-utils", file=sys.stderr)


def display_on() -> None:
    xset("dpms", "force", "on")


def display_off() -> None:
    xset("dpms", "force", "off")


def open_input_fds() -> list[int]:
    fds: list[int] = []
    for path in sorted(Path("/dev/input").glob("event*")):
        try:
            fds.append(os.open(str(path), os.O_RDONLY | os.O_NONBLOCK))
        except OSError as exc:
            print(f"skipping {path}: {exc}", file=sys.stderr)
    return fds


def is_playing() -> bool:
    try:
        with urllib.request.urlopen(STATE_URL, timeout=3) as resp:
            return bool(json.loads(resp.read()).get("playing"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False


def main() -> int:
    fds = open_input_fds()
    if not fds:
        print("no /dev/input/event* devices readable; exiting", file=sys.stderr)
        return 1

    # Make sure DPMS is enabled at all. Keep X's own timers off — we manage them.
    xset("+dpms")
    xset("s", "off")
    xset("-dpms")  # disable X's built-in timeouts
    xset("+dpms")  # re-enable DPMS feature, still with our own driver logic below

    last_active = time.monotonic()
    last_poll = 0.0
    sleeping = False

    print(f"watcher: timeout={IDLE_TIMEOUT}s, poll={POLL_INTERVAL}s, state={STATE_URL}")

    while True:
        ready, _, _ = select.select(fds, [], [], 1.0)
        now = time.monotonic()

        if ready:
            # Drain to avoid filling input buffers
            for fd in ready:
                try:
                    while True:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                except (BlockingIOError, OSError):
                    pass
            last_active = now
            if sleeping:
                display_on()
                sleeping = False

        if now - last_poll >= POLL_INTERVAL:
            last_poll = now
            if is_playing():
                last_active = now
                if sleeping:
                    display_on()
                    sleeping = False

        if not sleeping and now - last_active >= IDLE_TIMEOUT:
            display_off()
            sleeping = True


if __name__ == "__main__":
    raise SystemExit(main())
