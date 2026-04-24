#!/usr/bin/env python3
"""Blank the Pi display via X11 DPMS after a period of inactivity.

Runs on the Pi kiosk itself (not the jukebox server). Watches /dev/input
for any activity and polls the jukebox server to see if music is playing.
If the Pi has been untouched AND no music is playing for IDLE_TIMEOUT
seconds, the display is blanked with `xset dpms force off`. Any further
input event (arcade button press included — CY-2201 enumerates as HID,
which produces evdev events) immediately brings the display back on.

Logs go to stdout — pair with ">> /tmp/jukebox-sleep.log 2>&1 &" in
the openbox autostart so they're visible.

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
VERBOSE = os.environ.get("JUKEBOX_VERBOSE", "0") == "1"
RESCAN_INTERVAL = 5  # seconds — re-check /dev/input for hot-plugged devices


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def xset(*args: str) -> None:
    env = {**os.environ}
    env.setdefault("DISPLAY", ":0")
    try:
        subprocess.run(["xset", *args], check=False, env=env)
    except FileNotFoundError:
        log("xset not found — install x11-xserver-utils")


def display_on() -> None:
    xset("dpms", "force", "on")


def display_off() -> None:
    xset("dpms", "force", "off")


def scan_devices(known: dict[str, int], paths: dict[int, str]) -> None:
    """Open any new /dev/input/event* or /dev/input/js* devices. Mutates both maps."""
    candidates = sorted(Path("/dev/input").glob("event*")) + sorted(
        Path("/dev/input").glob("js*")
    )
    for path in candidates:
        key = str(path)
        if key in known:
            continue
        try:
            fd = os.open(key, os.O_RDONLY | os.O_NONBLOCK)
            known[key] = fd
            paths[fd] = key
            log(f"opened {key}")
        except PermissionError:
            log(f"PERMISSION DENIED reading {key} — is the user in the 'input' group?")
            # Record the failure so we don't spam it; use -1 as a sentinel
            known[key] = -1
        except OSError as exc:
            log(f"skip {key}: {exc}")
            known[key] = -1


def close_device(known: dict[str, int], key: str) -> None:
    fd = known.pop(key, -1)
    if fd >= 0:
        try:
            os.close(fd)
        except OSError:
            pass


def active_fds(known: dict[str, int]) -> list[int]:
    return [fd for fd in known.values() if fd >= 0]


def is_playing() -> bool:
    try:
        with urllib.request.urlopen(STATE_URL, timeout=3) as resp:
            return bool(json.loads(resp.read()).get("playing"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        log(f"state poll failed: {exc}")
        return False


def main() -> int:
    # Make sure X's own DPMS timers are disabled so only we manage sleep.
    # Without this, X can auto-sleep the display on its default schedule,
    # which looks to the user like "sleep fires 15 min after boot no matter
    # what." `dpms 0 0 0` sets standby/suspend/off timeouts all to 0 = off.
    xset("s", "off")
    xset("s", "noblank")
    xset("-dpms")
    xset("+dpms")
    xset("dpms", "0", "0", "0")

    known: dict[str, int] = {}
    paths: dict[int, str] = {}
    scan_devices(known, paths)
    if not any(fd >= 0 for fd in known.values()):
        log("no readable /dev/input devices — watcher will still run, retrying every 5s")

    last_active = time.monotonic()
    last_poll = 0.0
    last_rescan = time.monotonic()
    sleeping = False
    event_counts: dict[str, int] = {}
    last_verbose_summary = time.monotonic()

    log(
        f"watcher up: timeout={IDLE_TIMEOUT}s, poll={POLL_INTERVAL}s, "
        f"state={STATE_URL}, devices={len(active_fds(known))}, verbose={VERBOSE}"
    )

    while True:
        fds = active_fds(known)
        timeout = 1.0 if fds else 2.0
        ready, _, _ = ([], [], [])
        if fds:
            ready, _, _ = select.select(fds, [], [], timeout)
        else:
            time.sleep(timeout)
        now = time.monotonic()

        if ready:
            # Drain without caring about content; any byte means activity.
            for fd in ready:
                bytes_read = 0
                try:
                    while True:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                except (BlockingIOError, OSError):
                    pass
                if VERBOSE:
                    p = paths.get(fd, f"fd{fd}")
                    event_counts[p] = event_counts.get(p, 0) + 1
            last_active = now
            if sleeping:
                log("input activity -> wake")
                display_on()
                sleeping = False

        if VERBOSE and now - last_verbose_summary >= 5.0:
            last_verbose_summary = now
            if event_counts:
                summary = ", ".join(f"{p}={c}" for p, c in sorted(event_counts.items()))
                log(f"events in last 5s: {summary}")
                event_counts.clear()
            else:
                log("events in last 5s: (none)")

        if now - last_poll >= POLL_INTERVAL:
            last_poll = now
            if is_playing():
                last_active = now
                if sleeping:
                    log("playback started -> wake")
                    display_on()
                    sleeping = False

        if now - last_rescan >= RESCAN_INTERVAL:
            last_rescan = now
            before = len(active_fds(known))
            scan_devices(known, paths)
            after = len(active_fds(known))
            if after > before:
                log(f"rescan: {before} -> {after} active devices")

        if not sleeping and now - last_active >= IDLE_TIMEOUT:
            log(f"idle {int(now - last_active)}s, no playback -> sleep display")
            display_off()
            sleeping = True


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("interrupted, exiting")
