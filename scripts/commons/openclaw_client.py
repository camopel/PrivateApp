"""OpenClaw messaging client for privateapp apps.

Apps import this module to send messages to OpenClaw chat rooms
(Matrix, Discord, Telegram, etc.) through the OpenClaw gateway API.

Usage in an app's routes.py:

    from privateapp_openclaw import send_message, get_gateway_url
    await send_message("Alert: stock NVDA dropped 5%!", room="cronjob")

The module auto-discovers the OpenClaw gateway:
  1. OPENCLAW_GATEWAY_URL env var
  2. Read from ~/.openclaw/openclaw.json
  3. Default: http://localhost:18789

This is a lightweight HTTP client — no OpenClaw SDK required.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import logging
from pathlib import Path

log = logging.getLogger("privateapp.openclaw_client")


def get_gateway_url() -> str:
    """Discover the OpenClaw gateway URL."""
    # 1. Env var
    url = os.environ.get("OPENCLAW_GATEWAY_URL")
    if url:
        return url.rstrip("/")

    # 2. Read from config
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            port = cfg.get("gateway", {}).get("port", 18789)
            host = cfg.get("gateway", {}).get("host", "127.0.0.1")
            return f"http://{host}:{port}"
        except Exception:
            pass

    # 3. Default
    return "http://localhost:18789"


async def send_message(
    message: str,
    room: str | None = None,
    channel: str | None = None,
) -> bool:
    """Send a message to an OpenClaw chat room.

    Args:
        message: Text to send
        room:    Room name or ID (optional — uses default if not specified)
        channel: Channel type (matrix, discord, telegram, etc.)

    Returns:
        True if sent successfully.
    """
    try:
        gateway = get_gateway_url()
        url = f"{gateway}/api/v1/message"

        payload: dict = {"message": message}
        if room:
            payload["room"] = room
        if channel:
            payload["channel"] = channel

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200

    except Exception as e:
        log.warning(f"OpenClaw message failed: {e}")
        return False


def send_message_sync(
    message: str,
    room: str | None = None,
    channel: str | None = None,
) -> bool:
    """Synchronous version."""
    try:
        gateway = get_gateway_url()
        url = f"{gateway}/api/v1/message"

        payload: dict = {"message": message}
        if room:
            payload["room"] = room
        if channel:
            payload["channel"] = channel

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200

    except Exception as e:
        log.warning(f"OpenClaw message failed: {e}")
        return False
