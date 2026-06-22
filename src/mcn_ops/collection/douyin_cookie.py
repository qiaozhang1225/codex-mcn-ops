from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any
import urllib.request


DEFAULT_DOUYIN_HOME = "https://www.douyin.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class DouyinCookieResult:
    status: str
    cookie: str
    cookie_valid: bool
    cookie_count: int
    cookie_names: list[str]
    status_code: int | None = None
    final_url: str | None = None
    error: str | None = None

    def to_dict(self, *, include_cookie: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "cookie_valid": self.cookie_valid,
            "cookie_count": self.cookie_count,
            "cookie_names": self.cookie_names,
            "cookie_length": len(self.cookie),
            "status_code": self.status_code,
            "final_url": self.final_url,
        }
        if include_cookie:
            payload["cookie"] = self.cookie
        elif self.cookie:
            payload["cookie_preview"] = _redact_cookie(self.cookie)
        if self.error:
            payload["error"] = self.error
        return payload


def fetch_douyin_cookie(
    *,
    url: str = DEFAULT_DOUYIN_HOME,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: float = 15.0,
    min_cookie_length: int = 100,
) -> DouyinCookieResult:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", None)
            final_url = response.geturl()
    except Exception as exc:
        return DouyinCookieResult(
            status="error",
            cookie="",
            cookie_valid=False,
            cookie_count=0,
            cookie_names=[],
            error=str(exc),
        )

    cookie_pairs = [f"{cookie.name}={cookie.value}" for cookie in jar]
    cookie = "; ".join(cookie_pairs)
    names = [cookie.name for cookie in jar]
    return DouyinCookieResult(
        status="success",
        cookie=cookie,
        cookie_valid=len(cookie) > min_cookie_length,
        cookie_count=len(cookie_pairs),
        cookie_names=names,
        status_code=status_code,
        final_url=final_url,
    )


def _redact_cookie(cookie: str) -> str:
    if len(cookie) <= 24:
        return "<redacted>"
    return f"{cookie[:12]}...{cookie[-8:]}"
