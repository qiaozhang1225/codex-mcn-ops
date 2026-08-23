from __future__ import annotations

import gzip
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Literal


PROTOCOL_VERSION = "channels-lan-v1"
REQUEST_ID_PREFIX = "clv1-"
MAX_MESSAGE_BYTES = 10 * 1024 * 1024
WorkerCapability = Literal["search", "feed", "profile"]


class ChannelsProtocolError(ValueError):
    """The peer sent a message that doesn't satisfy the LAN contract."""


class ChannelsWorkerDisconnected(RuntimeError):
    """The requested worker isn't connected or disconnected mid-call."""


class ChannelsWorkerNotReady(RuntimeError):
    """The worker is connected but its WeChat page cannot serve the command."""


class ChannelsTimeoutError(TimeoutError):
    """The remote worker didn't answer before the command deadline."""


class ChannelsRemoteError(RuntimeError):
    """The Windows worker rejected or failed a command."""


@dataclass(frozen=True)
class CloudMessage:
    message_id: str
    message_type: str
    client_id: str
    payload: Any
    timestamp: int

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.message_id,
            "type": self.message_type,
            "client_id": self.client_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class WorkerCapabilities:
    worker_id: str
    hostname: str = ""
    version: str = ""
    status: str = "unknown"
    page_path: str = ""
    api_ready: bool = False
    supports_search: bool = False
    supports_feed: bool = False
    supports_profile: bool = False
    methods: dict[str, bool] = field(default_factory=dict)
    heartbeat_timestamp: int = 0

    @classmethod
    def from_heartbeat(cls, message: CloudMessage) -> "WorkerCapabilities":
        if message.message_type != "heartbeat":
            raise ChannelsProtocolError("worker capabilities require a heartbeat message")
        payload = _object(message.payload, "heartbeat payload")
        methods = payload.get("methods") if isinstance(payload.get("methods"), dict) else {}
        return cls(
            worker_id=message.client_id,
            hostname=str(payload.get("hostname") or ""),
            version=str(payload.get("version") or ""),
            status=str(payload.get("status") or "unknown"),
            page_path=str(payload.get("page_path") or ""),
            api_ready=bool(payload.get("api_ready")),
            supports_search=bool(payload.get("supports_search")),
            supports_feed=bool(payload.get("supports_feed")),
            supports_profile=bool(payload.get("supports_profile")),
            methods={str(key): bool(value) for key, value in methods.items()},
            heartbeat_timestamp=message.timestamp,
        )


@dataclass(frozen=True)
class RemoteResponse:
    request_id: str
    success: bool
    data: Any
    error: str = ""

    @classmethod
    def from_message(cls, message: CloudMessage) -> "RemoteResponse":
        if message.message_type != "response":
            raise ChannelsProtocolError("remote response requires a response message")
        payload = _object(message.payload, "response payload")
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            raise ChannelsProtocolError("response payload has no request_id")
        return cls(
            request_id=request_id,
            success=bool(payload.get("success")),
            data=payload.get("data"),
            error=str(payload.get("error") or ""),
        )


def decode_cloud_message(raw: str | bytes) -> CloudMessage:
    if isinstance(raw, bytes):
        if len(raw) > MAX_MESSAGE_BYTES:
            raise ChannelsProtocolError("binary message exceeds the maximum size")
        try:
            raw = gzip.decompress(raw).decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ChannelsProtocolError("binary message is not gzip-compressed JSON") from exc
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ChannelsProtocolError("message exceeds the maximum size")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChannelsProtocolError("message is not valid JSON") from exc
    body = _object(body, "message")
    message_id = str(body.get("id") or "").strip()
    message_type = str(body.get("type") or "").strip()
    client_id = str(body.get("client_id") or "").strip()
    if not message_id or not message_type or not client_id:
        raise ChannelsProtocolError("message requires id, type, and client_id")
    try:
        timestamp = int(body.get("timestamp") or 0)
    except (TypeError, ValueError) as exc:
        raise ChannelsProtocolError("message timestamp must be an integer") from exc
    return CloudMessage(
        message_id=message_id,
        message_type=message_type,
        client_id=client_id,
        payload=body.get("payload"),
        timestamp=timestamp,
    )


def encode_cloud_message(message: CloudMessage) -> str:
    return json.dumps(message.to_wire(), ensure_ascii=False, separators=(",", ":"))


def redact_payload(value: Any, *, parent_key: str = "") -> Any:
    """Return a log-safe copy without transport or signed-media credentials."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower().replace("_", "")
            if lowered in {
                "authorization",
                "bypass",
                "clientreportbuff",
                "cookie",
                "cloudsecret",
                "decodekey",
                "decryptkey",
                "exportkey",
                "passticket",
                "secretedata",
                "sessionbuffer",
                "urltoken",
            }:
                redacted[key_text] = "<redacted>"
                continue
            redacted[key_text] = redact_payload(item, parent_key=key_text)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, str) and _looks_like_url(value):
        return _redact_url(value)
    return value


def redact_text(value: str) -> str:
    """Redact signed URLs and named credentials embedded in error text."""

    value = re.sub(
        r"(?i)\b(decodeKey|decryptKey|urlToken|cookie|authorization|pass_ticket|exportkey|sessionBuffer)\s*[:=]\s*([^\s,;&]+)",
        lambda match: f"{match.group(1)}=<redacted>",
        value,
    )
    return re.sub(r"https?://[^\s\"'<>]+", lambda match: _redact_url(match.group(0)), value)


def _redact_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return value
    if not parsed.query:
        return value
    query = []
    for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if any(
            token in lowered
            for token in ("token", "sign", "key", "auth", "cookie", "ticket", "session", "secret")
        ):
            query.append((key, "<redacted>"))
        else:
            query.append((key, item))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChannelsProtocolError(f"{label} must be an object")
    return value
