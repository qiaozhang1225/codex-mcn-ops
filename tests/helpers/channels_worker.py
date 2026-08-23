from __future__ import annotations

import asyncio
import gzip
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed


Responder = Callable[[str, dict[str, Any]], Awaitable[Any]]


class MockChannelsWorker:
    def __init__(
        self,
        *,
        uri: str,
        secret: str,
        worker_id: str,
        responder: Responder,
        gzip_messages: bool = False,
    ) -> None:
        self.uri = uri
        self.secret = secret
        self.worker_id = worker_id
        self.responder = responder
        self.gzip_messages = gzip_messages
        self.connection: ClientConnection | None = None
        self.task: asyncio.Task[None] | None = None
        self.connected = asyncio.Event()
        self.stop_event = asyncio.Event()

    async def start(self) -> None:
        self.task = asyncio.create_task(self._run())
        await asyncio.wait_for(self.connected.wait(), timeout=2)

    async def stop(self) -> None:
        self.stop_event.set()
        if self.connection is not None:
            await self.connection.close()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)

    async def disconnect(self) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def _run(self) -> None:
        try:
            async with connect(
                self.uri,
                additional_headers={
                    "X-Cloud-Secret": self.secret,
                    "X-Client-ID": self.worker_id,
                },
            ) as connection:
                self.connection = connection
                await self._send(
                    {
                        "id": f"hb-{time.time_ns()}",
                        "type": "heartbeat",
                        "client_id": self.worker_id,
                        "payload": {
                            "hostname": "mock-windows",
                            "version": "test",
                            "status": "running",
                            "api_ready": True,
                            "supports_search": True,
                            "supports_feed": True,
                            "supports_profile": True,
                            "methods": {"finderSearch": True},
                        },
                        "timestamp": int(time.time()),
                    }
                )
                self.connected.set()
                async for raw in connection:
                    if self.stop_event.is_set():
                        return
                    if isinstance(raw, bytes):
                        raw = gzip.decompress(raw).decode("utf-8")
                    message = json.loads(raw)
                    if message.get("type") != "command":
                        continue
                    payload = message.get("payload") or {}
                    action = str(payload.get("action") or "")
                    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                    try:
                        response_data = await self.responder(action, data)
                    except Exception as exc:
                        await self._send_response(message, success=False, data=None, error=str(exc))
                    else:
                        await self._send_response(message, success=True, data=response_data, error="")
        except ConnectionClosed:
            pass
        finally:
            self.connected.set()

    async def _send_response(
        self,
        command: dict[str, Any],
        *,
        success: bool,
        data: Any,
        error: str,
    ) -> None:
        await self._send(
            {
                "id": f"resp-{command['id']}",
                "type": "response",
                "client_id": self.worker_id,
                "payload": {
                    "request_id": command["id"],
                    "success": success,
                    "data": data,
                    "error": error,
                },
                "timestamp": int(time.time()),
            }
        )

    async def _send(self, message: dict[str, Any]) -> None:
        if self.connection is None:
            raise RuntimeError("mock worker is not connected")
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        await self.connection.send(gzip.compress(encoded) if self.gzip_messages else encoded.decode("utf-8"))
