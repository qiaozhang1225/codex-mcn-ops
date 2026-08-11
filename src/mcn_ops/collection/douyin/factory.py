from __future__ import annotations

import os
from pathlib import Path

from ..transcription.aliyun import AliyunTranscriptionConfig, AliyunTranscriptionProvider
from ..transcription.service import DouyinTranscriptionService
from ..transcription.sqlite_cache import SqliteTranscriptionCache
from .browser_session import BrowserSessionConfig, BrowserSessionDouyinClient
from .contracts import DouyinProvider, TranscriptionProvider
from .direct import DirectDouyinClient, DirectDouyinConfig
from .errors import ProviderConfigError


class TranscribingDouyinProvider:
    def __init__(
        self,
        *,
        data_provider: DouyinProvider,
        transcription_provider: TranscriptionProvider | None = None,
    ) -> None:
        self.data_provider = data_provider
        self.transcription_provider = transcription_provider
        self.provider_name = data_provider.provider_name
        self.data_provider_name = data_provider.provider_name
        self.transcription_provider_name = (
            transcription_provider.provider_name if transcription_provider is not None else "none"
        )
        self.browser_pagination = bool(getattr(data_provider, "browser_pagination", False))

    def call(self, method_key, params=None, body=None, use_cache=True):
        if method_key not in {"video_to_text_v2", "douyin_extract_video_text"}:
            return self.data_provider.call(method_key, params=params, body=body, use_cache=use_cache)
        if self.transcription_provider is None:
            raise ProviderConfigError(
                "transcription provider is not configured; select aliyun explicitly"
            )
        supplied = {**(params or {}), **(body or {})}
        source = str(supplied.get("url") or "").strip()
        if not source:
            raise ProviderConfigError("video_to_text_v2 requires url")
        source_package = supplied.get("source_package")
        if source_package is not None and not isinstance(source_package, dict):
            raise ProviderConfigError("source_package must be an object")
        return self.transcription_provider.transcribe(
            source,
            source_package=source_package,
            use_cache=use_cache,
        )


def load_local_env(path: str | Path = ".env.local") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


def build_data_provider(
    name: str,
    *,
    allow_paid_fallback: bool = False,
) -> DouyinProvider:
    load_local_env()
    if allow_paid_fallback:
        raise ProviderConfigError("paid provider fallback has been removed")
    provider_name = name.strip().lower()
    if provider_name == "direct":
        return _build_direct_provider()
    raise ProviderConfigError(f"unsupported Douyin provider: {name}")


def build_transcription_provider(
    name: str,
    *,
    data_provider: DouyinProvider,
) -> TranscriptionProvider | None:
    load_local_env()
    provider_name = name.strip().lower()
    if provider_name in {"", "none", "provider"}:
        return None
    if provider_name != "aliyun":
        raise ProviderConfigError(f"unsupported transcription provider: {name}")
    cache_path = Path(os.environ.get("MCN_ASR_CACHE_PATH", "data/transcription-cache.sqlite"))
    aliyun = AliyunTranscriptionProvider(
        AliyunTranscriptionConfig.from_env(),
        cache=SqliteTranscriptionCache(cache_path),
    )
    return DouyinTranscriptionService(data_provider=data_provider, transcription_provider=aliyun)


def build_collection_provider(
    data_provider_name: str,
    *,
    transcription_provider_name: str = "aliyun",
    allow_paid_fallback: bool = False,
) -> DouyinProvider:
    data_provider = build_data_provider(
        data_provider_name,
        allow_paid_fallback=allow_paid_fallback,
    )
    transcription_provider = build_transcription_provider(
        transcription_provider_name,
        data_provider=data_provider,
    )
    return TranscribingDouyinProvider(
        data_provider=data_provider,
        transcription_provider=transcription_provider,
    )


def _build_direct_provider() -> DouyinProvider:
    timeout = _float_env("DOUYIN_TIMEOUT_SECONDS", 30.0)
    empty_page_retries = _int_env("DOUYIN_EMPTY_PAGE_RETRIES", 1)
    direct = DirectDouyinClient(
        DirectDouyinConfig(
            cookie=os.environ.get("DOUYIN_COOKIE", "").strip() or None,
            timeout_seconds=timeout,
            empty_page_retries=empty_page_retries,
        )
    )
    mode = os.environ.get("DOUYIN_DIRECT_MODE", "browser").strip().lower()
    if mode == "http":
        return direct
    if mode != "browser":
        raise ProviderConfigError("DOUYIN_DIRECT_MODE must be browser or http")
    return BrowserSessionDouyinClient(
        direct,
        BrowserSessionConfig(
            executable=os.environ.get("DOUYIN_BROWSER_EXECUTABLE", "ego-browser").strip(),
            task_space=os.environ.get(
                "DOUYIN_BROWSER_TASK_SPACE",
                "codex-mcn-ops douyin browser provider v1",
            ).strip(),
            wait_seconds=_float_env("DOUYIN_BROWSER_WAIT_SECONDS", 8.0),
            timeout_seconds=_float_env("DOUYIN_BROWSER_TIMEOUT_SECONDS", 45.0),
            empty_result_retries=_int_env("DOUYIN_BROWSER_EMPTY_RESULT_RETRIES", 1),
            max_page_limit=_int_env("DOUYIN_BROWSER_MAX_PAGE_LIMIT", 100),
            scroll_wait_seconds=_float_env("DOUYIN_BROWSER_SCROLL_WAIT_SECONDS", 1.5),
        ),
    )


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ProviderConfigError(f"{key} must be numeric") from exc


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError as exc:
        raise ProviderConfigError(f"{key} must be an integer") from exc
