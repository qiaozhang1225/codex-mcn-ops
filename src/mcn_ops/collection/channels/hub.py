from __future__ import annotations

import asyncio
import hmac
import json
import ssl
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .contracts import (
    MAX_MESSAGE_BYTES,
    REQUEST_ID_PREFIX,
    ChannelsProtocolError,
    ChannelsRemoteError,
    ChannelsTimeoutError,
    ChannelsWorkerDisconnected,
    ChannelsWorkerNotReady,
    CloudMessage,
    RemoteResponse,
    WorkerCapability,
    WorkerCapabilities,
    decode_cloud_message,
    encode_cloud_message,
    redact_text,
)


@dataclass
class _WorkerSession:
    worker_id: str
    connection: ServerConnection
    capabilities: WorkerCapabilities | None = None
    heartbeat_received_at: float | None = None
    command_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChannelsHub:
    """Authenticated, single-worker-oriented WebSocket Hub for Channels calls."""

    def __init__(
        self,
        *,
        shared_secret: str,
        allowed_worker_ids: set[str] | None = None,
        heartbeat_max_age_seconds: float = 60.0,
    ) -> None:
        shared_secret = shared_secret.strip()
        if not shared_secret:
            raise ValueError("shared_secret is required")
        if heartbeat_max_age_seconds <= 0:
            raise ValueError("heartbeat_max_age_seconds must be positive")
        self._secret = shared_secret
        self._allowed_worker_ids = set(allowed_worker_ids or [])
        self._heartbeat_max_age_seconds = float(heartbeat_max_age_seconds)
        self._workers: dict[str, _WorkerSession] = {}
        self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}
        self._worker_changed = asyncio.Condition()
        self._server: Server | None = None

    @property
    def listening_port(self) -> int | None:
        if self._server is None or not self._server.sockets:
            return None
        return int(self._server.sockets[0].getsockname()[1])

    async def start(
        self,
        host: str,
        port: int,
        *,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if self._server is not None:
            raise RuntimeError("ChannelsHub is already running")
        self._server = await serve(
            self._handle_connection,
            host,
            port,
            ssl=ssl_context,
            max_size=MAX_MESSAGE_BYTES,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            compression=None,
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for worker_id in list(self._workers):
            await self._drop_worker(worker_id, "hub stopped")

    def worker_capabilities(self, worker_id: str) -> WorkerCapabilities | None:
        session = self._workers.get(worker_id)
        return session.capabilities if session else None

    async def wait_for_worker(
        self,
        worker_id: str,
        *,
        timeout: float,
        require_search_ready: bool = False,
        required_capability: WorkerCapability | None = None,
    ) -> WorkerCapabilities:
        capability = _resolve_required_capability(
            require_search_ready=require_search_ready,
            required_capability=required_capability,
        )

        async def _wait() -> WorkerCapabilities:
            async with self._worker_changed:
                while True:
                    session = self._workers.get(worker_id)
                    if session is not None and self._session_is_ready(session, capability):
                        assert session.capabilities is not None
                        return session.capabilities
                    await self._worker_changed.wait()

        try:
            return await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ChannelsTimeoutError(f"worker {worker_id} didn't become ready") from exc

    async def wait_for_worker_disconnect(self, worker_id: str, *, timeout: float) -> None:
        async def _wait() -> None:
            async with self._worker_changed:
                while worker_id in self._workers:
                    await self._worker_changed.wait()

        try:
            await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ChannelsTimeoutError(f"worker {worker_id} didn't disconnect") from exc

    async def call(
        self,
        worker_id: str,
        action: str,
        data: dict[str, Any],
        *,
        timeout: float = 30.0,
        require_search_ready: bool = False,
        required_capability: WorkerCapability | None = None,
    ) -> Any:
        capability = _resolve_required_capability(
            require_search_ready=require_search_ready,
            required_capability=required_capability,
        )
        session = self._workers.get(worker_id)
        if session is None:
            raise ChannelsWorkerDisconnected(f"worker {worker_id} is not connected")
        self._require_session_ready(session, capability)

        async with session.command_lock:
            if self._workers.get(worker_id) is not session:
                raise ChannelsWorkerDisconnected(f"worker {worker_id} reconnected before dispatch")
            self._require_session_ready(session, capability)
            request_id = f"{REQUEST_ID_PREFIX}{uuid.uuid4().hex}"
            loop = asyncio.get_running_loop()
            future: asyncio.Future[Any] = loop.create_future()
            self._pending[request_id] = (worker_id, future)
            message = CloudMessage(
                message_id=request_id,
                message_type="command",
                client_id=worker_id,
                payload={"action": action, "data": data},
                timestamp=int(time.time()),
            )
            try:
                await session.connection.send(encode_cloud_message(message))
                return await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise ChannelsTimeoutError(
                    f"worker {worker_id} timed out while running {action}"
                ) from exc
            except ConnectionClosed as exc:
                raise ChannelsWorkerDisconnected(f"worker {worker_id} disconnected") from exc
            finally:
                self._pending.pop(request_id, None)

    async def _handle_connection(self, connection: ServerConnection) -> None:
        request = connection.request
        headers = request.headers if request is not None else {}
        if request is None or request.path.split("?", 1)[0] != "/ws/client":
            await connection.close(code=1008, reason="unsupported websocket path")
            return
        worker_id = str(headers.get("X-Client-ID") or "").strip()
        supplied_secret = str(headers.get("X-Cloud-Secret") or "")
        if not worker_id or not hmac.compare_digest(supplied_secret, self._secret):
            await connection.close(code=1008, reason="unauthorized worker")
            return
        if self._allowed_worker_ids and worker_id not in self._allowed_worker_ids:
            await connection.close(code=1008, reason="worker is not allowlisted")
            return

        previous = self._workers.get(worker_id)
        if previous is not None:
            await previous.connection.close(code=1012, reason="worker reconnected")
            await self._fail_pending(worker_id, "worker reconnected")

        session = _WorkerSession(worker_id=worker_id, connection=connection)
        self._workers[worker_id] = session
        await self._notify_worker_changed()
        try:
            async for raw in connection:
                try:
                    message = decode_cloud_message(raw)
                except ChannelsProtocolError:
                    await connection.close(code=1007, reason="invalid message")
                    return
                if message.client_id != worker_id:
                    await connection.close(code=1008, reason="client id mismatch")
                    return
                try:
                    await self._handle_message(session, message)
                except ChannelsProtocolError:
                    await connection.close(code=1007, reason="invalid message")
                    return
        except ConnectionClosed:
            pass
        finally:
            if self._workers.get(worker_id) is session:
                self._workers.pop(worker_id, None)
                await self._fail_pending(worker_id, "worker disconnected")
                await self._notify_worker_changed()

    async def _handle_message(self, session: _WorkerSession, message: CloudMessage) -> None:
        if message.message_type == "heartbeat":
            session.capabilities = WorkerCapabilities.from_heartbeat(message)
            session.heartbeat_received_at = time.monotonic()
            ack = CloudMessage(
                message_id=f"ack-{message.message_id}",
                message_type="heartbeat_ack",
                client_id=session.worker_id,
                payload={},
                timestamp=int(time.time()),
            )
            await session.connection.send(encode_cloud_message(ack))
            await self._notify_worker_changed()
            return
        if message.message_type == "response":
            response = RemoteResponse.from_message(message)
            pending = self._pending.get(response.request_id)
            if pending is None or pending[0] != session.worker_id:
                return
            future = pending[1]
            if future.done():
                return
            if response.success:
                future.set_result(response.data)
            else:
                future.set_exception(
                    ChannelsRemoteError(
                        redact_text(response.error) or "remote worker returned an error"
                    )
                )
            return
        if message.message_type == "sync_data":
            return
        raise ChannelsProtocolError(f"unsupported worker message type: {message.message_type}")

    def _session_is_ready(
        self,
        session: _WorkerSession,
        capability: WorkerCapability | None,
    ) -> bool:
        capabilities = session.capabilities
        if capabilities is None or session.heartbeat_received_at is None:
            return False
        if time.monotonic() - session.heartbeat_received_at > self._heartbeat_max_age_seconds:
            return False
        if capability is None:
            return True
        if not capabilities.api_ready:
            return False
        return bool(getattr(capabilities, f"supports_{capability}"))

    def _require_session_ready(
        self,
        session: _WorkerSession,
        capability: WorkerCapability | None,
    ) -> None:
        if self._session_is_ready(session, capability):
            return
        command_type = capability or "generic"
        raise ChannelsWorkerNotReady(
            f"worker {session.worker_id} cannot serve {command_type} commands with a fresh heartbeat"
        )

    async def _drop_worker(self, worker_id: str, reason: str) -> None:
        session = self._workers.pop(worker_id, None)
        if session is not None:
            await session.connection.close(code=1001, reason=reason)
        await self._fail_pending(worker_id, reason)
        await self._notify_worker_changed()

    async def _fail_pending(self, worker_id: str, reason: str) -> None:
        for request_id, (pending_worker_id, future) in list(self._pending.items()):
            if pending_worker_id != worker_id:
                continue
            if not future.done():
                future.set_exception(
                    ChannelsWorkerDisconnected(f"worker {worker_id} {reason}")
                )
            self._pending.pop(request_id, None)

    async def _notify_worker_changed(self) -> None:
        async with self._worker_changed:
            self._worker_changed.notify_all()


def _resolve_required_capability(
    *,
    require_search_ready: bool,
    required_capability: WorkerCapability | None,
) -> WorkerCapability | None:
    if require_search_ready and required_capability not in (None, "search"):
        raise ValueError("require_search_ready conflicts with required_capability")
    if required_capability not in (None, "search", "feed", "profile"):
        raise ValueError(f"unsupported worker capability: {required_capability}")
    return "search" if require_search_ready else required_capability
