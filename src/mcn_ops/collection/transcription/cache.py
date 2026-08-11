from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from ..douyin.contracts import ProviderResult


def transcription_cache_key(
    *,
    audio_sha256: str,
    provider: str,
    model: str,
    options: dict[str, Any] | None = None,
) -> str:
    """Build a provider-aware cache key from normalized audio content."""
    payload = {
        "audio_sha256": audio_sha256.strip().lower(),
        "contract": "transcription:v1",
        "model": model.strip(),
        "options": options or {},
        "provider": provider.strip().lower(),
    }
    if not payload["audio_sha256"] or not payload["provider"] or not payload["model"]:
        raise ValueError("audio_sha256, provider, and model are required")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class MemoryTranscriptionCache:
    """Small injectable cache; persistent storage can implement the same get/put API."""

    def __init__(self) -> None:
        self._items: dict[str, ProviderResult] = {}

    def get(self, key: str) -> ProviderResult | None:
        item = self._items.get(key)
        return copy.deepcopy(item) if item is not None else None

    def put(self, key: str, result: ProviderResult) -> None:
        self._items[key] = cache_safe_provider_result(result)


_SECRET_KEY_MARKERS = (
    "a_bogus",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "secret",
)
_EPHEMERAL_MEDIA_KEYS = {
    "audio_url",
    "cover_url",
    "file_url",
    "media_url",
    "transcription_url",
    "uploaded_url",
    "video_url",
}


def cache_safe_provider_result(result: ProviderResult) -> ProviderResult:
    """Remove credentials and expiring media URLs before any cache persists them."""
    return _cache_safe_value(copy.deepcopy(result))


def _cache_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _EPHEMERAL_MEDIA_KEYS:
                continue
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                continue
            output[key] = _cache_safe_value(item)
        return output
    if isinstance(value, list):
        return [_cache_safe_value(item) for item in value]
    return value
