from __future__ import annotations

from pathlib import Path

import pytest

from mcn_ops.collection.channels.media import acquire_channels_media
from mcn_ops.collection.channels.media_probe import _Isaac64
from mcn_ops.collection.channels.provider import ChannelsMediaLease
from mcn_ops.collection.douyin.errors import TranscriptionInputError
from mcn_ops.collection.channels.transcribe_cli import find_candidate


def test_acquire_channels_media_downloads_decrypts_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del tmp_path
    monkeypatch.setattr(
        "mcn_ops.collection.channels.media._validate_channels_locator", lambda url: None
    )
    seed = 123456789
    plaintext = b"\x00\x00\x00\x18ftypisom" + bytes(range(128)) * 50
    stream = _Isaac64(seed).generate(len(plaintext))
    encrypted = bytes(left ^ right for left, right in zip(plaintext, stream, strict=True))

    def downloader(url: str, destination: Path, max_bytes: int, timeout: float) -> None:
        assert url.startswith("https://finder.video.qq.com/")
        assert max_bytes > len(encrypted)
        assert timeout > 0
        destination.write_bytes(encrypted)

    lease = ChannelsMediaLease(
        work_id="work-1",
        locator="https://finder.video.qq.com/media?token=private",
        decryption_key=str(seed),
        duration_ms=1000,
        file_size=len(encrypted),
    )
    media = acquire_channels_media(lease, downloader=downloader)
    media_directory = media.temporary_directory
    try:
        assert media.path.read_bytes() == plaintext
        assert media.decrypted_prefix_bytes == len(plaintext)
        assert media.advertised_size_bytes == len(encrypted)
        assert media.size_matches_detail is True
        assert media.source_host == "finder.video.qq.com"
        assert "private" not in str(media)
    finally:
        media.cleanup()
    assert media_directory.exists() is False


def test_acquire_channels_media_rejects_untrusted_host() -> None:
    lease = ChannelsMediaLease(
        work_id="work-1",
        locator="https://example.com/media.mp4",
        decryption_key="123",
        duration_ms=1000,
        file_size=1,
    )
    with pytest.raises(TranscriptionInputError, match="not allowlisted"):
        acquire_channels_media(lease)


def test_acquire_channels_media_treats_detail_size_as_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mcn_ops.collection.channels.media._validate_channels_locator", lambda url: None
    )
    plaintext = b"\x00\x00\x00\x18ftypisom" + b"payload"

    def downloader(url: str, destination: Path, max_bytes: int, timeout: float) -> None:
        del url, max_bytes, timeout
        destination.write_bytes(plaintext)

    lease = ChannelsMediaLease(
        work_id="work-size-mismatch",
        locator="https://finder.video.qq.com/media",
        decryption_key="",
        duration_ms=1000,
        file_size=len(plaintext) * 12,
    )
    media = acquire_channels_media(lease, downloader=downloader)
    try:
        assert media.size_bytes == len(plaintext)
        assert media.advertised_size_bytes == len(plaintext) * 12
        assert media.size_matches_detail is False
    finally:
        media.cleanup()


def test_find_candidate_reads_provider_jsonl(tmp_path: Path) -> None:
    result_path = tmp_path / "results.jsonl"
    result_path.write_text(
        '{"normalized":{"source_packages":[{"work_id":"work-1","title":"标题"}]}}\n',
        encoding="utf-8",
    )

    assert find_candidate(result_path, "work-1")["title"] == "标题"
    with pytest.raises(ValueError, match="was not found"):
        find_candidate(result_path, "missing")
