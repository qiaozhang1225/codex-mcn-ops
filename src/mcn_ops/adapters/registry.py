from __future__ import annotations

from .base import PlatformAdapter, make_adapter


_ADAPTERS: dict[str, PlatformAdapter] = {
    "douyin": make_adapter(
        key="douyin",
        display_name="Douyin",
        package_name="com.ss.android.ugc.aweme",
        max_title_length=30,
        max_body_length=1000,
        max_hashtags=5,
        notes=("Official V1 path is Android app automation via ADB, not web private APIs.",),
    ),
    "xhs": make_adapter(
        key="xhs",
        display_name="Xiaohongshu",
        package_name="com.xingin.xhs",
        max_title_length=20,
        max_body_length=1000,
        max_hashtags=20,
        notes=("Topic selection may require UI calibration per app version.",),
    ),
    "wechat_channels": make_adapter(
        key="wechat_channels",
        display_name="WeChat Channels",
        package_name="com.tencent.mm",
        max_body_length=1000,
        max_hashtags=10,
        notes=("Publishing is inside WeChat; adapter must launch and navigate to Channels.",),
    ),
    "kwai": make_adapter(
        key="kwai",
        display_name="Kuaishou",
        package_name="com.smile.gifmaker",
        max_body_length=500,
        max_hashtags=3,
        notes=("Cover constraints should be verified on the connected device before live publish.",),
    ),
}


def list_platforms() -> list[str]:
    return sorted(_ADAPTERS)


def get_adapter(platform: str) -> PlatformAdapter:
    try:
        return _ADAPTERS[platform]
    except KeyError as exc:
        supported = ", ".join(list_platforms())
        raise KeyError(f"unknown platform: {platform}; supported: {supported}") from exc
