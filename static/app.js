// === Key Bindings (R12) ===
// Physical buttons wired to arrow keys: Right = select/play, Up/Down = navigate, Left = back/next-screen.
// Number keys retained as a desktop fallback.
const KEY_MAP = {
  ArrowRight: "btn1",
  ArrowUp: "btn2",
  ArrowDown: "btn3",
  ArrowLeft: "btn4",
  "1": "btn1",
  "2": "btn2",
  "3": "btn3",
  "4": "btn4",
};

// === Button labels per screen ===
// btn4 is set dynamically in updateButtonLabels() for non-drill screens
// (shows the name of the screen it will cycle to).
const SCREEN_LABELS = {
  "now-playing": {
    btn1: "Play/Pause",
    btn2: "Previous",
    btn3: "Next",
  },
  browse: {
    btn1: "Select",
    btn2: "Up",
    btn3: "Down",
  },
  artists: {
    btn1: "Select",
    btn2: "Up",
    btn3: "Down",
  },
  "artist-albums": {
    btn1: "Select",
    btn2: "Up",
    btn3: "Down",
    btn4: "Back",
  },
  queue: {
    btn1: "",
    btn2: "Up",
    btn3: "Down",
  },
};

const SCREEN_DISPLAY_NAMES = {
  "now-playing": "Now Playing",
  browse: "Albums",
  artists: "Artists",
  queue: "Queue",
};

// === State ===
const SCREENS = ["now-playing", "browse", "artists", "queue"];
let currentScreen = 0;
let drillScreen = null; // e.g. "artist-albums" — overrides SCREENS[currentScreen] when set
let ws = null;
let reconnectDelay = 1000;

let state = {
  connected: false,
  playing: false,
  track: null,
  elapsed: 0,
  duration: 0,
  has_next: false,
  has_previous: false,
};

// Browse state
let albums = [];
let albumsLoaded = false;
let browseIndex = 0;

// Artists state
let artists = [];
let artistsLoaded = false;
let artistIndex = 0;

// Artist-albums (drill) state
let artistAlbums = [];
let artistAlbumsIndex = 0;
let currentArtist = null;

// Queue state
let queueItems = [];
let queueIndex = 0;

// Progress interpolation
let progressInterval = null;
let lastStateTime = 0;

// === WebSocket ===

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    reconnectDelay = 1000;
    document.getElementById("disconnected").classList.add("hidden");
  };

  ws.onclose = () => {
    state.connected = false;
    document.getElementById("disconnected").classList.remove("hidden");
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
  };

  ws.onerror = () => {
    ws.close();
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };
}

function send(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

function handleMessage(msg) {
  if (msg.type === "state") {
    state = msg.data;
    lastStateTime = Date.now();

    if (!state.connected) {
      document.getElementById("disconnected").classList.remove("hidden");
    } else {
      document.getElementById("disconnected").classList.add("hidden");
    }

    updateNowPlaying();
    startProgressInterpolation();
  } else if (msg.type === "albums") {
    if (msg.offset === 0) {
      albums = msg.data;
    } else {
      albums = albums.concat(msg.data);
    }
    albumsLoaded = true;
    renderAlbumList();
  } else if (msg.type === "queue") {
    queueItems = msg.data;
    renderQueueList();
  } else if (msg.type === "artists") {
    if (msg.offset === 0) {
      artists = msg.data;
    } else {
      artists = artists.concat(msg.data);
    }
    artistsLoaded = true;
    renderArtistList();
  } else if (msg.type === "artist_albums") {
    artistAlbums = msg.data;
    artistAlbumsIndex = 0;
    renderArtistAlbumList();
  } else if (msg.type === "error") {
    console.error("Server error:", msg.message);
  }
}

// === Screen Management ===

function activeScreenId() {
  return drillScreen || SCREENS[currentScreen];
}

function showScreen(screenId) {
  document.querySelectorAll(".screen").forEach((el) => {
    el.classList.remove("active");
  });
  document.getElementById(screenId).classList.add("active");
  updateButtonLabels();
}

function switchScreen(index) {
  drillScreen = null;
  currentScreen = index;
  const screenId = SCREENS[currentScreen];
  showScreen(screenId);

  // Load data when entering screens
  if (screenId === "browse" && !albumsLoaded) {
    send({ type: "command", action: "get_albums", offset: 0, limit: 50 });
  }
  if (screenId === "artists" && !artistsLoaded) {
    send({ type: "command", action: "get_artists", offset: 0, limit: 50 });
  }
  if (screenId === "queue") {
    send({ type: "command", action: "get_queue" });
  }
}

function cycleScreen() {
  switchScreen((currentScreen + 1) % SCREENS.length);
}

function enterArtistAlbums(artist) {
  currentArtist = artist;
  artistAlbums = [];
  artistAlbumsIndex = 0;
  document.getElementById("artist-albums-title").textContent = artist.name;
  renderArtistAlbumList();
  drillScreen = "artist-albums";
  showScreen("artist-albums");
  send({
    type: "command",
    action: "get_artist_albums",
    artist_id: artist.id,
    provider: artist.provider,
  });
}

function exitDrill() {
  drillScreen = null;
  showScreen(SCREENS[currentScreen]);
}

function updateButtonLabels() {
  const screen = activeScreenId();
  const labels = SCREEN_LABELS[screen];
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById(`btn${i}-label`);
    el.textContent = labels[`btn${i}`] ?? "";
    el.setAttribute("data-key", i);
    el.classList.remove("disabled");
  }

  // btn4: "Back" on drill screens, otherwise the name of the next screen
  if (!labels.btn4) {
    const next = SCREENS[(currentScreen + 1) % SCREENS.length];
    document.getElementById("btn4-label").textContent = SCREEN_DISPLAY_NAMES[next];
  }

  if (screen === "now-playing") {
    document.getElementById("btn1-label").textContent = state.playing
      ? "Pause"
      : "Play";
    document.getElementById("btn2-label").classList.toggle("disabled", !state.has_previous);
    document.getElementById("btn3-label").classList.toggle("disabled", !state.has_next);
  }
}

// === Input Handling (R11) ===

function pressButton(btn) {
  const screen = activeScreenId();

  // btn4: Back from a drill, else cycle screens
  if (btn === "btn4") {
    if (drillScreen) {
      exitDrill();
    } else {
      cycleScreen();
    }
    return;
  }

  // Context-sensitive buttons (1-3)
  if (screen === "now-playing") {
    handleNowPlayingButton(btn);
  } else if (screen === "browse") {
    handleBrowseButton(btn);
  } else if (screen === "artists") {
    handleArtistsButton(btn);
  } else if (screen === "artist-albums") {
    handleArtistAlbumsButton(btn);
  } else if (screen === "queue") {
    handleQueueButton(btn);
  }
}

document.addEventListener("keydown", (e) => {
  const btn = KEY_MAP[e.key];
  if (!btn) return;
  e.preventDefault();
  pressButton(btn);
});

// === Gamepad Support ===
// CY-2201 board enumerates as a DirectInput gamepad. D-pad terminals (AL/AR/AU/AD)
// come through differently per platform — Windows/Chrome uses a POV-hat on axis 9,
// Linux/Chromium uses the first stick on axes 0/1. We watch both.
const GAMEPAD_HAT_AXIS = 9;
const GAMEPAD_HAT_DIRS = [
  { value: -1.0,   btn: "btn2" }, // Up    -> AU
  { value: -0.428, btn: "btn1" }, // Right -> AR
  { value:  0.143, btn: "btn3" }, // Down  -> AD
  { value:  0.714, btn: "btn4" }, // Left  -> AL
];
const GAMEPAD_HAT_TOLERANCE = 0.1;

// Stick-style D-pad (axes 0=X, 1=Y; +1/-1 at cardinals)
const GAMEPAD_STICK_X_AXIS = 0;
const GAMEPAD_STICK_Y_AXIS = 1;
const GAMEPAD_STICK_THRESHOLD = 0.5;

// Face-button fallback if any are wired directly (A/B/X/Y -> btn1..btn4)
const GAMEPAD_BUTTON_MAP = {
  0: "btn1", // A
  1: "btn2", // B
  2: "btn3", // X
  3: "btn4", // Y
};

let gamepadPolling = false;
let prevHatBtn = null;
let prevHatRaw = null;
let prevStickBtn = null;
let loggedNoGamepad = false;
const prevButtonState = {};
const prevAxisSnapshot = {};
const prevButtonSnapshot = {};
const GAMEPAD_DEBUG = true; // set false once mappings are confirmed

function pollGamepad() {
  const gp = navigator.getGamepads()[0];
  if (!gp) {
    if (GAMEPAD_DEBUG && !loggedNoGamepad) {
      console.log("[gamepad] poll running, but no gamepad at index 0 yet (press a button once to wake it up)");
      loggedNoGamepad = true;
    }
    requestAnimationFrame(pollGamepad);
    return;
  }
  if (loggedNoGamepad) {
    console.log(`[gamepad] acquired: ${gp.id}`);
    loggedNoGamepad = false;
  }

  // Discovery logging: report any axis/button change so we can identify
  // the D-pad mapping on this platform.
  if (GAMEPAD_DEBUG) {
    for (let i = 0; i < gp.axes.length; i++) {
      const v = gp.axes[i];
      const prev = prevAxisSnapshot[i];
      if (prev === undefined || Math.abs(prev - v) > 0.05) {
        if (prev !== undefined) {
          console.log(`[gamepad] axis${i}: ${prev.toFixed(4)} -> ${v.toFixed(4)}`);
        }
        prevAxisSnapshot[i] = v;
      }
    }
    for (let i = 0; i < gp.buttons.length; i++) {
      const pressed = !!(gp.buttons[i] && gp.buttons[i].pressed);
      if (pressed !== !!prevButtonSnapshot[i]) {
        console.log(`[gamepad] button${i}: ${!!prevButtonSnapshot[i]} -> ${pressed}`);
        prevButtonSnapshot[i] = pressed;
      }
    }
  }

  // POV-hat via axis
  const hat = gp.axes[GAMEPAD_HAT_AXIS];
  if (GAMEPAD_DEBUG && hat !== undefined && Math.abs((prevHatRaw ?? hat) - hat) > 0.01) {
    console.log(`[gamepad] axis${GAMEPAD_HAT_AXIS}: ${prevHatRaw?.toFixed(4)} -> ${hat.toFixed(4)}`);
  }
  prevHatRaw = hat;

  let hatBtn = null;
  if (hat !== undefined) {
    for (const d of GAMEPAD_HAT_DIRS) {
      if (Math.abs(hat - d.value) < GAMEPAD_HAT_TOLERANCE) {
        hatBtn = d.btn;
        break;
      }
    }
  }
  if (hatBtn !== prevHatBtn) {
    if (GAMEPAD_DEBUG) console.log(`[gamepad] hat decode: ${prevHatBtn} -> ${hatBtn} (axis=${hat?.toFixed(4)})`);
    if (hatBtn) {
      if (GAMEPAD_DEBUG) console.log(`[gamepad] pressButton(${hatBtn})`);
      pressButton(hatBtn);
    }
  }
  prevHatBtn = hatBtn;

  // Stick-style D-pad (axes 0/1)
  const sx = gp.axes[GAMEPAD_STICK_X_AXIS] ?? 0;
  const sy = gp.axes[GAMEPAD_STICK_Y_AXIS] ?? 0;
  let stickBtn = null;
  if (sx >  GAMEPAD_STICK_THRESHOLD)      stickBtn = "btn1"; // Right -> AR
  else if (sx < -GAMEPAD_STICK_THRESHOLD) stickBtn = "btn4"; // Left  -> AL
  else if (sy < -GAMEPAD_STICK_THRESHOLD) stickBtn = "btn2"; // Up    -> AU
  else if (sy >  GAMEPAD_STICK_THRESHOLD) stickBtn = "btn3"; // Down  -> AD
  if (stickBtn !== prevStickBtn) {
    if (GAMEPAD_DEBUG) console.log(`[gamepad] stick decode: ${prevStickBtn} -> ${stickBtn} (x=${sx.toFixed(2)}, y=${sy.toFixed(2)})`);
    if (stickBtn) {
      if (GAMEPAD_DEBUG) console.log(`[gamepad] pressButton(${stickBtn})`);
      pressButton(stickBtn);
    }
  }
  prevStickBtn = stickBtn;

  // Face-button edges
  for (const idx in GAMEPAD_BUTTON_MAP) {
    const pressed = !!(gp.buttons[idx] && gp.buttons[idx].pressed);
    if (pressed !== !!prevButtonState[idx]) {
      if (GAMEPAD_DEBUG) console.log(`[gamepad] button${idx}: ${!!prevButtonState[idx]} -> ${pressed}`);
      if (pressed) {
        if (GAMEPAD_DEBUG) console.log(`[gamepad] pressButton(${GAMEPAD_BUTTON_MAP[idx]})`);
        pressButton(GAMEPAD_BUTTON_MAP[idx]);
      }
    }
    prevButtonState[idx] = pressed;
  }

  requestAnimationFrame(pollGamepad);
}

function startGamepadPolling() {
  if (gamepadPolling) return;
  gamepadPolling = true;
  if (GAMEPAD_DEBUG) console.log("[gamepad] polling started");
  requestAnimationFrame(pollGamepad);
}

window.addEventListener("gamepadconnected", (e) => {
  console.log(`[gamepad] connected: ${e.gamepad.id} (${e.gamepad.buttons.length} buttons, ${e.gamepad.axes.length} axes)`);
  startGamepadPolling();
});

// Some browsers don't fire gamepadconnected if the pad was already plugged in
// on page load — kick off polling anyway and it'll pick up a pad if present.
startGamepadPolling();

for (let i = 1; i <= 4; i++) {
  document.getElementById(`btn${i}-label`).addEventListener("click", () => {
    pressButton(`btn${i}`);
  });
}

// === Now Playing ===

function handleNowPlayingButton(btn) {
  if (btn === "btn1") send({ type: "command", action: "play_pause" });
  else if (btn === "btn2") {
    if (state.has_previous) send({ type: "command", action: "previous" });
  } else if (btn === "btn3") {
    if (state.has_next) send({ type: "command", action: "next" });
  }
}

function updateNowPlaying() {
  const art = document.getElementById("np-art");
  const placeholder = document.getElementById("np-placeholder");
  const title = document.getElementById("np-title");
  const artist = document.getElementById("np-artist");

  if (state.track) {
    art.src = state.track.image_url || "";
    art.classList.toggle("hidden", !state.track.image_url);
    placeholder.classList.toggle("hidden", !!state.track.image_url);
    title.textContent = state.track.title;
    artist.textContent = state.track.artist;
  } else {
    art.classList.add("hidden");
    placeholder.classList.remove("hidden");
    title.textContent = "";
    artist.textContent = "";
  }

  // Update play/pause label + prev/next disabled state if on Now Playing
  if (activeScreenId() === "now-playing") {
    document.getElementById("btn1-label").textContent = state.playing
      ? "Pause"
      : "Play";
    document.getElementById("btn2-label").classList.toggle("disabled", !state.has_previous);
    document.getElementById("btn3-label").classList.toggle("disabled", !state.has_next);
  }

  updateProgress();
}

function updateProgress() {
  const fill = document.getElementById("progress-fill");
  const elapsedEl = document.getElementById("elapsed");
  const durationEl = document.getElementById("duration");

  const elapsed = state.elapsed || 0;
  const duration = state.duration || 0;

  const pct = duration > 0 ? (elapsed / duration) * 100 : 0;
  fill.style.width = `${Math.min(pct, 100)}%`;
  elapsedEl.textContent = formatTime(elapsed);
  durationEl.textContent = formatTime(duration);
}

function startProgressInterpolation() {
  if (progressInterval) clearInterval(progressInterval);

  if (state.playing && state.duration > 0) {
    progressInterval = setInterval(() => {
      const secondsSinceUpdate = (Date.now() - lastStateTime) / 1000;
      const interpolated = (state.elapsed || 0) + secondsSinceUpdate;
      const pct = Math.min((interpolated / state.duration) * 100, 100);

      document.getElementById("progress-fill").style.width = `${pct}%`;
      document.getElementById("elapsed").textContent = formatTime(
        Math.min(interpolated, state.duration)
      );
    }, 1000);
  }
}

function formatTime(seconds) {
  const s = Math.floor(seconds);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

// === Browse ===

function handleBrowseButton(btn) {
  if (btn === "btn1") {
    // Select album -> play it
    if (albums.length > 0 && browseIndex < albums.length) {
      const album = albums[browseIndex];
      send({
        type: "command",
        action: "play_album",
        uri: album.uri,
        album_id: album.id,
      });
      switchScreen(0); // Go to Now Playing
    }
  } else if (btn === "btn2") {
    // Up
    if (browseIndex > 0) {
      browseIndex--;
      updateBrowseSelection();
    }
  } else if (btn === "btn3") {
    // Down
    if (browseIndex < albums.length - 1) {
      browseIndex++;
      updateBrowseSelection();

      // Load more when near the end
      if (browseIndex >= albums.length - 5 && albums.length % 50 === 0) {
        send({
          type: "command",
          action: "get_albums",
          offset: albums.length,
          limit: 50,
        });
      }
    }
  }
}

function renderAlbumList() {
  const container = document.getElementById("album-list");
  const empty = document.getElementById("albums-empty");

  // Clear existing items (preserve empty message)
  container.querySelectorAll(".list-item").forEach((el) => el.remove());

  if (albums.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  albums.forEach((album, i) => {
    const el = document.createElement("div");
    el.className = "list-item" + (i === browseIndex ? " selected" : "");
    el.dataset.index = i;
    el.innerHTML = `
      <img class="list-item-art" src="${escapeAttr(album.image_url)}" alt="" loading="lazy">
      <div class="list-item-info">
        <div class="list-item-title">${escapeHtml(album.name)}</div>
        <div class="list-item-artist">${escapeHtml(album.artist)}</div>
      </div>
    `;
    container.appendChild(el);
  });
}

function updateBrowseSelection() {
  const container = document.getElementById("album-list");
  container.querySelectorAll(".list-item").forEach((el, i) => {
    el.classList.toggle("selected", i === browseIndex);
  });

  const selected = container.querySelector(".list-item.selected");
  if (selected) {
    selected.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

// === Artists ===

function handleArtistsButton(btn) {
  if (btn === "btn1") {
    if (artists.length > 0 && artistIndex < artists.length) {
      enterArtistAlbums(artists[artistIndex]);
    }
  } else if (btn === "btn2") {
    if (artistIndex > 0) {
      artistIndex--;
      updateArtistSelection();
    }
  } else if (btn === "btn3") {
    if (artistIndex < artists.length - 1) {
      artistIndex++;
      updateArtistSelection();

      if (artistIndex >= artists.length - 5 && artists.length % 50 === 0) {
        send({
          type: "command",
          action: "get_artists",
          offset: artists.length,
          limit: 50,
        });
      }
    }
  }
}

function renderArtistList() {
  const container = document.getElementById("artist-list");
  const empty = document.getElementById("artists-empty");

  container.querySelectorAll(".list-item").forEach((el) => el.remove());

  if (artists.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  artists.forEach((artist, i) => {
    const el = document.createElement("div");
    el.className = "list-item" + (i === artistIndex ? " selected" : "");
    el.dataset.index = i;
    el.innerHTML = `
      <img class="list-item-art" src="${escapeAttr(artist.image_url)}" alt="" loading="lazy">
      <div class="list-item-info">
        <div class="list-item-title">${escapeHtml(artist.name)}</div>
      </div>
    `;
    container.appendChild(el);
  });
}

function updateArtistSelection() {
  const container = document.getElementById("artist-list");
  container.querySelectorAll(".list-item").forEach((el, i) => {
    el.classList.toggle("selected", i === artistIndex);
  });
  const selected = container.querySelector(".list-item.selected");
  if (selected) selected.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// === Artist Albums (drill) ===

function handleArtistAlbumsButton(btn) {
  if (btn === "btn1") {
    if (artistAlbums.length > 0 && artistAlbumsIndex < artistAlbums.length) {
      const album = artistAlbums[artistAlbumsIndex];
      send({ type: "command", action: "play_album", uri: album.uri, album_id: album.id });
      drillScreen = null;
      switchScreen(0); // Go to Now Playing
    }
  } else if (btn === "btn2") {
    if (artistAlbumsIndex > 0) {
      artistAlbumsIndex--;
      updateArtistAlbumsSelection();
    }
  } else if (btn === "btn3") {
    if (artistAlbumsIndex < artistAlbums.length - 1) {
      artistAlbumsIndex++;
      updateArtistAlbumsSelection();
    }
  }
}

function renderArtistAlbumList() {
  const container = document.getElementById("artist-album-list");
  const empty = document.getElementById("artist-albums-empty");

  container.querySelectorAll(".list-item").forEach((el) => el.remove());

  if (artistAlbums.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  artistAlbums.forEach((album, i) => {
    const el = document.createElement("div");
    el.className = "list-item" + (i === artistAlbumsIndex ? " selected" : "");
    el.dataset.index = i;
    el.innerHTML = `
      <img class="list-item-art" src="${escapeAttr(album.image_url)}" alt="" loading="lazy">
      <div class="list-item-info">
        <div class="list-item-title">${escapeHtml(album.name)}</div>
        <div class="list-item-artist">${escapeHtml(album.artist)}</div>
      </div>
    `;
    container.appendChild(el);
  });
}

function updateArtistAlbumsSelection() {
  const container = document.getElementById("artist-album-list");
  container.querySelectorAll(".list-item").forEach((el, i) => {
    el.classList.toggle("selected", i === artistAlbumsIndex);
  });
  const selected = container.querySelector(".list-item.selected");
  if (selected) selected.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// === Queue ===

function handleQueueButton(btn) {
  if (btn === "btn2") {
    // Up
    if (queueIndex > 0) {
      queueIndex--;
      updateQueueSelection();
    }
  } else if (btn === "btn3") {
    // Down
    if (queueIndex < queueItems.length - 1) {
      queueIndex++;
      updateQueueSelection();
    }
  }
}

function renderQueueList() {
  const container = document.getElementById("queue-list");
  const empty = document.getElementById("queue-empty");

  container.querySelectorAll(".list-item").forEach((el) => el.remove());

  if (queueItems.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  // Clamp index
  if (queueIndex >= queueItems.length) {
    queueIndex = Math.max(0, queueItems.length - 1);
  }

  queueItems.forEach((item, i) => {
    const el = document.createElement("div");
    let classes = "list-item";
    if (i === queueIndex) classes += " selected";
    if (i === 0) classes += " current-track"; // First item is current
    el.className = classes;
    el.dataset.index = i;
    el.innerHTML = `
      <img class="list-item-art" src="${escapeAttr(item.image_url)}" alt="" loading="lazy">
      <div class="list-item-info">
        <div class="list-item-title">${escapeHtml(item.title)}</div>
        <div class="list-item-artist">${escapeHtml(item.artist)}</div>
      </div>
    `;
    container.appendChild(el);
  });
}

function updateQueueSelection() {
  const container = document.getElementById("queue-list");
  container.querySelectorAll(".list-item").forEach((el, i) => {
    el.classList.toggle("selected", i === queueIndex);
  });

  const selected = container.querySelector(".list-item.selected");
  if (selected) {
    selected.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

// === Helpers ===

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function escapeAttr(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// === Init ===

switchScreen(0);
connect();
