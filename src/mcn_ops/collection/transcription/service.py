from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from ..douyin.contracts import DouyinProvider, ProviderResult, TranscriptionProvider
from ..douyin.errors import ProviderResponseError, TranscriptionInputError


class DouyinTranscriptionService:
    """Resolve authoritative Douyin metadata before transcribing its audio."""

    provider_name = "douyin-transcription"

    def __init__(
        self,
        *,
        data_provider: DouyinProvider,
        transcription_provider: TranscriptionProvider,
    ) -> None:
        self.data_provider = data_provider
        self.transcription_provider = transcription_provider

    def transcribe(
        self,
        source: str,
        *,
        source_package: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        source = str(source or "").strip()
        if not source:
            raise TranscriptionInputError("transcription source is required")
        package = dict(source_package or {})
        if not package and not Path(source).expanduser().is_file():
            detail = self.data_provider.call("detail_v4", body={"url": source}, use_cache=use_cache)
            normalized = detail.get("normalized") if isinstance(detail.get("normalized"), dict) else {}
            package = dict(normalized.get("source_package") or {})
        media_source = str(package.get("audio_url") or package.get("video_url") or source).strip()
        if media_source == source and _is_douyin_url(source):
            raise ProviderResponseError("Douyin detail returned no transcribable audio or video URL")
        result = dict(
            self.transcription_provider.transcribe(
                media_source,
                source_package=package,
                use_cache=use_cache,
            )
        )
        normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
        transcript_package = normalized.get("source_package") if isinstance(normalized.get("source_package"), dict) else {}
        merged = {
            key: value
            for key, value in transcript_package.items()
            if value not in (None, "", [], {})
        }
        merged.update(package)
        transcript_text = str(normalized.get("text") or transcript_package.get("transcript_text") or "").strip()
        if transcript_text:
            merged["transcript_text"] = transcript_text
        normalized["source_package"] = merged
        result["normalized"] = normalized
        result["method_key"] = "video_to_text_v2"
        return result  # type: ignore[return-value]


def _is_douyin_url(value: str) -> bool:
    try:
        hostname = (urllib.parse.urlsplit(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return hostname == "douyin.com" or hostname.endswith(".douyin.com")
