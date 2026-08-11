from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mcn_ops.migrations.collection_schema_v3 import (
    COLLECTION_SCHEMA_V3,
    LEGACY_CANDIDATE_COLUMNS,
    LEGACY_MATERIAL_COLUMNS,
    LEGACY_TABLES,
    CollectionSchemaV3Migrator,
    MigrationError,
    extract_work_id,
    migrate_collection_schema_v3,
)
from mcn_ops.store import SCHEMA


LEGACY_COLLECTION_SCHEMA_FOR_TEST = """
CREATE TABLE douyin_authors (
    sec_uid TEXT PRIMARY KEY,
    uid TEXT,
    douyin_id TEXT,
    nickname TEXT NOT NULL,
    signature TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    ip_location TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    aweme_count INTEGER,
    total_favorited INTEGER,
    source_material_id TEXT,
    source_work_id TEXT,
    fetched_at TEXT NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE douyin_author_videos (
    id TEXT PRIMARY KEY,
    author_sec_uid TEXT NOT NULL,
    work_id TEXT NOT NULL,
    source_material_id TEXT,
    source_url TEXT,
    title TEXT,
    platform_caption TEXT,
    caption_text TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    post_time TEXT,
    duration_ms INTEGER,
    cover_url TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_package_json TEXT NOT NULL DEFAULT '{}',
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(author_sec_uid, work_id)
);
CREATE TABLE mxnzp_call_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    provider TEXT NOT NULL DEFAULT 'mxnzp',
    tool_name TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE mxnzp_call_cache (
    request_fingerprint TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'mxnzp',
    tool_name TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);
"""


def _make_legacy_db(path: Path, *, unresolved: bool = False) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executescript(
            """
            DROP TABLE material_transcriptions;
            DROP TABLE source_observations;
            DROP TABLE source_works;
            DROP TABLE source_authors;
            DROP TABLE provider_call_logs;
            DROP TABLE provider_call_cache;
            DROP TABLE schema_migrations;
            """
        )
        conn.executescript(LEGACY_COLLECTION_SCHEMA_FOR_TEST)
        conn.execute(
            """
            INSERT INTO collection_runs(
                id, topic, target_count, like_floor, super_like_threshold,
                tool_provider, status, started_at
            ) VALUES ('run-1', '关系', 1, 100, 1000, 'mxnzp', 'completed', '2026-08-01T00:00:00Z')
            """
        )
        material_url = "https://www.douyin.com/video/7345678901234567890"
        conn.execute(
            """
            INSERT INTO collected_materials(
                id, run_id, source_url, title, transcript_text, author_name,
                author_sec_uid, work_id, source_platform, metrics_json,
                material_understanding_json, created_at, updated_at
            ) VALUES (?, 'run-1', ?, '不是作品身份', '完整的历史转写', '示例作者',
                      'MS4wLjAB-author', ?, 'douyin', '{"digg_count":1200}',
                      '{"summary":"可用"}', '2026-08-01T00:00:00Z', '2026-08-01T01:00:00Z')
            """,
            (
                "mat-1",
                None if unresolved else material_url,
                None,
            ),
        )
        source_url = None if unresolved else "https://www.iesdouyin.com/share/video/7345678901234567890"
        raw_json = "{}" if unresolved else '{"aweme_detail":{"aweme_id":"7345678901234567890"}}'
        conn.execute(
            """
            INSERT INTO collection_candidates(
                id, run_id, source_key, source_url, title, metrics_json,
                source_package_json, raw_json, status, material_id, created_at, updated_at
            ) VALUES ('cand-1', 'run-1', ?, ?, '不能用这个标题生成ID', '{"digg_count":1200}',
                      '{}', ?, 'saved', 'mat-1', '2026-08-01T00:00:00Z', '2026-08-01T01:00:00Z')
            """,
            ("unresolved" if unresolved else source_url, source_url, raw_json),
        )
        conn.execute(
            """
            INSERT INTO douyin_authors(
                sec_uid, douyin_id, nickname, follower_count, fetched_at,
                raw_json, created_at, updated_at
            ) VALUES ('MS4wLjAB-author', 'author-001', '示例作者', 50000,
                      '2026-08-01T01:00:00Z', '{}', '2026-08-01T00:00:00Z', '2026-08-01T01:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO douyin_author_videos(
                id, author_sec_uid, work_id, source_material_id, source_url,
                title, metrics_json, source_package_json, raw_json, created_at, updated_at
            ) VALUES ('video-1', 'MS4wLjAB-author', '7345678901234567890', 'mat-1',
                      'https://www.douyin.com/video/7345678901234567890', '作品标题',
                      '{"digg_count":1200}', '{}', '{}',
                      '2026-08-01T00:00:00Z', '2026-08-01T01:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO mxnzp_call_logs(
                id, run_id, tool_name, request_fingerprint, status,
                duration_ms, cache_hit, created_at
            ) VALUES ('call-1', 'run-1', 'detail_v4', 'fp-1', 'success', 20, 0,
                      '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO mxnzp_call_cache(
                request_fingerprint, tool_name, response_json, created_at, updated_at
            ) VALUES ('fp-1', 'detail_v4', '{"code":1}',
                      '2026-08-01T00:00:00Z', '2026-08-01T01:00:00Z')
            """
        )
        conn.commit()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def test_extract_work_id_uses_authoritative_fields_only() -> None:
    assert extract_work_id({"work_id": "explicit-work"}) == ("explicit-work", "explicit:work_id")
    assert extract_work_id({"raw_json": '{"aweme_id":"7345678901234567890"}'})[0] == "7345678901234567890"
    assert extract_work_id({"source_url": "https://www.douyin.com/?modal_id=7345678901234567891"})[0] == "7345678901234567891"
    assert extract_work_id({"source_url": "https://www.douyin.com/video/7345678901234567892"})[0] == "7345678901234567892"
    assert extract_work_id({"title": "7345678901234567893"}) == (None, None)


def test_migration_rebuilds_collection_schema_and_reconciles(tmp_path: Path) -> None:
    source = tmp_path / "legacy.sqlite"
    destination = tmp_path / "v3.sqlite"
    _make_legacy_db(source)

    report = migrate_collection_schema_v3(source, destination)

    assert report["status"] == "validated"
    assert report["checks"]["passed"] is True
    assert report["checks"]["integrity_check"] == "ok"
    assert report["checks"]["foreign_key_violations"] == []
    assert report["unresolved"] == []
    assert report["before"]["collection_candidates"] == report["after"]["collection_candidates"] == 1
    assert report["before"]["collected_materials"] == report["after"]["collected_materials"] == 1
    assert report["expected"] == {
        "source_authors": 1,
        "source_works": 1,
        "source_observations": 3,
        "material_transcriptions": 1,
    }
    assert all(report["checks"]["row_parity"].values())
    json.dumps(report, ensure_ascii=False)

    with sqlite3.connect(source) as legacy:
        assert LEGACY_TABLES <= _tables(legacy)
    with sqlite3.connect(destination) as migrated:
        migrated.row_factory = sqlite3.Row
        tables = _tables(migrated)
        assert not (tables & LEGACY_TABLES)
        assert not (_columns(migrated, "collection_candidates") & LEGACY_CANDIDATE_COLUMNS)
        assert not (_columns(migrated, "collected_materials") & LEGACY_MATERIAL_COLUMNS)
        work = migrated.execute("SELECT * FROM source_works").fetchone()
        assert work["platform_work_id"] == "7345678901234567890"
        assert work["author_id"] == "srcauth:douyin:MS4wLjAB-author"
        assert migrated.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0] == 3
        transcription = migrated.execute("SELECT * FROM material_transcriptions").fetchone()
        assert transcription["identity_key"] == "legacy:material:mat-1"
        assert transcription["transcript_text"] == "完整的历史转写"
        material = migrated.execute("SELECT * FROM collected_materials").fetchone()
        assert material["source_work_id"] == work["id"]
        assert material["transcription_id"] == transcription["id"]
        assert tuple(migrated.execute("SELECT provider, operation FROM provider_call_logs").fetchone()) == ("mxnzp", "detail_v4")
        assert tuple(migrated.execute("SELECT provider, operation FROM provider_call_cache").fetchone()) == ("mxnzp", "detail_v4")
        stored = migrated.execute(
            "SELECT report_json FROM schema_migrations WHERE version = ?", (COLLECTION_SCHEMA_V3,)
        ).fetchone()
        assert stored is not None
        assert json.loads(stored[0])["checks"]["passed"] is True


def test_unresolved_work_identity_fails_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "legacy.sqlite"
    destination = tmp_path / "v3.sqlite"
    _make_legacy_db(source, unresolved=True)

    with pytest.raises(MigrationError) as raised:
        migrate_collection_schema_v3(source, destination)

    assert raised.value.report["status"] == "failed"
    assert {item["table"] for item in raised.value.report["unresolved"]} == {
        "collection_candidates",
        "collected_materials",
    }
    with sqlite3.connect(source) as conn:
        assert LEGACY_TABLES <= _tables(conn)
        assert conn.execute("SELECT COUNT(*) FROM collected_materials").fetchone()[0] == 1


def test_already_migrated_database_is_recognized_idempotently(tmp_path: Path) -> None:
    source = tmp_path / "legacy.sqlite"
    migrated_once = tmp_path / "v3-first.sqlite"
    migrated_twice = tmp_path / "v3-second.sqlite"
    _make_legacy_db(source)
    migrate_collection_schema_v3(source, migrated_once)

    report = migrate_collection_schema_v3(migrated_once, migrated_twice)

    assert report["status"] == "already_migrated"
    assert report["checks"]["passed"] is True
    with sqlite3.connect(migrated_twice) as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_works").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM material_transcriptions").fetchone()[0] == 1


def test_default_dry_run_validates_without_replacing_source(tmp_path: Path) -> None:
    source = tmp_path / "legacy.sqlite"
    _make_legacy_db(source)

    report = CollectionSchemaV3Migrator(source).migrate()

    assert report["status"] == "validated_dry_run"
    assert report["destination"] is None
    with sqlite3.connect(source) as conn:
        assert LEGACY_TABLES <= _tables(conn)


def test_atomic_replacement_is_explicit_and_retains_recovery(tmp_path: Path) -> None:
    source = tmp_path / "mcn_ops.sqlite"
    destination = tmp_path / "mcn_ops.v3.sqlite"
    recovery = tmp_path / "mcn_ops.pre-v3.sqlite"
    _make_legacy_db(source)

    with pytest.raises(ValueError, match="recovery_path"):
        migrate_collection_schema_v3(source, destination, replace=True)

    report = migrate_collection_schema_v3(
        source,
        destination,
        replace=True,
        recovery_path=recovery,
    )

    assert report["status"] == "replaced"
    assert recovery.is_file()
    with sqlite3.connect(source) as current:
        assert not (_tables(current) & LEGACY_TABLES)
    with sqlite3.connect(recovery) as old:
        assert LEGACY_TABLES <= _tables(old)
