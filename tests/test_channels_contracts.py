from __future__ import annotations

import gzip
import json

import pytest

from mcn_ops.collection.channels.contracts import (
    ChannelsProtocolError,
    WorkerCapabilities,
    decode_cloud_message,
    redact_payload,
    redact_text,
)
from mcn_ops.collection.channels.media_probe import (
    _Isaac64,
    extract_media_candidate,
    summarize_candidate,
)


def test_decode_gzip_heartbeat_and_capabilities() -> None:
    raw = {
        "id": "hb-1",
        "type": "heartbeat",
        "client_id": "windows-01",
        "payload": {
            "hostname": "worker",
            "version": "5.7",
            "status": "running",
            "api_ready": True,
            "supports_search": True,
            "supports_feed": True,
            "supports_profile": False,
            "methods": {"finderSearch": True},
        },
        "timestamp": 123,
    }
    message = decode_cloud_message(gzip.compress(json.dumps(raw).encode("utf-8")))
    capabilities = WorkerCapabilities.from_heartbeat(message)

    assert capabilities.worker_id == "windows-01"
    assert capabilities.api_ready is True
    assert capabilities.supports_search is True
    assert capabilities.methods == {"finderSearch": True}


def test_invalid_message_fails_closed() -> None:
    with pytest.raises(ChannelsProtocolError, match="requires id"):
        decode_cloud_message('{"type":"heartbeat"}')


def test_redact_payload_removes_media_credentials() -> None:
    value = {
        "urlToken": "private-token",
        "decodeKey": "12345",
        "video_url": "https://media.example/video.mp4?token=abc&quality=high&sign=secret",
        "nested": {
            "cookie": "session=secret",
            "sessionBuffer": "opaque-session",
            "pass_ticket": "ticket-value",
        },
    }

    redacted = redact_payload(value)

    assert redacted["urlToken"] == "<redacted>"
    assert redacted["decodeKey"] == "<redacted>"
    assert "abc" not in redacted["video_url"]
    assert "secret" not in redacted["video_url"]
    assert "quality=high" in redacted["video_url"]
    assert redacted["nested"]["cookie"] == "<redacted>"
    assert redacted["nested"]["sessionBuffer"] == "<redacted>"
    assert redacted["nested"]["pass_ticket"] == "<redacted>"


def test_redact_text_removes_embedded_signed_url_and_decode_key() -> None:
    value = (
        "download failed https://media.example/video.mp4?token=abc&quality=high "
        "decodeKey=12345 pass_ticket=ticket-value"
    )

    redacted = redact_text(value)

    assert "abc" not in redacted
    assert "12345" not in redacted
    assert "ticket-value" not in redacted
    assert "quality=high" in redacted
    assert "decodeKey=<redacted>" in redacted


def test_media_candidate_summary_never_contains_locator_or_key() -> None:
    raw = {
        "object": {
            "id": "work-1",
            "objectNonceId": "nonce-1",
            "objectDesc": {
                "media": [
                    {
                        "url": "https://media.example/video.mp4?quality=high&",
                        "urlToken": "token=private&sign=secret",
                        "decodeKey": "decrypt-me",
                        "durationMs": 12000,
                        "fileSize": 3456,
                    }
                ]
            },
        }
    }

    candidate = extract_media_candidate(raw)
    assert candidate is not None
    summary = summarize_candidate(candidate, source="search")
    serialized = json.dumps(summary)

    assert summary["locator_present"] is True
    assert summary["locator_host"] == "media.example"
    assert summary["locator_query_keys"] == ["quality", "sign", "token"]
    assert summary["decryption_key_present"] is True
    assert "private" not in serialized
    assert "secret" not in serialized
    assert "decrypt-me" not in serialized


def test_media_candidate_supports_nested_detail_response() -> None:
    raw = {
        "data": {
            "object": {
                "id": "work-2",
                "encryptedObjectId": "eid-2",
                "objectDesc": {"media": [{"urlToken": "https://cdn.example/media"}]},
            }
        }
    }

    candidate = extract_media_candidate(raw)

    assert candidate is not None
    assert candidate["work_id"] == "work-2"
    assert candidate["encrypted_object_id"] == "eid-2"
    assert candidate["locator"] == "https://cdn.example/media"


def test_isaac64_matches_worker_reference_vector() -> None:
    assert _Isaac64(123456789).generate(32).hex() == (
        "9c87e6946a410182aee08a5a116f7cb986f10740dd490b9a330cd31db53ddc4a"
    )
