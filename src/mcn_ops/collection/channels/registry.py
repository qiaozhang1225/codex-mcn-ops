from __future__ import annotations

from typing import Any

from ..douyin.contracts import ProviderResult, TranscriptionProvider
from ..tools import ToolRegistry, ToolSpec
from .media import acquire_channels_media
from .provider import ChannelsRemoteProvider


def build_channels_registry(
    provider: ChannelsRemoteProvider,
    *,
    transcription_provider: TranscriptionProvider,
    download_limit_bytes: int = 512 * 1024 * 1024,
    download_timeout_seconds: float = 180.0,
) -> ToolRegistry:
    """Expose WeChat Channels through the platform-neutral collection runner."""

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="channels_search_videos",
            description="Search public WeChat Channels videos by keyword.",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string"},
                    "cursor": {"type": "string", "default": ""},
                    "max_pages": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["keyword"],
            },
            handler=lambda args: provider.call(
                "wechat_channels_search",
                params={
                    "keyword": args["keyword"],
                    "cursor": str(args.get("cursor") or ""),
                    "max_pages": int(args.get("max_pages", 1)),
                    "page_size": int(args.get("page_size", 20)),
                },
                use_cache=False,
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="channels_list_author_works",
            description=(
                "List public works for one WeChat Channels author. The response parser "
                "requires live PoC fixture validation before production traversal."
            ),
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "platform_author_id": {"type": "string"},
                    "cursor": {"type": "string", "default": ""},
                    "max_pages": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["platform_author_id"],
            },
            handler=lambda args: provider.call(
                "wechat_channels_author_feed",
                params={
                    "platform_author_id": args["platform_author_id"],
                    "cursor": str(args.get("cursor") or ""),
                    "max_pages": int(args.get("max_pages", 1)),
                    "page_size": int(args.get("page_size", 20)),
                },
                use_cache=False,
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="channels_fetch_video_detail",
            description="Fetch authoritative WeChat Channels detail by stable object identity.",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {"detail_ref": {"type": "object"}},
                "required": ["detail_ref"],
            },
            handler=lambda args: provider.call(
                "wechat_channels_detail",
                body=dict(args.get("detail_ref") or {}),
                use_cache=False,
            ),
        )
    )

    def transcribe(args: dict[str, Any]) -> ProviderResult:
        source_package = dict(args.get("source_package") or {})
        lease = provider.resolve_media_lease(dict(source_package.get("detail_ref") or {}))
        media = acquire_channels_media(
            lease,
            download_limit_bytes=download_limit_bytes,
            timeout_seconds=download_timeout_seconds,
        )
        try:
            safe_package = {
                key: value
                for key, value in source_package.items()
                if key not in {"detail_ref", "media_lease_available"}
            }
            safe_package["audio_sha256"] = media.sha256
            result = transcription_provider.transcribe(
                str(media.path),
                source_package=safe_package,
                use_cache=True,
            )
            normalized = result.get("normalized")
            if isinstance(normalized, dict):
                result_package = normalized.get("source_package")
                if isinstance(result_package, dict):
                    result_package["audio_sha256"] = media.sha256
                    result_package["media_evidence"] = {
                        "size_bytes": media.size_bytes,
                        "advertised_size_bytes": media.advertised_size_bytes,
                        "size_matches_detail": media.size_matches_detail,
                        "sha256": media.sha256,
                        "source_host": media.source_host,
                        "decrypted_prefix_bytes": media.decrypted_prefix_bytes,
                    }
            result["method_key"] = "channels_extract_video_text"
            return result
        finally:
            media.cleanup()

    registry.register(
        ToolSpec(
            name="channels_extract_video_text",
            description="Download, decrypt, and transcribe one WeChat Channels candidate.",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {"source_package": {"type": "object"}},
                "required": ["source_package"],
            },
            handler=transcribe,
        )
    )
    return registry
