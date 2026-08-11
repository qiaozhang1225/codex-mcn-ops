from __future__ import annotations

import base64
import copy
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from ..douyin.contracts import ProviderResult, build_provider_result
from ..douyin.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    TranscriptionInputError,
)
from .cache import MemoryTranscriptionCache, transcription_cache_key
from .media import PreparedMedia, normalize_prepared_media, prepare_media, validate_public_https_url


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] | None = None


HttpTransport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], HttpResponse]
MediaPreparer = Callable[[str], PreparedMedia]
MediaNormalizer = Callable[[PreparedMedia], PreparedMedia]
UrlUploader = Callable[[Path], str]
UploadedUrlCleanup = Callable[[str], None]


class ResultCache(Protocol):
    def get(self, key: str) -> ProviderResult | None: ...

    def put(self, key: str, result: ProviderResult) -> None: ...


@dataclass
class AliyunTranscriptionConfig:
    api_key: str
    workspace_id: str
    region: str = "cn-beijing"
    short_model: str = "qwen3-asr-flash"
    long_model: str = "qwen3-asr-flash-filetrans"
    language: str | None = "zh"
    enable_itn: bool = False
    enable_words: bool = False
    timeout_seconds: float = 30.0
    poll_timeout_seconds: float = 600.0
    poll_interval_seconds: float = 2.0
    short_max_seconds: float = 300.0
    short_max_bytes: int = 10 * 1024 * 1024
    unit_price_cny_per_second: float = 0.00022
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> "AliyunTranscriptionConfig":
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        workspace_id = os.environ.get("DASHSCOPE_WORKSPACE_ID", "").strip()
        if not api_key or not workspace_id:
            raise ProviderConfigError("DASHSCOPE_API_KEY and DASHSCOPE_WORKSPACE_ID are required")
        return cls(
            api_key=api_key,
            workspace_id=workspace_id,
            region=os.environ.get("DASHSCOPE_REGION", "cn-beijing").strip() or "cn-beijing",
            language=os.environ.get("MCN_ASR_LANGUAGE", "zh").strip() or None,
            enable_itn=os.environ.get("MCN_ASR_ENABLE_ITN", "false").lower() in {"1", "true", "yes"},
            short_model=os.environ.get("MCN_ASR_SHORT_MODEL", "qwen3-asr-flash").strip(),
            long_model=os.environ.get("MCN_ASR_LONG_MODEL", "qwen3-asr-flash-filetrans").strip(),
        )

    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        return f"https://{self.workspace_id}.{self.region}.maas.aliyuncs.com"

    def validate(self) -> None:
        if not self.api_key.strip() or not self.workspace_id.strip():
            raise ProviderConfigError("Aliyun API key and workspace ID are required")
        if self.short_max_seconds <= 0 or self.short_max_bytes <= 0:
            raise ProviderConfigError("short-audio limits must be positive")
        if self.poll_timeout_seconds <= 0 or self.poll_interval_seconds < 0:
            raise ProviderConfigError("polling configuration is invalid")


class AliyunTranscriptionProvider:
    provider_name = "aliyun-qwen-asr"

    def __init__(
        self,
        config: AliyunTranscriptionConfig,
        *,
        transport: HttpTransport | None = None,
        media_preparer: MediaPreparer | None = None,
        media_normalizer: MediaNormalizer | None = None,
        cache: ResultCache | None = None,
        url_uploader: UrlUploader | None = None,
        uploaded_url_cleanup: UploadedUrlCleanup | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        config.validate()
        self.config = config
        self.transport = transport or urllib_transport
        self.media_preparer = media_preparer or prepare_media
        self.media_normalizer = media_normalizer or normalize_prepared_media
        self.cache = cache or MemoryTranscriptionCache()
        self.url_uploader = url_uploader
        self.uploaded_url_cleanup = uploaded_url_cleanup
        self.sleep = sleep
        self.monotonic = monotonic

    def transcribe(
        self,
        source: str,
        *,
        source_package: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        package = dict(source_package or {})
        media_source = str(package.get("audio_url") or source or "").strip()
        if not media_source:
            raise TranscriptionInputError("transcription source is required")

        original_media = self.media_preparer(media_source)
        prepared = original_media
        uploaded_url: str | None = None
        try:
            prepared = self.media_normalizer(original_media)
            is_short = (
                prepared.duration_seconds <= self.config.short_max_seconds
                and prepared.size_bytes <= self.config.short_max_bytes
            )
            model = self.config.short_model if is_short else self.config.long_model
            options = {
                "enable_itn": self.config.enable_itn,
                "enable_words": self.config.enable_words if not is_short else False,
                "language": self.config.language,
            }
            cache_key = transcription_cache_key(
                audio_sha256=prepared.sha256,
                provider=self.provider_name,
                model=model,
                options=options,
            )
            if use_cache:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    result = copy.deepcopy(cached)
                    result["cache_hit"] = True
                    return result

            if is_short:
                result = self._transcribe_short(prepared, package)
            else:
                pending_job = self._pending_job(cache_key) if use_cache else None
                persisted_upload = str((pending_job or {}).get("uploaded_url") or "") or None
                if pending_job:
                    long_url = persisted_upload or media_source
                    uploaded_url = persisted_upload
                else:
                    long_url, uploaded_url = self._resolve_long_audio_url(media_source, prepared)
                result = self._transcribe_long(
                    long_url,
                    prepared,
                    package,
                    cache_key=cache_key if use_cache else "",
                    task_id=str((pending_job or {}).get("task_id") or ""),
                    uploaded_url=uploaded_url,
                )
            if use_cache:
                self.cache.put(cache_key, result)
                if not is_short:
                    self._clear_pending_task(cache_key)
            if not is_short and uploaded_url:
                self._cleanup_uploaded_url(uploaded_url)
            return result
        finally:
            prepared.cleanup()
            if original_media.temporary_directory != prepared.temporary_directory:
                original_media.cleanup()

    def _transcribe_short(self, media: PreparedMedia, source_package: dict[str, Any]) -> ProviderResult:
        encoded = base64.b64encode(media.read_bytes(max_bytes=self.config.short_max_bytes)).decode("ascii")
        data_uri = f"data:{media.mime_type};base64,{encoded}"
        asr_options: dict[str, Any] = {"enable_itn": self.config.enable_itn}
        if self.config.language:
            asr_options["language"] = self.config.language
        payload = {
            "model": self.config.short_model,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
                }
            ],
            "stream": False,
            "asr_options": asr_options,
        }
        endpoint = f"{self.config.resolved_base_url()}/compatible-mode/v1/chat/completions"
        response = self._request_json("POST", endpoint, payload=payload, include_auth=True)
        try:
            message = response["choices"][0]["message"]
            text = str(message["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError("Aliyun short-ASR response has no transcript") from exc
        if not text:
            raise ProviderResponseError("Aliyun short-ASR returned empty text")
        annotations = message.get("annotations") if isinstance(message, dict) else []
        audio_info = annotations[0] if isinstance(annotations, list) and annotations else {}
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        seconds = _number(usage.get("seconds"), media.duration_seconds)
        return self._result(
            text=text,
            model=self.config.short_model,
            package=source_package,
            language=str(audio_info.get("language") or self.config.language or ""),
            segments=[],
            seconds=seconds,
            endpoint=endpoint,
            raw={"request_id": response.get("id"), "audio_info": scrub_sensitive(audio_info)},
        )

    def _resolve_long_audio_url(self, source: str, media: PreparedMedia) -> tuple[str, str | None]:
        parsed = urllib.parse.urlsplit(source)
        if parsed.scheme and media.source_url:
            validate_public_https_url(source)
            return source, None
        if self.url_uploader is None:
            raise TranscriptionInputError("long local audio requires an HTTPS URL uploader")
        uploaded_url = str(self.url_uploader(media.path))
        validate_public_https_url(uploaded_url)
        return uploaded_url, uploaded_url

    def _transcribe_long(
        self,
        file_url: str,
        media: PreparedMedia,
        source_package: dict[str, Any],
        *,
        cache_key: str,
        task_id: str = "",
        uploaded_url: str | None = None,
    ) -> ProviderResult:
        parameters: dict[str, Any] = {
            "channel_id": [0],
            "enable_itn": self.config.enable_itn,
            "enable_words": self.config.enable_words,
        }
        if self.config.language:
            parameters["language"] = self.config.language
        payload = {
            "model": self.config.long_model,
            "input": {"file_url": file_url},
            "parameters": parameters,
        }
        submit_endpoint = f"{self.config.resolved_base_url()}/api/v1/services/audio/asr/transcription"
        submit: dict[str, Any] = {}
        if not task_id:
            submit = self._request_json(
                "POST",
                submit_endpoint,
                payload=payload,
                include_auth=True,
                async_header=True,
            )
            output = submit.get("output") if isinstance(submit.get("output"), dict) else {}
            task_id = str(output.get("task_id") or "").strip()
            if not task_id:
                raise ProviderResponseError("Aliyun long-ASR submission returned no task_id")
            self._save_pending_task(cache_key, task_id, uploaded_url=uploaded_url)

        task_endpoint = f"{self.config.resolved_base_url()}/api/v1/tasks/{urllib.parse.quote(task_id, safe='')}"
        deadline = self.monotonic() + self.config.poll_timeout_seconds
        final: dict[str, Any] | None = None
        while self.monotonic() < deadline:
            if self.config.poll_interval_seconds:
                self.sleep(self.config.poll_interval_seconds)
            polled = self._request_json("GET", task_endpoint, include_auth=True, async_header=True)
            polled_output = polled.get("output") if isinstance(polled.get("output"), dict) else {}
            status = str(polled_output.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                final = polled
                break
            if status in {"FAILED", "UNKNOWN"}:
                detail = str(polled_output.get("message") or polled.get("message") or status)
                self._clear_pending_task(cache_key)
                if uploaded_url:
                    self._cleanup_uploaded_url(uploaded_url)
                raise ProviderResponseError(f"Aliyun long-ASR task {status.lower()}", detail=scrub_text(detail))
            if status not in {"PENDING", "RUNNING", ""}:
                raise ProviderResponseError(f"Aliyun long-ASR returned unexpected task status: {status}")
        if final is None:
            raise ProviderUnavailableError("Aliyun long-ASR polling timed out", detail=f"task_id={task_id}")

        final_output = final.get("output") if isinstance(final.get("output"), dict) else {}
        result_info = final_output.get("result") if isinstance(final_output.get("result"), dict) else {}
        transcription_url = str(result_info.get("transcription_url") or "")
        if not transcription_url:
            raise ProviderResponseError("Aliyun long-ASR task returned no transcription URL")
        transcription = self._request_json("GET", transcription_url, include_auth=False)
        text, segments, language = normalize_long_transcription(transcription)
        usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
        seconds = _number(usage.get("seconds"), media.duration_seconds)
        result = self._result(
            text=text,
            model=self.config.long_model,
            package=source_package,
            language=language or self.config.language or "",
            segments=segments,
            seconds=seconds,
            endpoint=submit_endpoint,
            raw={
                "request_id": final.get("request_id") or submit.get("request_id"),
                "task_id": task_id,
                "task_status": "SUCCEEDED",
            },
        )
        return result

    def _pending_job(self, cache_key: str) -> dict[str, str] | None:
        if not cache_key:
            return None
        getter = getattr(self.cache, "get_job", None)
        if not callable(getter):
            return None
        job = getter(cache_key)
        return job if isinstance(job, dict) else None

    def _save_pending_task(self, cache_key: str, task_id: str, *, uploaded_url: str | None = None) -> None:
        if not cache_key:
            return
        writer = getattr(self.cache, "put_job", None)
        if callable(writer):
            writer(cache_key, task_id, status="submitted", uploaded_url=uploaded_url)

    def _clear_pending_task(self, cache_key: str) -> None:
        if not cache_key:
            return
        deleter = getattr(self.cache, "delete_job", None)
        if callable(deleter):
            deleter(cache_key)

    def _cleanup_uploaded_url(self, uploaded_url: str) -> None:
        if not self.uploaded_url_cleanup:
            return
        try:
            self.uploaded_url_cleanup(uploaded_url)
        except Exception:
            pass

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        include_auth: bool,
        async_header: bool = False,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if include_auth:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if async_header:
            headers["X-DashScope-Async"] = "enable"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        try:
            response = self.transport(method, url, headers, body, self.config.timeout_seconds)
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderUnavailableError("Aliyun ASR request timed out") from exc
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Aliyun ASR request failed", detail=scrub_text(str(exc))) from exc

        try:
            decoded = _decode_json(response.body)
        except ProviderResponseError:
            if response.status < 400:
                raise
            decoded = {"message": response.body[:500].decode("utf-8", errors="replace")}
        if response.status in {401, 403}:
            raise ProviderAuthError("Aliyun ASR authentication failed", detail=_safe_error(decoded))
        if response.status == 429:
            raise ProviderRateLimitError("Aliyun ASR rate limit exceeded", detail=_safe_error(decoded))
        if response.status in {408, 425} or response.status >= 500:
            raise ProviderUnavailableError(
                f"Aliyun ASR is temporarily unavailable (HTTP {response.status})",
                detail=_safe_error(decoded),
            )
        if response.status >= 400:
            raise ProviderResponseError(
                f"Aliyun ASR rejected the request (HTTP {response.status})",
                detail=_safe_error(decoded),
            )
        return decoded

    def _result(
        self,
        *,
        text: str,
        model: str,
        package: dict[str, Any],
        language: str,
        segments: list[dict[str, Any]],
        seconds: float,
        endpoint: str,
        raw: dict[str, Any],
    ) -> ProviderResult:
        source_package = dict(package)
        source_package["transcript_text"] = text
        estimated_cost = round(seconds * self.config.unit_price_cny_per_second, 8)
        return build_provider_result(
            provider=self.provider_name,
            method_key="douyin_extract_video_text",
            endpoint=endpoint,
            normalized={
                "text": text,
                "language": language,
                "segments": segments,
                "source_package": source_package,
                "model": model,
            },
            raw=scrub_sensitive(raw),
            usage={
                "audio_seconds": seconds,
                "billable_seconds": seconds,
                "unit_price_cny_per_second": self.config.unit_price_cny_per_second,
                "estimated_cost_cny": estimated_cost,
                "model": model,
            },
        )


def urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_seconds: float,
) -> HttpResponse:
    request = urllib.request.Request(url=url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(status=response.status, body=response.read(), headers=dict(response.headers))
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=exc.code, body=exc.read(), headers=dict(exc.headers or {}))
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise ProviderUnavailableError("Aliyun ASR network request failed", detail=scrub_text(str(exc))) from exc


def normalize_long_transcription(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    transcripts = payload.get("transcripts")
    if not isinstance(transcripts, list):
        raise ProviderResponseError("Aliyun transcription result has no transcripts")
    transcript_texts: list[str] = []
    segments: list[dict[str, Any]] = []
    language = ""
    for transcript in transcripts:
        if not isinstance(transcript, dict):
            continue
        direct_text = str(transcript.get("text") or "").strip()
        sentences = transcript.get("sentences")
        sentence_texts: list[str] = []
        if isinstance(sentences, list):
            for sentence in sentences:
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                sentence_texts.append(text)
                language = language or str(sentence.get("language") or "")
                segment: dict[str, Any] = {"text": text}
                if sentence.get("begin_time") is not None:
                    segment["begin_time_ms"] = sentence["begin_time"]
                if sentence.get("end_time") is not None:
                    segment["end_time_ms"] = sentence["end_time"]
                if sentence.get("emotion") is not None:
                    segment["emotion"] = sentence["emotion"]
                segments.append(segment)
        transcript_texts.append(direct_text or "".join(sentence_texts))
    text = "".join(part for part in transcript_texts if part).strip()
    if not text:
        raise ProviderResponseError("Aliyun transcription result contains no text")
    return text, segments, language


def scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ("api_key", "apikey", "authorization", "secret", "cookie")):
                scrubbed[key] = "<redacted>"
            elif "url" in lowered and isinstance(item, str):
                scrubbed[key] = scrub_url(item)
            else:
                scrubbed[key] = scrub_sensitive(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_sensitive(item) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def scrub_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme:
        return scrub_text(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def scrub_text(text: str) -> str:
    text = re.sub(r"(?i)(Bearer\s+)[^\s]+", r"\1<redacted>", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "<redacted>", text)
    return text


def _decode_json(body: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderResponseError("Aliyun ASR response is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ProviderResponseError("Aliyun ASR response JSON must be an object")
    return decoded


def _safe_error(payload: dict[str, Any]) -> str:
    message = payload.get("message") or payload.get("error") or payload.get("code") or "request failed"
    if isinstance(message, dict):
        message = message.get("message") or message.get("code") or "request failed"
    return scrub_text(str(message))[:500]


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
