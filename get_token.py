"""Get an API token from Music Assistant.

Usage:
  python get_token.py http://10.10.10.17:8095

You'll be prompted for username and password. The token will be printed
so you can set it as MA_TOKEN.
"""

import asyncio
import json
import sys

import aiohttp


async def get_token(url: str):
    url = url.rstrip("/")
    async with aiohttp.ClientSession() as session:
        print(f"Connecting to Music Assistant at {url}")
        print()

        # Step 1: Login with username/password to get a short-lived token
        username = input("MA Username: ").strip()
        password = input("MA Password: ").strip()

        login_url = f"{url}/auth/login"
        payload = {"credentials": {"username": username, "password": password}}

        try:
            async with session.post(login_url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("token"):
                    print(f"Login failed: {json.dumps(data, indent=2)}")
                    return

                short_token = data["token"]
                print(f"Login successful!")
                print()
        except Exception as e:
            print(f"Login request failed: {e}")
            return

        # Step 2: Use the short-lived token to create a long-lived token via WebSocket
        ws_url = f"{url.replace('http://', 'ws://').replace('https://', 'wss://')}/ws"
        try:
            async with session.ws_connect(ws_url) as ws:
                # Read and discard the initial server info message
                await ws.receive_json()

                # Authenticate
                await ws.send_json({
                    "message_id": "auth",
                    "command": "auth",
                    "args": {"token": short_token},
                })
                auth_resp = await ws.receive_json()
                if not auth_resp.get("result", {}).get("authenticated"):
                    print(f"WebSocket auth failed: {json.dumps(auth_resp, indent=2)}")
                    return

                # Create long-lived token
                await ws.send_json({
                    "message_id": "create-token",
                    "command": "auth/token/create",
                    "args": {"name": "Jukebox"},
                })
                token_resp = await ws.receive_json()
                # Skip event messages, find our response
                while token_resp.get("message_id") != "create-token":
                    token_resp = await ws.receive_json()

                long_token = token_resp.get("result")
                if not long_token:
                    # If create returns the token in a different shape, try the short token
                    print("Could not create long-lived token. Using session token instead.")
                    print("(Session tokens expire after 30 days of inactivity)")
                    long_token = short_token

                print(f"Token: {long_token}")
                print()
                print(f"Run the jukebox with:")
                print(f'  $env:MA_URL="{url}"; $env:MA_TOKEN="{long_token}"; python server.py')
        except Exception as e:
            # Fall back to using the short-lived token directly
            print(f"Could not create long-lived token ({e}). Using session token.")
            print(f"(Session tokens expire after 30 days of inactivity)")
            print()
            print(f"Run the jukebox with:")
            print(f'  $env:MA_URL="{url}"; $env:MA_TOKEN="{short_token}"; python server.py')


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8095"
    asyncio.run(get_token(url))
