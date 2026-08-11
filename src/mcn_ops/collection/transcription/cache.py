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
        self._items[key] = copy.deepcopy(result)
