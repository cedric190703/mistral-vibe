"""Local WebSocket bridge between Vibe and the Vibe-in-Chrome extension.

A Chrome MV3 service worker can only be a WebSocket *client*, so Vibe hosts the
server (bound to 127.0.0.1) and the extension connects to it. The tool sends
JSON commands and awaits the matching response, correlated by an ``id``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from vibe.core.logger import logger


class ExtensionBridge:
    """Owns the local WS server and the single connected extension client."""

    def __init__(self) -> None:
        self._server: Any = None
        self._client: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._started = False
        self._client_event = asyncio.Event()

    async def ensure_started(self, port: int, *, grace: float = 0.0) -> None:
        """Start the server (once) and wait ``grace`` seconds for a first client.

        The grace wait applies only on the initial start, so later calls return
        immediately and simply reflect the current connection state.
        """
        if self._started:
            return
        from websockets.asyncio.server import serve

        try:
            self._server = await serve(self._handler, "127.0.0.1", port)
            self._started = True
            logger.info("vibe-in-chrome bridge listening on 127.0.0.1:%d", port)
        except OSError as exc:
            logger.warning("vibe-in-chrome bridge could not bind :%d — %s", port, exc)
            return
        if grace > 0 and self._client is None:
            try:
                await asyncio.wait_for(self._client_event.wait(), timeout=grace)
            except TimeoutError:
                pass

    async def _handler(self, ws: Any) -> None:
        self._client = ws
        self._client_event.set()
        logger.info("vibe-in-chrome extension connected")
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                mid = msg.get("id")
                if mid and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
        finally:
            if self._client is ws:
                self._client = None
                self._client_event.clear()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("extension disconnected"))
            self._pending.clear()

    def is_connected(self) -> bool:
        return self._client is not None

    async def send(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        client = self._client
        if client is None:
            raise ConnectionError("no extension connected")
        mid = uuid4().hex
        payload["id"] = mid
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await client.send(json.dumps(payload))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(mid, None)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        self._server = None
        self._client = None
        self._started = False
        self._client_event = asyncio.Event()


_BRIDGE: ExtensionBridge | None = None


def bridge() -> ExtensionBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = ExtensionBridge()
    return _BRIDGE


async def close_bridge() -> None:
    global _BRIDGE
    if _BRIDGE is not None:
        await _BRIDGE.close()
        _BRIDGE = None
