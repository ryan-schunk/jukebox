# Album & Artist Browse — Hero Slider Redesign

Date: 2026-04-22

## Problem

The current album and artist screens are small-thumbnail vertical lists. They work but feel utilitarian on a dedicated jukebox that's meant to be an artifact. The user wants the browse surfaces to feel more "artsy" — album art should slide by one at a time, like flipping through a physical collection.

## Users & context

- Single device: a Pi kiosk driving a fixed display from across the room.
- Input: 4 arcade buttons (red=btn1, purple=btn2, blue=btn3, green=btn4). No keyboard, no mouse, no touch.
- Library sizes can reach hundreds of albums / artists, so paging-as-you-navigate (already implemented) stays.

## Goals

- Album art becomes the visual anchor of the browse experience.
- One big cover at any time; previous and next visible at the edges as peeks.
- Whole screen takes on the color of the current cover (blurred backdrop) so flipping feels alive.
- Same pattern for albums, artists, and the artist-drill-in albums screen — one consistent visual language.

## Non-goals / deferred

- No 3D transforms (CoverFlow-style tilt) — explicitly rejected for visual clarity and Pi perf.
- No tile/grid view — rejected in favor of consistency with the hero metaphor.
- No touch/swipe gestures — input is 4 arcade buttons only.
- No search. No filtering. No sorting controls. (Future, not now.)

## Behavior

- **Layout**: Full-screen blurred backdrop (current cover, scaled up, heavily blurred and dimmed). Centered hero cover. Small slivers of previous and next covers peeking on left and right.
- **Text**: Album name (or artist name) and secondary line below the hero, centered, drop-shadow for legibility over the blurred backdrop.
- **Navigation**: btn2 (purple) = previous cover, btn3 (blue) = next cover. Button-bar labels update to "Previous" / "Next" on these screens.
- **Select**: btn1 (red) on albums plays the album; on artists drills into that artist's albums.
- **Back/cycle**: btn4 (green) keeps existing behavior — back from a drill, otherwise cycle screens.
- **Transition**: quick horizontal slide on prev/next (snappy — 150–200ms ease-out). Backdrop crossfades to the new cover's blur.
- **Missing art**: fall back to a solid dark tile with the item name overlaid; backdrop falls back to the app's default dark surface.
- **Edges**: at index 0, peek on the left is empty. At the last loaded item, trigger the existing paging fetch as before.

## Success criteria

- Pressing btn2/btn3 flips the hero cover with the described motion, and the backdrop visibly shifts color within one flip.
- All three list surfaces (albums, artists, artist's albums drill-in) share the same layout.
- No regression in paging: list continues to load more as user approaches the end.
- Runs smoothly on the Pi kiosk (Chromium on Pi OS Lite, arm64).

## Dependencies / assumptions

- Cover images are already proxied via `/image?path=...` on the server; hero and blurred backdrop both reuse that proxy. Backdrop can use the same URL with CSS `filter: blur()` rather than a new server-side blurred variant.
- Pi Chromium GPU compositing handles `filter: blur()` at acceptable cost; if it chugs, fallback is a dominant-color wash (see deferred option).

## Files likely touched

- `static/index.html` — restructure `#browse`, `#artists`, `#artist-albums` sections.
- `static/style.css` — new hero + peeks layout, blurred backdrop rules.
- `static/app.js` — update `renderAlbumList` / `renderArtistList` / `renderArtistAlbumList` to render hero+peeks instead of lists; update btn2/btn3 labels for these screens in `SCREEN_LABELS`.
