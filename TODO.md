# Jukebox TODO

## Coding

- [ ] Skip the tty1 login prompt on boot — enable getty autologin for the `jukebox` user so `startx` → Chromium kiosk runs hands-free.
- [ ] Redesign album and artist pages to look like flipping through album covers.
- [ ] Add profiles, activated by holding a button.
- [ ] Timer doesn't change unless the song changes or you hit pause. The total song length isn't updated either.

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
