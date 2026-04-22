# Pi Display Sleep Watcher

A tiny daemon that blanks the Pi kiosk's display after 15 minutes of inactivity and wakes it on any button press.

- **Sleep**: `xset dpms force off` — HDMI output idles, most TVs/monitors enter standby. The Pi itself stays running.
- **Wake**: any evdev event (arcade button press, keyboard key) or the jukebox server reporting that music started.

## Install on the Pi

SSH into the Pi and run:

```bash
# one-time: make sure xset is available and the user can read /dev/input/event*
sudo apt install -y x11-xserver-utils
sudo usermod -aG input jukebox   # already true on Pi OS Lite, doesn't hurt

# pull latest from this repo onto the Pi (wherever you keep it)
cd ~/jukebox && git pull

# run it in the foreground once to smoke-test
python3 scripts/pi-sleep/watcher.py
```

Press a button on the controller; the script should log nothing but suppress sleep. Stop with Ctrl-C.

## Autostart with openbox

Add this line to `~/.config/openbox/autostart` (same file that already launches Chromium):

```sh
python3 ~/jukebox/scripts/pi-sleep/watcher.py >> /tmp/jukebox-sleep.log 2>&1 &
```

Reboot the Pi. Logs stream to `/tmp/jukebox-sleep.log`.

## Tuning

Environment variables override the defaults:

- `JUKEBOX_STATE_URL` — default `http://10.10.10.17:8080/state`
- `JUKEBOX_IDLE_TIMEOUT` — seconds of inactivity before sleep, default `900` (15 min)
- `JUKEBOX_POLL_INTERVAL` — seconds between server state polls, default `10`

Set them before the `python3 ...` line in the openbox autostart, or in a wrapper script.

## Troubleshooting

- **Display doesn't blank**: run `xset q` in a tty and check the `DPMS` section shows `Enabled`. Some HDMI-to-VGA adapters don't honor DPMS.
- **Wake doesn't happen on button press**: the script reads every `/dev/input/event*` device. Confirm your user is in the `input` group and that a `event*` device appears for the gamepad (`ls -l /dev/input/by-id/`).
- **Sleeps during playback**: the watcher polls the jukebox `/state` endpoint every 10s. If the server is unreachable from the Pi, it'll treat that as "not playing" — check the URL in `JUKEBOX_STATE_URL`.
