import asyncio
import json
import logging
import os
from urllib.parse import urlencode

import aiohttp
from dotenv import load_dotenv

load_dotenv()
from aiohttp import web

log = logging.getLogger(__name__)

MA_URL = os.environ.get("MA_URL", "http://localhost:8095")
MA_TOKEN = os.environ.get("MA_TOKEN", "")
MA_PLAYER = os.environ.get("MA_PLAYER", "")
HOST = os.environ.get("JUKEBOX_HOST", "0.0.0.0")
PORT = int(os.environ.get("JUKEBOX_PORT", "8080"))

# --- Mutable runtime state (avoids aiohttp app[] deprecation) ---
rt: dict = {
    "ma_client": None,
    "ma_connected": False,
    "http_session": None,
    "active_player_id": "",
    "active_queue_id": "",
    "ma_task": None,
}

# --- Connected browser clients ---
clients: set[web.WebSocketResponse] = set()


async def broadcast(msg: dict):
    """Send a JSON message to all connected browser clients."""
    data = json.dumps(msg)
    dead = set()
    for ws in clients:
        try:
            await ws.send_str(data)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


# --- Routes ---

async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html")
    )


async def image_proxy(request: web.Request) -> web.Response:
    """Proxy album art requests to Music Assistant's imageproxy."""
    params = dict(request.query)
    url = f"{MA_URL}/imageproxy?{urlencode(params)}"
    try:
        session: aiohttp.ClientSession = rt["http_session"]
        async with session.get(url) as resp:
            if resp.status == 200:
                body = await resp.read()
                return web.Response(
                    body=body,
                    content_type=resp.content_type or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
    except Exception:
        pass
    # 1x1 transparent pixel fallback
    pixel = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return web.Response(body=pixel, content_type="image/png")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)
    clients.add(ws)
    log.info("Browser client connected (%d total)", len(clients))

    # Push initial state to new client
    await push_full_state(ws_target=ws)

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await handle_command(ws, data)
                except json.JSONDecodeError:
                    log.warning("Invalid JSON from browser: %s", msg.data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.warning("WebSocket error: %s", ws.exception())
    finally:
        clients.discard(ws)
        log.info("Browser client disconnected (%d remaining)", len(clients))

    return ws


async def handle_command(ws: web.WebSocketResponse, data: dict):
    """Dispatch a command from the browser to Music Assistant."""
    action = data.get("action")
    ma = rt.get("ma_client")

    if ma is None or not rt.get("ma_connected"):
        await ws.send_json({"type": "error", "message": "Not connected to Music Assistant"})
        return

    player_id = rt.get("active_player_id", "")
    queue_id = rt.get("active_queue_id", "")

    try:
        if action == "play_pause":
            await ma.player_queues.play_pause(queue_id)
        elif action == "next":
            await ma.player_queues.next(queue_id)
        elif action == "previous":
            await ma.player_queues.previous(queue_id)
        elif action == "play_album":
            uri = data.get("uri")
            if not uri:
                album_id = data.get("album_id")
                if album_id:
                    uri = f"library://album/{album_id}"
            if uri:
                await ma.player_queues.play_media(queue_id, media=[uri], option="replace")
        elif action == "get_albums":
            offset = data.get("offset", 0)
            limit = data.get("limit", 50)
            albums = await ma.music.get_library_albums(limit=limit, offset=offset)
            album_list = []
            for a in albums.items if hasattr(albums, "items") else albums:
                image_url = ""
                if hasattr(a, "image") and a.image:
                    image_url = f"/image?{urlencode({'path': a.image.path, 'size': '300', 'fmt': 'jpeg'})}" if hasattr(a.image, "path") else ""
                elif hasattr(a, "metadata") and hasattr(a.metadata, "images") and a.metadata.images:
                    img = a.metadata.images[0]
                    path = img.path if hasattr(img, "path") else str(img)
                    image_url = f"/image?{urlencode({'path': path, 'size': '300', 'fmt': 'jpeg'})}"
                album_list.append({
                    "id": str(a.item_id) if hasattr(a, "item_id") else str(a.uri),
                    "uri": getattr(a, "uri", ""),
                    "name": a.name,
                    "artist": a.artists[0].name if hasattr(a, "artists") and a.artists else "Unknown Artist",
                    "image_url": image_url,
                })
            await ws.send_json({"type": "albums", "data": album_list, "offset": offset})
        elif action == "get_artists":
            offset = data.get("offset", 0)
            limit = data.get("limit", 50)
            artists = await ma.music.get_library_artists(
                limit=limit, offset=offset, order_by="sort_name", album_artists_only=True
            )
            artist_list = []
            for a in artists.items if hasattr(artists, "items") else artists:
                image_url = ""
                if hasattr(a, "image") and a.image:
                    image_url = f"/image?{urlencode({'path': a.image.path, 'size': '200', 'fmt': 'jpeg'})}" if hasattr(a.image, "path") else ""
                elif hasattr(a, "metadata") and hasattr(a.metadata, "images") and a.metadata.images:
                    img = a.metadata.images[0]
                    path = img.path if hasattr(img, "path") else str(img)
                    image_url = f"/image?{urlencode({'path': path, 'size': '200', 'fmt': 'jpeg'})}"
                artist_list.append({
                    "id": str(a.item_id),
                    "provider": a.provider,
                    "name": a.name,
                    "image_url": image_url,
                })
            await ws.send_json({"type": "artists", "data": artist_list, "offset": offset})
        elif action == "get_artist_albums":
            artist_id = data.get("artist_id")
            provider = data.get("provider")
            if not artist_id or not provider:
                return
            albums = await ma.music.get_artist_albums(artist_id, provider)
            album_list = []
            for a in albums.items if hasattr(albums, "items") else albums:
                image_url = ""
                if hasattr(a, "image") and a.image:
                    image_url = f"/image?{urlencode({'path': a.image.path, 'size': '300', 'fmt': 'jpeg'})}" if hasattr(a.image, "path") else ""
                elif hasattr(a, "metadata") and hasattr(a.metadata, "images") and a.metadata.images:
                    img = a.metadata.images[0]
                    path = img.path if hasattr(img, "path") else str(img)
                    image_url = f"/image?{urlencode({'path': path, 'size': '300', 'fmt': 'jpeg'})}"
                album_list.append({
                    "id": str(a.item_id),
                    "uri": getattr(a, "uri", ""),
                    "name": a.name,
                    "artist": a.artists[0].name if hasattr(a, "artists") and a.artists else "Unknown Artist",
                    "image_url": image_url,
                })
            await ws.send_json({"type": "artist_albums", "data": album_list})
        elif action == "get_queue":
            items = await ma.player_queues.get_queue_items(queue_id, limit=100, offset=0)
            queue_list = []
            for item in items.items if hasattr(items, "items") else items:
                track = item.media_item if hasattr(item, "media_item") else item
                image_url = ""
                if hasattr(track, "image") and track.image:
                    image_url = f"/image?{urlencode({'path': track.image.path, 'size': '80', 'fmt': 'jpeg'})}" if hasattr(track.image, "path") else ""
                queue_list.append({
                    "id": str(item.queue_item_id) if hasattr(item, "queue_item_id") else str(item.item_id),
                    "title": track.name if hasattr(track, "name") else "Unknown",
                    "artist": track.artists[0].name if hasattr(track, "artists") and track.artists else "Unknown Artist",
                    "image_url": image_url,
                })
            await ws.send_json({"type": "queue", "data": queue_list})
        else:
            log.warning("Unknown action: %s", action)
    except Exception as e:
        log.exception("Error handling command %s", action)
        await ws.send_json({"type": "error", "message": str(e)})


# --- Music Assistant connection ---

async def connect_to_ma():
    """Connect to Music Assistant and start listening for events."""
    from music_assistant_client import MusicAssistantClient

    rt["ma_connected"] = False

    try:
        session = aiohttp.ClientSession()
        rt["http_session"] = session

        client = MusicAssistantClient(MA_URL, session, token=MA_TOKEN if MA_TOKEN else None)
        rt["ma_client"] = client

        # Subscribe to events before connecting
        client.subscribe(lambda event: asyncio.create_task(on_ma_event(event)))

        init_ready = asyncio.Event()

        async def on_ready():
            await init_ready.wait()
            rt["ma_connected"] = True
            log.info("Connected to Music Assistant at %s", MA_URL)
            await discover_player()
            await push_full_state()

        asyncio.create_task(on_ready())
        await client.start_listening(init_ready=init_ready)

    except Exception:
        log.exception("Failed to connect to Music Assistant at %s", MA_URL)
        rt["ma_connected"] = False
        await broadcast({"type": "state", "data": {"connected": False}})


async def discover_player():
    """Find and select the active player/queue."""
    ma = rt["ma_client"]
    try:
        players = list(ma.players)
        for p in players:
            log.info("Found player: %s (id=%s, active_source=%s)", p.name, p.player_id, getattr(p, "active_source", None))

        queues = list(ma.player_queues)
        queue_map = {}
        for q in queues:
            qid = getattr(q, "queue_id", None) or getattr(q, "player_id", None)
            log.info("Found queue: %s (queue_id=%s)", getattr(q, "display_name", qid), qid)
            if qid:
                queue_map[qid] = q

        selected = None
        if MA_PLAYER:
            for p in players:
                if p.player_id == MA_PLAYER or p.name == MA_PLAYER:
                    selected = p
                    log.info("Using configured player: %s (%s)", p.name, p.player_id)
                    break
            if not selected:
                log.warning("Configured player '%s' not found, falling back to first", MA_PLAYER)

        if not selected and players:
            selected = players[0]

        if selected:
            rt["active_player_id"] = selected.player_id
            # Use the player's own queue if it exists, otherwise try active_source
            if selected.player_id in queue_map:
                rt["active_queue_id"] = selected.player_id
            elif getattr(selected, "active_source", None) and selected.active_source in queue_map:
                rt["active_queue_id"] = selected.active_source
            elif queues:
                fallback_id = getattr(queues[0], "queue_id", None) or getattr(queues[0], "player_id", None)
                rt["active_queue_id"] = fallback_id
            else:
                rt["active_queue_id"] = selected.player_id
            log.info("Selected player: %s, queue: %s", rt["active_player_id"], rt["active_queue_id"])
        else:
            log.warning("No players found in Music Assistant")
    except Exception:
        log.exception("Error discovering players")


async def on_ma_event(event):
    """Handle events from Music Assistant."""
    try:
        event_type = event.event if hasattr(event, "event") else str(event)

        if event_type in ("player_added", "player_removed", "player_updated", "queue_updated", "queue_time_updated"):
            ma = rt.get("ma_client")
            if ma:
                active_id = rt.get("active_player_id", "")
                current_ids = {p.player_id for p in ma.players}
                if not active_id or active_id not in current_ids:
                    log.info("Active player %r missing; rediscovering", active_id)
                    await discover_player()
            await push_full_state()
        else:
            log.debug("Unhandled event type: %s", event_type)
    except Exception:
        log.exception("Error handling MA event")


async def push_full_state(ws_target=None):
    """Build and broadcast the current playback state. If ws_target is given, send only to that client."""
    ma = rt.get("ma_client")
    if not ma or not rt.get("ma_connected"):
        msg = {"type": "state", "data": {"connected": False}}
        if ws_target:
            try:
                await ws_target.send_json(msg)
            except Exception:
                pass
        else:
            await broadcast(msg)
        return

    player_id = rt.get("active_player_id", "")
    queue_id = rt.get("active_queue_id", "")

    try:
        # Get player state
        player = None
        players = list(ma.players)
        for p in players:
            if p.player_id == player_id:
                player = p
                break

        # Get queue state
        queue = None
        try:
            queues = list(ma.player_queues)
            for q in queues:
                if hasattr(q, "queue_id") and q.queue_id == queue_id:
                    queue = q
                    break
                elif hasattr(q, "player_id") and q.player_id == player_id:
                    queue = q
                    break
        except Exception:
            pass

        state = {
            "connected": True,
            "playing": False,
            "track": None,
            "elapsed": 0,
            "duration": 0,
            "has_next": False,
            "has_previous": False,
        }

        if player:
            state["playing"] = str(getattr(player, "playback_state", "")).lower() == "playing"

        if queue:
            state["elapsed"] = getattr(queue, "elapsed_time", 0) or 0

            items_count = getattr(queue, "items", 0) or 0
            current_index = getattr(queue, "current_index", None)
            if current_index is None:
                current_index = 0
            state["has_next"] = items_count > current_index + 1
            state["has_previous"] = current_index > 0

            current_item = getattr(queue, "current_item", None)
            if current_item:
                track = getattr(current_item, "media_item", current_item)
                # Track duration lives on the queue item / media item, not the queue itself.
                state["duration"] = (
                    getattr(current_item, "duration", None)
                    or getattr(track, "duration", None)
                    or 0
                )
                image_url = ""
                if hasattr(track, "image") and track.image:
                    image_url = f"/image?{urlencode({'path': track.image.path, 'size': '600', 'fmt': 'jpeg'})}" if hasattr(track.image, "path") else ""
                elif hasattr(track, "metadata") and hasattr(track.metadata, "images") and track.metadata.images:
                    img = track.metadata.images[0]
                    path = img.path if hasattr(img, "path") else str(img)
                    image_url = f"/image?{urlencode({'path': path, 'size': '600', 'fmt': 'jpeg'})}"

                state["track"] = {
                    "title": track.name if hasattr(track, "name") else "Unknown",
                    "artist": track.artists[0].name if hasattr(track, "artists") and track.artists else "Unknown Artist",
                    "album": track.album.name if hasattr(track, "album") and track.album else "",
                    "image_url": image_url,
                }

        if ws_target:
            try:
                await ws_target.send_json({"type": "state", "data": state})
            except Exception:
                pass
        else:
            await broadcast({"type": "state", "data": state})

    except Exception:
        log.exception("Error building state")


async def start_ma_background(app: web.Application):
    """Start MA connection as a background task."""
    rt["ma_task"] = asyncio.create_task(connect_to_ma())


async def state_endpoint(request: web.Request) -> web.Response:
    """Plain JSON snapshot of playback state. Consumed by the Pi display-sleep watcher."""
    ma = rt.get("ma_client")
    connected = bool(ma and rt.get("ma_connected"))
    playing = False
    if connected:
        player_id = rt.get("active_player_id", "")
        for p in list(ma.players):
            if p.player_id == player_id:
                playing = str(getattr(p, "playback_state", "")).lower() == "playing"
                break
    return web.json_response({"connected": connected, "playing": playing})


async def cleanup(app: web.Application):
    """Clean up on shutdown."""
    task = rt.get("ma_task")
    if task:
        task.cancel()
    session = rt.get("http_session")
    if session:
        await session.close()
    ma = rt.get("ma_client")
    if ma:
        try:
            await ma.disconnect()
        except Exception:
            pass


@web.middleware
async def no_cache_middleware(request: web.Request, handler):
    """Force the kiosk browser to revalidate HTML/CSS/JS on every load so that
    a redeploy or a user-triggered reload always picks up the latest code."""
    resp = await handler(request)
    path = request.path
    if path == "/" or path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


def create_app() -> web.Application:
    app = web.Application(middlewares=[no_cache_middleware])
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/image", image_proxy)
    app.router.add_get("/state", state_endpoint)
    app.router.add_static("/static/", os.path.join(os.path.dirname(__file__), "static"))
    app.on_startup.append(start_ma_background)
    app.on_cleanup.append(cleanup)
    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    log.info("Starting Jukebox on %s:%d", HOST, PORT)
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
