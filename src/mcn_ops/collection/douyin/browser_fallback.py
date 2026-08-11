from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from .errors import ProviderError


@runtime_checkable
class BrowserFallback(Protocol):
    def request_human_action(
        self,
        *,
        operation: str,
        error: ProviderError,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HumanActionBrowserFallback:
    """Stop automation at verification boundaries and ask a human to proceed."""

    provider_name: str = "browser"

    def request_human_action(
        self,
        *,
        operation: str,
        error: ProviderError,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "human_action_required",
            "provider": self.provider_name,
            "operation": operation,
            "reason_code": error.code,
            "message": (
                "Open Douyin in an authenticated browser, complete any visible "
                "verification manually, then retry the command."
            ),
            "retryable": True,
            "automation_attempted": False,
            "captcha_bypass_attempted": False,
            "context": _safe_context(context or {}),
        }


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = {"url", "work_id", "user_id", "cursor"}
    safe = {key: value for key, value in context.items() if key in allowed}
    if isinstance(safe.get("url"), str):
        parsed = urlsplit(safe["url"])
        safe["url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return safe
