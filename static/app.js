// === Key Bindings (R12) ===
const KEY_MAP = {
  "1": "btn1",
  "2": "btn2",
  "3": "btn3",
  "4": "btn4",
  "5": "btn5",
  "6": "btn6",
};

// === Button labels per screen ===
const SCREEN_LABELS = {
  "now-playing": {
    btn1: "Play/Pause",
    btn2: "Previous",
    btn3: "Next",
    btn4: "Favorite",
    btn5: "Shuffle",
    btn6: "Next Screen",
  },
  browse: {
    btn1: "Select",
    btn2: "Up",
    btn3: "Down",
    btn4: "Favorite",
    btn5: "Shuffle",
    btn6: "Next Screen",
  },
  queue: {
    btn1: "Remove",
    btn2: "Up",
    btn3: "Down",
    btn4: "Favorite",
    btn5: "Shuffle",
    btn6: "Next Screen",
  },
};

// === State ===
const SCREENS = ["now-playing", "browse", "queue"];
let currentScreen = 0;
let ws = null;
let reconnectDelay = 1000;

let state = {
  connected: false,
  playing: false,
  shuffle: false,
  track: null,
  elapsed: 0,
  duration: 0,
};

// Browse state
let albums = [];
let albumsLoaded = false;
let browseIndex = 0;

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
  } else if (msg.type === "error") {
    console.error("Server error:", msg.message);
  }
}

// === Screen Management ===

function switchScreen(index) {
  currentScreen = index;
  const screenId = SCREENS[currentScreen];

  document.querySelectorAll(".screen").forEach((el) => {
    el.classList.remove("active");
  });
  document.getElementById(screenId).classList.add("active");

  updateButtonLabels();

  // Load data when entering screens
  if (screenId === "browse" && !albumsLoaded) {
    send({ type: "command", action: "get_albums", offset: 0, limit: 50 });
  }
  if (screenId === "queue") {
    send({ type: "command", action: "get_queue" });
  }
}

function cycleScreen() {
  switchScreen((currentScreen + 1) % SCREENS.length);
}

function updateButtonLabels() {
  const labels = SCREEN_LABELS[SCREENS[currentScreen]];
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`btn${i}-label`);
    el.textContent = labels[`btn${i}`];
    el.setAttribute("data-key", i);
  }

  // Dynamic label for play/pause on Now Playing
  if (SCREENS[currentScreen] === "now-playing") {
    document.getElementById("btn1-label").textContent = state.playing
      ? "Pause"
      : "Play";
  }
}

// === Input Handling (R11) ===

document.addEventListener("keydown", (e) => {
  const btn = KEY_MAP[e.key];
  if (!btn) return;
  e.preventDefault();

  // Global buttons (same on every screen)
  if (btn === "btn6") {
    cycleScreen();
    return;
  }
  if (btn === "btn4") {
    send({ type: "command", action: "favorite" });
    return;
  }
  if (btn === "btn5") {
    send({ type: "command", action: "shuffle" });
    return;
  }

  // Context-sensitive buttons (1-3)
  const screen = SCREENS[currentScreen];
  if (screen === "now-playing") {
    handleNowPlayingButton(btn);
  } else if (screen === "browse") {
    handleBrowseButton(btn);
  } else if (screen === "queue") {
    handleQueueButton(btn);
  }
});

// === Now Playing ===

function handleNowPlayingButton(btn) {
  if (btn === "btn1") send({ type: "command", action: "play_pause" });
  else if (btn === "btn2") send({ type: "command", action: "previous" });
  else if (btn === "btn3") send({ type: "command", action: "next" });
}

function updateNowPlaying() {
  const art = document.getElementById("np-art");
  const placeholder = document.getElementById("np-placeholder");
  const title = document.getElementById("np-title");
  const artist = document.getElementById("np-artist");
  const shuffleInd = document.getElementById("shuffle-indicator");
  const favInd = document.getElementById("favorite-indicator");

  if (state.track) {
    art.src = state.track.image_url || "";
    art.classList.toggle("hidden", !state.track.image_url);
    placeholder.classList.toggle("hidden", !!state.track.image_url);
    title.textContent = state.track.title;
    artist.textContent = state.track.artist;
    favInd.classList.toggle("hidden", !state.track.favorite);
  } else {
    art.classList.add("hidden");
    placeholder.classList.remove("hidden");
    title.textContent = "";
    artist.textContent = "";
    favInd.classList.add("hidden");
  }

  shuffleInd.classList.toggle("hidden", !state.shuffle);

  // Update play/pause label if on Now Playing screen
  if (SCREENS[currentScreen] === "now-playing") {
    document.getElementById("btn1-label").textContent = state.playing
      ? "Pause"
      : "Play";
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

// === Queue ===

function handleQueueButton(btn) {
  if (btn === "btn1") {
    // Remove
    if (queueItems.length > 0 && queueIndex < queueItems.length) {
      const item = queueItems[queueIndex];
      send({
        type: "command",
        action: "remove_queue_item",
        item_id: item.id,
      });
      // Adjust index if we removed the last item
      if (queueIndex >= queueItems.length - 1 && queueIndex > 0) {
        queueIndex--;
      }
    }
  } else if (btn === "btn2") {
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
