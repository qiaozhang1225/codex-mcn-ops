from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..douyin.factory import load_local_env
from ..tools import ToolRegistry
from ..transcription.aliyun import AliyunTranscriptionConfig, AliyunTranscriptionProvider
from ..transcription.sqlite_cache import SqliteTranscriptionCache
from .provider import ChannelsRemoteConfig, ChannelsRemoteProvider
from .registry import build_channels_registry

if TYPE_CHECKING:
    from .provider import ChannelsSessionGuard


def build_channels_collection_registry(
    *,
    transcription_provider_name: str = "aliyun",
    session_guard: "ChannelsSessionGuard | None" = None,
) -> ToolRegistry:
    load_local_env()
    if transcription_provider_name.strip().lower() != "aliyun":
        raise ValueError("WeChat Channels formal collection requires aliyun transcription")
    remote_config = ChannelsRemoteConfig.from_env(
        worker_id_override=session_guard.worker_id if session_guard is not None else None,
        shared_secret_override=(
            session_guard.shared_secret if session_guard is not None else None
        ),
    )
    provider = ChannelsRemoteProvider(remote_config, session_guard=session_guard)
    cache_path = Path(os.environ.get("MCN_ASR_CACHE_PATH", "data/transcription-cache.sqlite"))
    transcriber = AliyunTranscriptionProvider(
        AliyunTranscriptionConfig.from_env(),
        cache=SqliteTranscriptionCache(cache_path),
    )
    return build_channels_registry(
        provider,
        transcription_provider=transcriber,
        download_limit_bytes=_env_int("CHANNELS_MEDIA_MAX_BYTES", 512 * 1024 * 1024),
        download_timeout_seconds=_env_float("CHANNELS_MEDIA_TIMEOUT_SECONDS", 180.0),
    )


def _env_int(key: str, default: int) -> int:
    try:
        value = int(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{key} must be positive")
    return value


def _env_float(key: str, default: float) -> float:
    try:
        value = float(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be numeric") from exc
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value
