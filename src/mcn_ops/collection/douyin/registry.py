from __future__ import annotations

from typing import Any, Callable

from ..tools import ToolRegistry, ToolSpec
from .contracts import DouyinProvider, ProviderResult, TranscriptionProvider


def build_douyin_registry(
    provider: DouyinProvider,
    *,
    transcription_provider: TranscriptionProvider | None = None,
    include_user_post_tools: bool = True,
    include_text_tools: bool = True,
) -> ToolRegistry:
    """Build the stable collection tool surface for any Douyin provider."""

    registry = ToolRegistry()
    _register(
        registry,
        "douyin_search_videos",
        "Search Douyin videos by keyword.",
        {
            "keyword": {"type": "string"},
            "offset": {"type": "string", "default": "0"},
            "search_id": {"type": "string", "default": ""},
            "max_pages": {"type": "integer", "default": 1},
            "max_items": {"type": "integer", "default": 0},
            "cookie": {"type": "string"},
        },
        ["keyword"],
        lambda args: provider.call(
            "video_search",
            params={
                "keyword": args["keyword"],
                "offset": str(args.get("offset", "0")),
                "search_id": str(args.get("search_id", "")),
                **_browser_limits(provider, args),
                **_maybe("cookie", args.get("cookie")),
            },
        ),
    )
    _register(
        registry,
        "douyin_search_users",
        "Search Douyin users by keyword.",
        {
            "keyword": {"type": "string"},
            "offset": {"type": "string", "default": "0"},
            "search_id": {"type": "string", "default": ""},
        },
        ["keyword"],
        lambda args: provider.call("user_search", params=args),
    )
    _register(
        registry,
        "douyin_fetch_video_detail",
        "Fetch a Douyin video detail by share URL.",
        {"url": {"type": "string"}},
        ["url"],
        lambda args: provider.call("detail_v4", body={"url": args["url"]}),
    )
    _register(
        registry,
        "douyin_resolve_share_link",
        "Resolve a Douyin work ID into share links.",
        {"work_id": {"type": "string"}},
        ["work_id"],
        lambda args: provider.call("share_link", params={"id": args["work_id"]}),
    )
    _register(
        registry,
        "douyin_fetch_user_profile",
        "Fetch a Douyin user profile.",
        {
            "user_id": {"type": "string"},
            "by_douyin_id": {"type": "boolean", "default": False},
        },
        ["user_id"],
        lambda args: provider.call(
            "user_info_dy_id" if args.get("by_douyin_id") else "user_info",
            params={"userCode" if args.get("by_douyin_id") else "userId": args["user_id"]},
        ),
    )
    if include_user_post_tools:
        _register(
            registry,
            "douyin_fetch_user_posts",
            "Fetch a Douyin user's posted videos.",
            {
                "user_id": {"type": "string"},
                "cursor": {"type": "string", "default": ""},
                "sort_type": {"type": "integer", "enum": [0, 1], "default": 0},
                "max_pages": {"type": "integer", "default": 1},
                "max_items": {"type": "integer", "default": 0},
                "cookie": {"type": "string"},
            },
            ["user_id"],
            lambda args: provider.call(
                "user_post",
                params={
                    "userId": args["user_id"],
                    "cursor": str(args.get("cursor", "")),
                    "sortType": int(args.get("sort_type", 0)),
                    **_browser_limits(provider, args),
                    **_maybe("cookie", args.get("cookie")),
                },
            ),
        )
    _register(
        registry,
        "douyin_fetch_comments",
        "Fetch comments for a Douyin video.",
        {
            "url": {"type": "string"},
            "cursor": {"type": "string", "default": "0"},
            "comment_id": {"type": "string"},
        },
        ["url"],
        lambda args: provider.call(
            "child_comments" if args.get("comment_id") else "comments",
            params={
                "url": args["url"],
                "cursor": str(args.get("cursor", "0")),
                **_maybe("commentId", args.get("comment_id")),
            },
        ),
    )
    if include_text_tools:
        _register(
            registry,
            "douyin_extract_video_text",
            "Extract spoken copy text from a Douyin video.",
            {
                "url": {"type": "string"},
                "source_package": {"type": "object", "additionalProperties": True},
            },
            ["url"],
            _transcription_handler(provider, transcription_provider),
        )
    return registry


def _transcription_handler(
    provider: DouyinProvider,
    transcription_provider: TranscriptionProvider | None,
) -> Callable[[dict[str, Any]], ProviderResult]:
    if transcription_provider is None:
        return lambda args: provider.call(
            "video_to_text_v2",
            body={
                "url": args["url"],
                **_maybe("source_package", args.get("source_package")),
            },
        )
    return lambda args: transcription_provider.transcribe(
        args["url"],
        source_package=args.get("source_package"),
    )


def _register(
    registry: ToolRegistry,
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    handler: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    registry.register(
        ToolSpec(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": required,
            },
            handler=handler,
        )
    )


def _maybe(key: str, value: Any) -> dict[str, Any]:
    return {key: value} if value not in (None, "") else {}


def _browser_limits(provider: DouyinProvider, args: dict[str, Any]) -> dict[str, Any]:
    if not bool(getattr(provider, "browser_pagination", False)):
        return {}
    return {
        "max_pages": int(args.get("max_pages", 1)),
        "max_items": int(args.get("max_items", 0)),
    }
