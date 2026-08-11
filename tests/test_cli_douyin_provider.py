from __future__ import annotations

import json
import pytest

import mcn_ops.cli as cli
from mcn_ops.collection.douyin.contracts import build_provider_result


class FakeProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call(self, method_key, params=None, body=None, use_cache=True):
        self.calls.append(
            {
                "method_key": method_key,
                "params": params,
                "body": body,
                "use_cache": use_cache,
            }
        )
        return build_provider_result(
            provider=self.provider_name,
            method_key=method_key,
            normalized={"text": "ok"},
        )


def test_douyin_detail_uses_direct_provider_without_db_init(monkeypatch, tmp_path, capsys) -> None:
    provider = FakeProvider()
    captured: dict[str, object] = {}

    def build(name, *, allow_paid_fallback=False):
        captured.update(name=name, allow_paid_fallback=allow_paid_fallback)
        return provider

    monkeypatch.setattr(cli, "build_data_provider", build)
    db_path = tmp_path / "should-not-exist.sqlite"

    exit_code = cli.main(
        [
            "--db-path",
            str(db_path),
            "collect",
            "douyin",
            "detail",
            "https://www.douyin.com/video/1234567890123456789",
            "--no-cache",
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured == {"name": "direct", "allow_paid_fallback": False}
    assert provider.calls == [
        {
            "method_key": "detail_v4",
            "params": None,
            "body": {"url": "https://www.douyin.com/video/1234567890123456789"},
            "use_cache": False,
        }
    ]
    assert json.loads(capsys.readouterr().out)["provider"] == "fake"
    assert not db_path.exists()


def test_douyin_transcribe_rejects_removed_paid_fallback(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                "collect",
                "douyin",
                "transcribe",
                "https://www.douyin.com/video/1234567890123456789",
                "--allow-paid-fallback",
            ]
        )

    assert "unrecognized arguments: --allow-paid-fallback" in capsys.readouterr().err


def test_douyin_search_video_passes_bounded_browser_traversal(monkeypatch, capsys) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(cli, "build_data_provider", lambda *args, **kwargs: provider)

    exit_code = cli.main(
        [
            "collect",
            "douyin",
            "search-video",
            "--keyword",
            "亲子关系",
            "--max-pages",
            "6",
            "--max-items",
            "80",
            "--json",
        ]
    )

    assert exit_code == 0
    assert provider.calls == [
        {
            "method_key": "video_search",
            "params": {
                "keyword": "亲子关系",
                "offset": "0",
                "search_id": "",
                "max_pages": 6,
                "max_items": 80,
            },
            "body": None,
            "use_cache": True,
        }
    ]
    assert json.loads(capsys.readouterr().out)["provider"] == "fake"


def test_douyin_user_posts_passes_profile_traversal_limits(monkeypatch, capsys) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(cli, "build_data_provider", lambda *args, **kwargs: provider)

    exit_code = cli.main(
        [
            "collect",
            "douyin",
            "user-posts",
            "--sec-uid",
            "MS4.target",
            "--max-pages",
            "20",
            "--max-items",
            "500",
            "--json",
        ]
    )

    assert exit_code == 0
    assert provider.calls[0]["method_key"] == "user_post"
    assert provider.calls[0]["params"] == {
        "userId": "MS4.target",
        "cursor": "0",
        "sortType": 0,
        "max_pages": 20,
        "max_items": 500,
    }
    assert json.loads(capsys.readouterr().out)["provider"] == "fake"
