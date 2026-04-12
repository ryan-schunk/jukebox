"""Tests for the jukebox server.

These tests exercise the HTTP routes, WebSocket protocol, and command
dispatch without needing a real Music Assistant instance.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

import server


def make_app() -> web.Application:
    """Create the app without the MA background task."""
    app = web.Application()
    app.router.add_get("/", server.index)
    app.router.add_get("/ws", server.websocket_handler)
    app.router.add_get("/image", server.image_proxy)
    return app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state between tests."""
    server.rt.update({
        "ma_client": None,
        "ma_connected": False,
        "http_session": None,
        "active_player_id": "",
        "active_queue_id": "",
        "current_track": None,
        "shuffle_enabled": False,
        "ma_task": None,
    })
    server.clients.clear()
    yield


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
async def client(aiohttp_client, app):
    return await aiohttp_client(app)


# --- HTTP route tests ---


async def test_index_returns_html(client):
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "Jukebox" in text
    assert "text/html" in resp.content_type


async def test_image_proxy_returns_fallback_pixel(client):
    """When MA is not connected, image proxy returns a 1x1 transparent PNG."""
    resp = await client.get("/image?path=fake&size=300&fmt=jpeg")
    assert resp.status == 200
    assert resp.content_type == "image/png"
    body = await resp.read()
    assert body[:4] == b"\x89PNG"


# --- WebSocket tests ---


async def test_ws_receives_disconnected_state(client):
    """New WS client gets a state message with connected=False when MA is down."""
    async with client.ws_connect("/ws") as ws:
        msg = await ws.receive_json()
        assert msg["type"] == "state"
        assert msg["data"]["connected"] is False


async def test_ws_receives_connected_state(client):
    """New WS client gets full state when MA is connected."""
    server.rt["ma_connected"] = True
    server.rt["active_player_id"] = "test-player"
    server.rt["active_queue_id"] = "test-queue"

    # Mock the MA client with empty players/queues
    ma = MagicMock()
    ma.players = []
    ma.player_queues = []
    server.rt["ma_client"] = ma

    async with client.ws_connect("/ws") as ws:
        msg = await ws.receive_json()
        assert msg["type"] == "state"
        assert msg["data"]["connected"] is True
        assert msg["data"]["playing"] is False


async def test_ws_command_when_disconnected(client):
    """Commands sent when MA is disconnected return an error."""
    async with client.ws_connect("/ws") as ws:
        # Consume initial state
        await ws.receive_json()

        await ws.send_json({"type": "command", "action": "play_pause"})
        msg = await ws.receive_json()
        assert msg["type"] == "error"
        assert "Not connected" in msg["message"]


async def test_ws_play_pause_command(client):
    """play_pause command calls the queue API."""
    ma = MagicMock()
    ma.player_queues = MagicMock()
    ma.player_queues.play_pause = AsyncMock()
    ma.players = []

    server.rt["ma_client"] = ma
    server.rt["ma_connected"] = True
    server.rt["active_queue_id"] = "test-queue"

    async with client.ws_connect("/ws") as ws:
        await ws.receive_json()  # initial state

        await ws.send_json({"type": "command", "action": "play_pause"})
        # Give the handler time to process
        import asyncio
        await asyncio.sleep(0.05)

        ma.player_queues.play_pause.assert_called_once_with("test-queue")


async def test_ws_next_previous_commands(client):
    """next and previous commands call the queue API."""
    ma = MagicMock()
    ma.player_queues = MagicMock()
    ma.player_queues.next = AsyncMock()
    ma.player_queues.previous = AsyncMock()
    ma.players = []

    server.rt["ma_client"] = ma
    server.rt["ma_connected"] = True
    server.rt["active_queue_id"] = "test-queue"

    async with client.ws_connect("/ws") as ws:
        await ws.receive_json()

        await ws.send_json({"type": "command", "action": "next"})
        await ws.send_json({"type": "command", "action": "previous"})

        import asyncio
        await asyncio.sleep(0.05)

        ma.player_queues.next.assert_called_once_with("test-queue")
        ma.player_queues.previous.assert_called_once_with("test-queue")


async def test_ws_shuffle_command(client):
    """shuffle command toggles shuffle state."""
    ma = MagicMock()
    ma.player_queues = MagicMock()
    ma.player_queues.shuffle = AsyncMock()
    ma.players = []

    server.rt["ma_client"] = ma
    server.rt["ma_connected"] = True
    server.rt["active_queue_id"] = "test-queue"
    server.rt["shuffle_enabled"] = False

    async with client.ws_connect("/ws") as ws:
        await ws.receive_json()

        await ws.send_json({"type": "command", "action": "shuffle"})

        import asyncio
        await asyncio.sleep(0.05)

        ma.player_queues.shuffle.assert_called_once_with("test-queue", True)


async def test_ws_play_album_command(client):
    """play_album command sends the right URI to the queue."""
    ma = MagicMock()
    ma.player_queues = MagicMock()
    ma.player_queues.play_media = AsyncMock()
    ma.players = []

    server.rt["ma_client"] = ma
    server.rt["ma_connected"] = True
    server.rt["active_queue_id"] = "test-queue"

    async with client.ws_connect("/ws") as ws:
        await ws.receive_json()

        await ws.send_json({"type": "command", "action": "play_album", "album_id": "42"})

        import asyncio
        await asyncio.sleep(0.05)

        ma.player_queues.play_media.assert_called_once_with(
            "test-queue", media=["library://album/42"], option="replace"
        )


async def test_ws_unknown_action_no_crash(client):
    """Unknown actions are logged but don't crash."""
    ma = MagicMock()
    ma.players = []
    ma.player_queues = []

    server.rt["ma_client"] = ma
    server.rt["ma_connected"] = True

    async with client.ws_connect("/ws") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "command", "action": "nonexistent"})
        # Should not crash; no error sent back for unknown actions


# --- discover_player tests ---


async def test_discover_player_by_config():
    """discover_player selects the configured player."""
    player = SimpleNamespace(
        player_id="my-player",
        name="My Player",
        active_source="my-player",
    )
    queue = SimpleNamespace(queue_id="my-player", display_name="My Player")

    ma = MagicMock()
    ma.players = [player]
    ma.player_queues = [queue]
    server.rt["ma_client"] = ma

    with patch.object(server, "MA_PLAYER", "my-player"):
        await server.discover_player()

    assert server.rt["active_player_id"] == "my-player"
    assert server.rt["active_queue_id"] == "my-player"


async def test_discover_player_by_name():
    """discover_player can match by player name."""
    player = SimpleNamespace(
        player_id="abc123",
        name="Living Room Speaker",
        active_source="abc123",
    )
    queue = SimpleNamespace(queue_id="abc123", display_name="Living Room Speaker")

    ma = MagicMock()
    ma.players = [player]
    ma.player_queues = [queue]
    server.rt["ma_client"] = ma

    with patch.object(server, "MA_PLAYER", "Living Room Speaker"):
        await server.discover_player()

    assert server.rt["active_player_id"] == "abc123"


async def test_discover_player_fallback_to_first():
    """discover_player falls back to the first player when no config."""
    player = SimpleNamespace(
        player_id="first-player",
        name="First",
        active_source="first-player",
    )
    queue = SimpleNamespace(queue_id="first-player", display_name="First")

    ma = MagicMock()
    ma.players = [player]
    ma.player_queues = [queue]
    server.rt["ma_client"] = ma

    with patch.object(server, "MA_PLAYER", ""):
        await server.discover_player()

    assert server.rt["active_player_id"] == "first-player"


# --- broadcast tests ---


async def test_broadcast_removes_dead_clients():
    """broadcast cleans up clients that fail to receive."""
    good_ws = AsyncMock()
    bad_ws = AsyncMock()
    bad_ws.send_str.side_effect = ConnectionError("gone")

    server.clients = {good_ws, bad_ws}
    await server.broadcast({"type": "test"})

    assert bad_ws not in server.clients
    assert good_ws in server.clients
