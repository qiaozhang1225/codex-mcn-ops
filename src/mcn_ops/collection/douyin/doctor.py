from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .contracts import DouyinProvider, TranscriptionProvider


DoctorProbe = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    probe: DoctorProbe


def run_doctor(
    provider: DouyinProvider,
    *,
    transcription_provider: TranscriptionProvider | None = None,
    transcription_required: bool = True,
    checks: Iterable[DoctorCheck] = (),
) -> dict[str, Any]:
    """Run injected, non-secret diagnostics without requiring network access."""

    results: list[dict[str, Any]] = [
        _status("data_provider", True, "configured", provider=provider.provider_name)
    ]
    if transcription_provider is None:
        results.append(
            _status(
                "transcription_provider",
                not transcription_required,
                "not_configured" if transcription_required else "disabled",
            )
        )
    else:
        results.append(
            _status(
                "transcription_provider",
                True,
                "configured",
                provider=transcription_provider.provider_name,
            )
        )

    for check in checks:
        try:
            payload = _sanitize(dict(check.probe()))
            ok = bool(payload.pop("ok", False))
            code = str(payload.pop("code", "ok" if ok else "check_failed"))
            results.append(_status(check.name, ok, code, **payload))
        except Exception as exc:
            results.append(
                _status(
                    check.name,
                    False,
                    "check_error",
                    error_type=type(exc).__name__,
                )
            )

    return {
        "ok": all(item["ok"] for item in results),
        "status": "ready" if all(item["ok"] for item in results) else "attention_required",
        "checks": results,
    }


def _status(name: str, ok: bool, code: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "code": code, **_sanitize(details)}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(
                marker in lowered
                for marker in ("cookie", "secret", "token", "authorization", "api_key", "apikey", "password")
            ):
                safe[str(key)] = "<redacted>"
            else:
                safe[str(key)] = _sanitize(item)
        return safe
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        sanitized = re.sub(
            r"(?i)(cookie|secret|token|authorization|api[_-]?key|password)\s*[=:]\s*[^\s,;&]+",
            r"\1=<redacted>",
            value,
        )
        return re.sub(r"(?i)bearer\s+[a-z0-9._~+/-]+", "Bearer <redacted>", sanitized)
    return value
