from __future__ import annotations

from pathlib import Path

from mcn_ops.adapters import get_adapter, list_platforms
from mcn_ops.models import ContentPackage


def test_v1_platforms_are_registered() -> None:
    assert list_platforms() == ["douyin", "kwai", "wechat_channels", "xhs"]


def test_adapter_stops_before_submit_by_default() -> None:
    adapter = get_adapter("douyin")
    content = ContentPackage(
        id="content_1",
        title="短标题",
        body="正文",
        media_paths=[Path("/tmp/video.mp4")],
        hashtags=["topic"],
    )

    steps = adapter.build_steps(content)

    assert steps[-1].name == "stop_before_submit"
    assert steps[-1].action == "stop"


def test_adapter_validates_platform_limits() -> None:
    adapter = get_adapter("xhs")
    content = ContentPackage(
        id="content_1",
        title="x" * 21,
        body="body",
        media_paths=[Path("/tmp/video.mp4")],
    )

    issues = adapter.validate(content)

    assert any(issue.field == "title" for issue in issues)
