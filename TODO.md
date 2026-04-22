# Jukebox TODO

## Coding

- [ ] Add profiles, activated by holding a button.
- [ ] Install the Pi sleep watcher on the kiosk (see `scripts/pi-sleep/README.md`).
- [ ] Audit album and artist page efficiency on the Pi 3B+ — hero slide-in, backdrop blur, and image decoding may still be costing more than needed during navigation.

## Printing

- [ ] LED tube
- [ ] Power cable insert
- [ ] Support pillar for keyboard plate

## Electronics

- [ ] Pick speakers. Options:
  - TV soundbar — no new hardware, but requires TV to be on (HDMI-CEC/ARC handshake).
  - WiiM Mini + small amp + bookshelf speakers — always-on, MA-discoverable, ~$90.
  - Raspberry Pi + Squeezelite/Snapcast — reuse existing hardware.
  - Powered speakers into jukebox PC's 3.5mm out via MA "local audio" player — zero new hardware.
- [ ] LED setup — wiring, driver choice, behavior on play/pause/track change.

## Done

- Auto-rediscover active Music Assistant player when the cached one disappears.
- Gamepad API polling on CY-2201 controller (HAT axis 9 on VM, stick axes 0/1 on Pi/Linux Chromium).
- Kiosk autoboot on Pi Lite via auto-login → `startx` → openbox → Chromium.
- Dynamic btn4 label showing the target screen name.
- Gamepad debug logging disabled; on-screen button color circles match the physical red/purple/blue/green panel.
- Track duration pulled from the current queue item so the progress timer advances and shows total length.
- Album / artist / artist-drill browse screens redesigned as hero slider with previous/next peeks and a blurred cover backdrop.
- Skip the tty1 login prompt on boot — enable getty autologin for the `jukebox` user so `startx` → Chromium kiosk runs hands-free.
