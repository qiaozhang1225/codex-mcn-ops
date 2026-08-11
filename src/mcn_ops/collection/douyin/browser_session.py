from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from .contracts import ProviderResult, build_provider_result
from .direct.client import (
    DirectDouyinClient,
    _canonical_method,
    _normalize,
    _work_id,
    scrub_secrets,
)
from .direct import endpoints
from .errors import (
    ProviderConfigError,
    ProviderInputError,
    ProviderResponseError,
    ProviderRiskControlError,
    ProviderUnavailableError,
)


@dataclass(frozen=True)
class BrowserSessionConfig:
    executable: str = "ego-browser"
    task_space: str = "codex-mcn-ops douyin browser provider v1"
    wait_seconds: float = 8.0
    timeout_seconds: float = 45.0
    empty_result_retries: int = 1
    max_page_limit: int = 100
    scroll_wait_seconds: float = 1.5


@dataclass(frozen=True)
class BrowserCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class BrowserNavigation:
    target: str
    response_path: str
    max_pages: int = 1
    max_items: int = 0
    require_exhaustion: bool = False


BrowserRunner = Callable[[BrowserNavigation, BrowserSessionConfig], BrowserCommandResult]


class BrowserSessionDouyinClient:
    """Use the signed-in browser runtime for detail/search/author posts."""

    provider_name = "direct"
    browser_pagination = True

    def __init__(
        self,
        direct: DirectDouyinClient,
        config: BrowserSessionConfig | None = None,
        *,
        runner: BrowserRunner | None = None,
    ) -> None:
        self.direct = direct
        self.config = config or BrowserSessionConfig()
        self.runner = runner or _run_ego_browser
        self._cache: dict[str, ProviderResult] = {}

    def call(
        self,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ProviderResult:
        canonical = _canonical_method(method_key)
        if canonical not in {"detail", "video_search", "user_post"}:
            return self.direct.call(method_key, params=params, body=body, use_cache=use_cache)

        supplied = {**(params or {}), **(body or {})}
        if canonical == "detail":
            source = str(
                supplied.get("url")
                or supplied.get("aweme_id")
                or supplied.get("id")
                or ""
            ).strip()
            navigation = BrowserNavigation(
                target=_safe_detail_target(source),
                response_path="/aweme/v1/web/aweme/detail/",
            )
        elif canonical == "video_search":
            keyword = str(supplied.get("keyword") or "").strip()
            if not keyword:
                raise ProviderInputError("video_search requires keyword")
            offset = str(supplied.get("offset") or "0")
            if offset not in {"", "0"}:
                raise ProviderInputError(
                    "browser video_search currently supports the first result page only"
                )
            encoded_keyword = urllib.parse.quote(keyword, safe="")
            navigation = BrowserNavigation(
                target=f"{endpoints.DOUYIN_HOME}/search/{encoded_keyword}?type=video",
                response_path="/aweme/v1/web/search/item/",
                max_pages=_page_limit(supplied.get("max_pages"), self.config),
                max_items=_item_limit(supplied.get("max_items")),
                require_exhaustion=_requires_exhaustion(supplied.get("max_pages")),
            )
        else:
            sec_uid = str(
                supplied.get("sec_user_id")
                or supplied.get("userId")
                or supplied.get("user_id")
                or ""
            ).strip()
            if not sec_uid:
                raise ProviderInputError("user_post requires sec_user_id")
            cursor = str(supplied.get("max_cursor") or supplied.get("cursor") or "0")
            if cursor not in {"", "0"}:
                raise ProviderInputError(
                    "browser user_post resumes by rerunning the bounded profile traversal; nonzero cursor is not supported"
                )
            navigation = BrowserNavigation(
                target=f"{endpoints.DOUYIN_HOME}/user/{urllib.parse.quote(sec_uid, safe='')}",
                response_path="/aweme/v1/web/aweme/post/",
                max_pages=_page_limit(supplied.get("max_pages"), self.config),
                max_items=_item_limit(supplied.get("max_items")),
                require_exhaustion=_requires_exhaustion(supplied.get("max_pages")),
            )
        cache_key = json.dumps(
            [
                canonical,
                navigation.target,
                navigation.max_pages,
                navigation.max_items,
                navigation.require_exhaustion,
            ],
            ensure_ascii=False,
        )
        if use_cache and cache_key in self._cache:
            cached = dict(self._cache[cache_key])
            cached["cache_hit"] = True
            return cached  # type: ignore[return-value]

        attempts = self.config.empty_result_retries + 1 if canonical in {"video_search", "user_post"} else 1
        raw: dict[str, Any] | None = None
        for attempt in range(attempts):
            try:
                raw = _decode_browser_result(self.runner(navigation, self.config), canonical)
            except ProviderUnavailableError as exc:
                if attempt + 1 < attempts and "response was not observed" in str(exc.detail or ""):
                    continue
                raise
            if canonical == "video_search" and raw.get("data"):
                break
            if canonical == "user_post" and raw.get("aweme_list"):
                break
            if canonical not in {"video_search", "user_post"}:
                break
        assert raw is not None
        normalized, paging = _normalize(canonical, raw)
        if navigation.max_items > 0 and isinstance(normalized.get("items"), list):
            normalized["items"] = normalized["items"][: navigation.max_items]
            if isinstance(normalized.get("source_packages"), list):
                normalized["source_packages"] = normalized["source_packages"][: navigation.max_items]
        browser_meta = raw.get("_browser") if isinstance(raw.get("_browser"), dict) else {}
        if browser_meta:
            paging["raw"] = {**(paging.get("raw") or {}), **browser_meta}
            _ensure_requested_traversal_completed(navigation, paging)
        result = build_provider_result(
            provider=self.provider_name,
            method_key=method_key,
            endpoint=endpoints.METHOD_ENDPOINTS[canonical],
            normalized=normalized,
            raw=scrub_secrets(raw),
            paging=paging,
        )
        if use_cache:
            self._cache[cache_key] = result
        return result


def _page_limit(value: Any, config: BrowserSessionConfig) -> int:
    try:
        requested = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise ProviderInputError("max_pages must be an integer") from exc
    if requested < 0:
        raise ProviderInputError("max_pages must be >= 0")
    configured_limit = max(1, int(config.max_page_limit))
    return configured_limit if requested == 0 else min(requested, configured_limit)


def _item_limit(value: Any) -> int:
    try:
        requested = int(value if value not in (None, "") else 0)
    except (TypeError, ValueError) as exc:
        raise ProviderInputError("max_items must be an integer") from exc
    if requested < 0:
        raise ProviderInputError("max_items must be >= 0")
    return requested


def _requires_exhaustion(value: Any) -> bool:
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def _ensure_requested_traversal_completed(
    navigation: BrowserNavigation,
    paging: dict[str, Any],
) -> None:
    meta = paging.get("raw") if isinstance(paging.get("raw"), dict) else {}
    pages_captured = int(meta.get("pages_captured") or 0)
    stop_reason = str(meta.get("stop_reason") or "")
    has_next = bool(paging.get("has_next"))
    requested_pages_missing = (
        pages_captured < navigation.max_pages
        and stop_reason not in {"max_items", "no_next_page"}
    )
    exhaustion_not_proven = navigation.require_exhaustion and stop_reason == "max_pages"
    if has_next and (requested_pages_missing or exhaustion_not_proven):
        raise ProviderUnavailableError(
            "Douyin browser did not expose the requested next page",
            detail=(
                f"captured={pages_captured}, requested={navigation.max_pages}, "
                f"stop_reason={stop_reason}; traversal is incomplete"
            ),
        )


def _safe_detail_target(source: str) -> str:
    if not source:
        raise ProviderInputError("detail requires a Douyin share URL or aweme_id")
    if source.isdigit():
        work_id = _work_id(source)
        if not work_id:
            raise ProviderInputError("invalid Douyin aweme_id")
        return f"{endpoints.DOUYIN_HOME}/video/{work_id}"
    try:
        parsed = urllib.parse.urlparse(source)
    except ValueError as exc:
        raise ProviderInputError("invalid Douyin share URL") from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not (hostname == "douyin.com" or hostname.endswith(".douyin.com")):
        raise ProviderInputError("detail URL must be an HTTPS douyin.com URL")
    work_id = _work_id(source)
    if work_id:
        return f"{endpoints.DOUYIN_HOME}/video/{work_id}"
    return source


def _run_ego_browser(navigation: BrowserNavigation, config: BrowserSessionConfig) -> BrowserCommandResult:
    executable = shutil.which(config.executable)
    if not executable:
        raise ProviderConfigError(
            "ego-browser is required for DOUYIN_DIRECT_MODE=browser"
        )
    script = _browser_script(navigation, config)
    effective_timeout = max(
        float(config.timeout_seconds),
        navigation.max_pages * float(config.wait_seconds)
        + navigation.max_pages * float(config.scroll_wait_seconds) * 2
        + 20.0,
    )
    try:
        completed = subprocess.run(
            [executable, "nodejs"],
            input=script,
            text=True,
            capture_output=True,
            timeout=effective_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProviderUnavailableError("Douyin browser request timed out") from exc
    return BrowserCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _browser_script(navigation: BrowserNavigation, config: BrowserSessionConfig) -> str:
    target_literal = json.dumps(navigation.target, ensure_ascii=False)
    response_path_literal = json.dumps(navigation.response_path)
    task_literal = json.dumps(config.task_space, ensure_ascii=False)
    wait_seconds = max(1.0, min(float(config.wait_seconds), 30.0))
    scroll_wait_seconds = max(0.5, min(float(config.scroll_wait_seconds), 10.0))
    max_pages = max(1, int(navigation.max_pages))
    max_items = max(0, int(navigation.max_items))
    return f"""const target = {target_literal}
const responsePath = {response_path_literal}
const task = await useOrCreateTaskSpace({task_literal})
const maxPages = {max_pages}
const maxItems = {max_items}
const scrollWaitSeconds = {scroll_wait_seconds}
const isSearch = responsePath === '/aweme/v1/web/search/item/'
const isUserPost = responsePath === '/aweme/v1/web/aweme/post/'
let output
let handedOff = false
let injectedScriptId = null
try {{
  await openOrReuseTab('about:blank', {{ wait: false, timeout: 10 }})
  await cdp('Network.enable')
  await cdp('Page.enable')
  if (isUserPost) {{
    const source = String.raw`(() => {{
      const wanted = new URL(location.href).searchParams.get('__codex_max_cursor')
      const proto = XMLHttpRequest.prototype
      let current = proto.open
      const rewrite = (url) => {{
        if (!wanted) return url
        try {{
          const parsed = new URL(String(url), location.origin)
          if (parsed.pathname !== '/aweme/v1/web/aweme/post/') return url
          parsed.searchParams.set('max_cursor', wanted)
          return String(url).startsWith('http')
            ? parsed.toString()
            : parsed.pathname + '?' + parsed.searchParams.toString()
        }} catch (_) {{
          return url
        }}
      }}
      Object.defineProperty(proto, 'open', {{
        configurable: true,
        enumerable: true,
        get() {{ return current }},
        set(fn) {{
          current = function(method, url, ...rest) {{
            return fn.call(this, method, rewrite(url), ...rest)
          }}
        }},
      }})
    }})()`
    const injected = await cdp('Page.addScriptToEvaluateOnNewDocument', {{ source }})
    injectedScriptId = injected.identifier
  }}
  await cdp('Page.navigate', {{ url: target }})
  await wait({wait_seconds})
  const payloads = []
  const seenRequests = new Set()
  const seenPages = new Set()
  const itemIds = new Set()
  let firstRequestUrl = null
  const payloadItemIds = (payload) => {{
    const values = Array.isArray(payload.data)
      ? payload.data
      : (Array.isArray(payload.aweme_list) ? payload.aweme_list : [])
    const ids = []
    for (const value of values) {{
      const item = value && value.aweme_info ? value.aweme_info : value
      const id = item && (item.aweme_id || item.id)
      if (id) ids.push(String(id))
    }}
    return ids
  }}
  const appendPayload = (payload) => {{
    const ids = payloadItemIds(payload)
    const pageKey = JSON.stringify([
      payload.cursor ?? null,
      payload.max_cursor ?? null,
      ids,
    ])
    if (seenPages.has(pageKey)) return false
    seenPages.add(pageKey)
    payloads.push(payload)
    for (const id of ids) itemIds.add(id)
    return true
  }}
  const captureResponses = async () => {{
    const events = await drainEvents()
    let captured = 0
    for (const event of events) {{
      if (event.method === 'Network.requestWillBeSent') {{
        try {{
          const requestUrl = new URL(event.params.request.url)
          if (requestUrl.pathname === responsePath && !firstRequestUrl) {{
            firstRequestUrl = requestUrl.toString()
          }}
        }} catch (_) {{}}
        continue
      }}
      if (event.method !== 'Network.responseReceived') continue
      let matches = false
      try {{
        matches = new URL(event.params.response.url).pathname === responsePath
      }} catch (_) {{}}
      if (!matches || seenRequests.has(event.params.requestId)) continue
      seenRequests.add(event.params.requestId)
      try {{
        const body = await cdp('Network.getResponseBody', {{ requestId: event.params.requestId }})
        const payload = JSON.parse(body.body)
        if (appendPayload(payload)) captured += 1
      }} catch (_) {{}}
    }}
    return captured
  }}
  await captureResponses()
  const handOffForHuman = async () => {{
    let text
    try {{
      text = String(await js(String.raw`document.body ? document.body.innerText.slice(0, 4000) : ''`))
    }} catch (error) {{
      if (/task space not found/i.test(String(error))) return false
      throw error
    }}
    if (!/(验证码|安全验证|登录后继续|captcha|verification)/i.test(text)) return false
    const handed = await handOffTaskSpace(task.id)
    handedOff = Boolean(handed && handed.done)
    throw new Error(`Douyin browser requires human verification in task space ${{task.id}}`)
  }}
  if (!payloads.length) {{
    await handOffForHuman()
    throw new Error('Douyin browser response was not observed')
  }}

  let idleScrolls = 0
  let stopReason = 'max_pages'
  while (payloads.length < maxPages) {{
    const latest = payloads[payloads.length - 1] || {{}}
    const hasMore = latest.has_more === true || latest.has_more === 1 || latest.hasMore === true || latest.hasMore === 1
    if (!hasMore) {{
      stopReason = 'no_next_page'
      break
    }}
    if (maxItems > 0 && itemIds.size >= maxItems) {{
      stopReason = 'max_items'
      break
    }}
    let captured = 0
    try {{
      if (isSearch && firstRequestUrl) {{
        const requestUrl = new URL(firstRequestUrl)
        requestUrl.searchParams.delete('a_bogus')
        requestUrl.searchParams.set('offset', String(latest.cursor ?? latest.offset ?? ''))
        const searchId = latest.search_id || latest.searchId || (latest.extra && latest.extra.logid) || ''
        if (searchId) requestUrl.searchParams.set('search_id', String(searchId))
        const requestLiteral = JSON.stringify(requestUrl.toString())
        const next = await js(String.raw`(async () => {{
          const response = await window.fetch(${{requestLiteral}}, {{ credentials: 'include' }})
          const text = await response.text()
          try {{ return JSON.parse(text) }} catch (_) {{ return null }}
        }})()`)
        await drainEvents()
        if (next && typeof next === 'object') {{
          captured = appendPayload(next) ? 1 : 0
        }}
      }} else if (isUserPost) {{
        const nextTarget = new URL(target)
        nextTarget.searchParams.set('__codex_max_cursor', String(latest.max_cursor ?? latest.cursor ?? ''))
        nextTarget.searchParams.set('__codex_page_nonce', String(Date.now()))
        await cdp('Page.navigate', {{ url: nextTarget.toString() }})
        await wait({wait_seconds})
        captured = await captureResponses()
        if (!captured) {{
          await wait(scrollWaitSeconds)
          captured = await captureResponses()
        }}
      }} else {{
        stopReason = 'active_pagination_unavailable'
        break
      }}
    }} catch (error) {{
      if (/task space not found/i.test(String(error))) {{
        stopReason = 'task_space_released'
        break
      }}
      throw error
    }}
    idleScrolls = captured > 0 ? 0 : idleScrolls + 1
    if (idleScrolls >= 1) {{
      await handOffForHuman()
      stopReason = 'signed_page_request_failed'
      break
    }}
  }}
  if (payloads.length >= maxPages) stopReason = 'max_pages'
  if (maxItems > 0 && itemIds.size >= maxItems) stopReason = 'max_items'
  output = JSON.stringify({{
    __ego_browser__: true,
    payloads,
    browser_meta: {{
      browser_aggregated: true,
      pages_captured: payloads.length,
      unique_items: itemIds.size,
      max_pages: maxPages,
      max_items: maxItems,
      require_exhaustion: {str(bool(navigation.require_exhaustion)).lower()},
      stop_reason: stopReason,
    }},
  }})
}} finally {{
  if (injectedScriptId) {{
    try {{
      await cdp('Page.removeScriptToEvaluateOnNewDocument', {{ identifier: injectedScriptId }})
    }} catch (_) {{}}
  }}
  if (!handedOff) {{
    try {{
      await completeTaskSpace(task.id, {{ keep: false }})
    }} catch (error) {{
      if (!/task space not found/i.test(String(error))) throw error
    }}
  }}
}}
cliLog(output)
"""


def _decode_browser_result(result: BrowserCommandResult, method_key: str) -> dict[str, Any]:
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        lowered = message.lower()
        if any(marker in lowered for marker in ("captcha", "verification", "安全验证", "验证码")):
            raise ProviderRiskControlError(
                "Douyin browser requires human verification",
                detail=message[-1000:] or None,
            )
        raise ProviderUnavailableError(
            "Douyin browser request failed",
            detail=message[-1000:] or f"exit code {result.returncode}",
        )
    # ego-browser sends large cliLog payloads to stderr even when the command
    # succeeds, while small payloads normally arrive on stdout.
    lines = [
        line.strip()
        for stream in (result.stdout, result.stderr)
        for line in stream.splitlines()
        if line.strip()
    ]
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            decoded = _merge_browser_payloads(payload, method_key)
            if method_key == "detail" and not isinstance(decoded.get("aweme_detail"), dict):
                raise ProviderResponseError("Douyin browser detail returned no aweme_detail")
            if method_key == "video_search" and not isinstance(decoded.get("data"), list):
                raise ProviderResponseError("Douyin browser search returned no data list")
            if method_key == "user_post" and not isinstance(decoded.get("aweme_list"), list):
                raise ProviderResponseError("Douyin browser author page returned no aweme_list")
            return decoded
    raise ProviderResponseError("Douyin browser returned no JSON payload")


def _merge_browser_payloads(envelope: dict[str, Any], method_key: str) -> dict[str, Any]:
    if envelope.get("__ego_browser__") is True:
        payloads = [item for item in envelope.get("payloads", []) if isinstance(item, dict)]
        browser_meta = envelope.get("browser_meta") if isinstance(envelope.get("browser_meta"), dict) else {}
    else:
        payloads = [envelope]
        browser_meta = {}
    if not payloads:
        raise ProviderResponseError("Douyin browser returned no response payloads")
    for payload in payloads:
        status_code = payload.get("status_code")
        if status_code not in (None, 0, "0"):
            raise ProviderResponseError(
                str(payload.get("status_msg") or f"Douyin status_code={status_code}")
            )
    merged = dict(payloads[-1])
    collection_key = "data" if method_key == "video_search" else "aweme_list" if method_key == "user_post" else None
    if collection_key:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for payload in payloads:
            values = payload.get(collection_key)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                key = _browser_item_key(value)
                if key in seen:
                    continue
                seen.add(key)
                items.append(value)
        max_items = int(browser_meta.get("max_items") or 0)
        merged[collection_key] = items[:max_items] if max_items > 0 else items
    if browser_meta:
        merged["_browser"] = browser_meta
    return merged


def _browser_item_key(value: dict[str, Any]) -> str:
    item = value.get("aweme_info") if isinstance(value.get("aweme_info"), dict) else value
    identifier = item.get("aweme_id") or item.get("id")
    if identifier not in (None, ""):
        return str(identifier)
    return json.dumps(scrub_secrets(value), ensure_ascii=False, sort_keys=True)
