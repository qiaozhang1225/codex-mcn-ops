from __future__ import annotations

from typing import Any

from .mxnzp_client import MxnzpConfig, MxnzpDouyinProClient
from .tools import ToolRegistry, ToolSpec


def build_mxnzp_douyin_registry(
    client: MxnzpDouyinProClient | None = None,
    include_user_post_tools: bool = True,
    include_text_tools: bool = True,
) -> ToolRegistry:
    resolved_client = client or MxnzpDouyinProClient(MxnzpConfig.from_env())
    registry = ToolRegistry()

    _register(
        registry,
        "douyin_search_videos",
        "Search Douyin videos by keyword through the local mxnzp adapter.",
        {
            "keyword": {"type": "string"},
            "offset": {"type": "string", "default": "0"},
            "search_id": {"type": "string", "default": ""},
            "cookie": {"type": "string"},
        },
        ["keyword"],
        lambda args: resolved_client.call(
            "video_search",
            params={
                "keyword": args["keyword"],
                "offset": str(args.get("offset", "0")),
                "search_id": str(args.get("search_id", "")),
                **_maybe("cookie", args.get("cookie")),
            },
        ),
    )

    _register(
        registry,
        "douyin_search_users",
        "Search Douyin users by keyword through the local mxnzp adapter.",
        {
            "keyword": {"type": "string"},
            "offset": {"type": "string", "default": "0"},
            "search_id": {"type": "string", "default": ""},
        },
        ["keyword"],
        lambda args: resolved_client.call("user_search", params=args),
    )

    _register(
        registry,
        "douyin_fetch_video_detail",
        "Fetch a Douyin video detail by share URL.",
        {
            "url": {"type": "string"},
            "version": {"type": "string", "enum": ["v4", "v3", "raw"], "default": "v4"},
        },
        ["url"],
        lambda args: _fetch_video_detail(resolved_client, args),
    )

    _register(
        registry,
        "douyin_resolve_share_link",
        "Resolve a Douyin work ID into full and short share links.",
        {"work_id": {"type": "string"}},
        ["work_id"],
        lambda args: resolved_client.call("share_link", params={"id": args["work_id"]}),
    )

    if include_text_tools:
        _register(
            registry,
            "douyin_extract_video_text",
            "Extract spoken copy text from a Douyin video share URL through mxnzp.",
            {"url": {"type": "string"}},
            ["url"],
            lambda args: resolved_client.call("video_to_text_v2", body={"url": args["url"]}),
        )

    _register(
        registry,
        "douyin_fetch_user_profile",
        "Fetch Douyin user profile by sec_uid, Douyin ID, or userCode.",
        {
            "user_id": {"type": "string"},
            "by_douyin_id": {"type": "boolean", "default": False},
        },
        ["user_id"],
        lambda args: resolved_client.call(
            "user_info_dy_id" if args.get("by_douyin_id") else "user_info",
            params={"userCode" if args.get("by_douyin_id") else "userId": args["user_id"]},
        ),
    )

    if include_user_post_tools:
        _register(
            registry,
            "douyin_fetch_user_posts",
            "Fetch a Douyin user's posted videos. Requires Douyin cookie.",
            {
                "user_id": {"type": "string"},
                "cursor": {"type": "string", "default": ""},
                "sort_type": {"type": "integer", "enum": [0, 1], "default": 0},
                "cookie": {"type": "string"},
            },
            ["user_id"],
            lambda args: resolved_client.call(
                "user_post",
                params={
                    "userId": args["user_id"],
                    "cursor": str(args.get("cursor", "")),
                    "sortType": int(args.get("sort_type", 0)),
                    **_maybe("cookie", args.get("cookie")),
                },
            ),
        )

    _register(
        registry,
        "douyin_fetch_user_favorites",
        "Fetch videos from a user's public favorites/share page when available.",
        {
            "share_text": {"type": "string"},
            "cursor": {"type": "string", "default": ""},
        },
        ["share_text"],
        lambda args: resolved_client.call(
            "user_favorite_list",
            body={"shareText": args["share_text"], "cursor": str(args.get("cursor", ""))},
        ),
    )

    _register(
        registry,
        "douyin_fetch_comments",
        "Fetch comments for a Douyin video share URL.",
        {
            "url": {"type": "string"},
            "cursor": {"type": "string", "default": "0"},
            "comment_id": {"type": "string"},
        },
        ["url"],
        lambda args: resolved_client.call(
            "child_comments" if args.get("comment_id") else "comments",
            params={
                "url": args["url"],
                "cursor": str(args.get("cursor", "0")),
                **_maybe("commentId", args.get("comment_id")),
            },
        ),
    )

    _register(
        registry,
        "douyin_fetch_billboard",
        "Fetch Douyin billboard metadata or ranked videos/hot topics.",
        {
            "kind": {
                "type": "string",
                "enum": ["vertical_tag", "video", "city_list", "hot_category", "hot_rise", "hot_city", "hot_total"],
            },
            "page": {"type": "integer", "default": 1},
            "page_size": {"type": "integer", "default": 10},
            "category": {"type": "string"},
            "order": {"type": "string", "enum": ["rank", "rank_diff"], "default": "rank"},
            "city_code": {"type": "integer"},
            "date": {"type": "integer", "enum": [1, 24, 72, 168], "default": 24},
            "sub_type": {"type": "integer", "default": 1001},
            "root_tag": {"type": "integer"},
            "sub_tag": {"type": "integer"},
        },
        ["kind"],
        lambda args: _fetch_billboard(resolved_client, args),
    )

    _register(
        registry,
        "douyin_fetch_audience_profile",
        "Fetch audience profile data for a video or a user.",
        {
            "target_type": {"type": "string", "enum": ["video", "user"]},
            "target_info": {"type": "string"},
            "profile_type": {"type": "integer", "enum": [1, 2, 3, 4, 5, 6, 7, 8]},
        },
        ["target_type", "target_info", "profile_type"],
        lambda args: _fetch_audience_profile(resolved_client, args),
    )

    return registry


def _register(
    registry: ToolRegistry,
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    handler: Any,
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


def _fetch_video_detail(client: MxnzpDouyinProClient, args: dict[str, Any]) -> dict[str, Any]:
    version = args.get("version", "v4")
    if version == "v3":
        return client.call("detail_v3", params={"url": args["url"]})
    if version == "raw":
        return client.call("detail", params={"url": args["url"]})
    return client.call("detail_v4", body={"url": args["url"]})


def _fetch_billboard(client: MxnzpDouyinProClient, args: dict[str, Any]) -> dict[str, Any]:
    kind = args["kind"]
    if kind in {"vertical_tag", "city_list"}:
        return client.call(f"billboard_{kind}")
    if kind == "hot_category":
        return client.call("billboard_hot_category", params={"category": args.get("category", "rise")})
    if kind == "video":
        return client.call(
            "billboard_video",
            params={
                "date": int(args.get("date", 24)),
                "page": int(args.get("page", 1)),
                "pageSize": int(args.get("page_size", 10)),
                "subType": int(args.get("sub_type", 1001)),
                **_maybe("rootTag", args.get("root_tag")),
                **_maybe("subTag", args.get("sub_tag")),
            },
        )
    return client.call(
        f"billboard_{kind}",
        params={
            "page": int(args.get("page", 1)),
            "pageSize": int(args.get("page_size", 10)),
            "category": args.get("category", 0),
            "order": args.get("order", "rank"),
            **_maybe("cityCode", args.get("city_code")),
        },
    )


def _fetch_audience_profile(client: MxnzpDouyinProClient, args: dict[str, Any]) -> dict[str, Any]:
    if args["target_type"] == "video":
        return client.call(
            "aweme_digs_interest",
            params={"workInfo": args["target_info"], "type": int(args["profile_type"])},
        )
    return client.call(
        "user_fans_data",
        params={"userInfo": args["target_info"], "type": int(args["profile_type"])},
    )


def _maybe(key: str, value: Any) -> dict[str, Any]:
    return {key: value} if value not in (None, "") else {}
