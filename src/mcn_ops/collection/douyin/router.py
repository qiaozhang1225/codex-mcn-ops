from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import DouyinProvider, ProviderResult
from .errors import ProviderError


@dataclass
class ProviderRouter:
    """Route Douyin calls to direct first and optionally to paid MXNZP.

    Paid fallback is deliberately fail-closed. Only typed, retryable provider
    failures may cross the provider boundary, and only when the caller opted in.
    """

    direct: DouyinProvider
    mxnzp: DouyinProvider | None = None
    allow_paid_fallback: bool = False
    provider_name: str = "auto"

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        try:
            return self.direct.call(
                method_key,
                params=params,
                body=body,
                use_cache=use_cache,
            )
        except ProviderError as exc:
            if not exc.fallback_allowed:
                raise
            if not self.allow_paid_fallback or self.mxnzp is None:
                raise

            result = dict(
                self.mxnzp.call(
                    method_key,
                    params=params,
                    body=body,
                    use_cache=use_cache,
                )
            )
            result["fallback"] = {
                "attempted": True,
                "from": self.direct.provider_name,
                "to": self.mxnzp.provider_name,
                "reason_code": exc.code,
            }
            return result  # type: ignore[return-value]

