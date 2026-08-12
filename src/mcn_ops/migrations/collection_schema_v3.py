from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, urlparse


COLLECTION_SCHEMA_V3 = "collection_schema_v3"
LEGACY_TABLES = {
    "douyin_authors",
    "douyin_author_videos",
    "mxnzp_call_logs",
    "mxnzp_call_cache",
}
REQUIRED_TABLES = {
    "source_authors",
    "source_works",
    "source_observations",
    "material_transcriptions",
    "provider_call_logs",
    "provider_call_cache",
    "schema_migrations",
}
LEGACY_CANDIDATE_COLUMNS = {
    "source_key",
    "source_url",
    "title",
    "author_name",
    "platform_caption",
    "metrics_json",
    "source_package_json",
    "raw_json",
}
LEGACY_MATERIAL_COLUMNS = {
    "source_url",
    "title",
    "platform_caption",
    "caption_text",
    "hashtags_json",
    "transcript_text",
    "author_name",
    "author_sec_uid",
    "author_profile_url",
    "author_douyin_id",
    "work_id",
    "work_short_url",
    "source_platform",
    "post_time",
    "duration_ms",
    "cover_url",
    "video_url",
    "audio_url",
    "author_identity_confidence",
    "metrics_json",
    "source_package_json",
    "raw_json",
}

_VIDEO_PATH_RE = re.compile(r"/video/(\d+)(?:/|$)")
_DIGIT_ID_RE = re.compile(r"^\d{10,}$")


class MigrationError(RuntimeError):
    """Raised when a migration cannot prove that the rebuilt database is safe."""

    def __init__(self, message: str, report: Mapping[str, Any]):
        super().__init__(message)
        self.report = dict(report)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return decoded


def _json_text(value: Any, fallback: Any) -> str:
    decoded = _json(value, fallback)
    return json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in _tables(conn):
        return []
    return [_row_dict(row) for row in conn.execute(f'SELECT * FROM "{table}"')]


def _walk_json(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _id_from_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _VIDEO_PATH_RE.search(text)
    if match:
        return match.group(1)
    try:
        modal_id = parse_qs(urlparse(text).query).get("modal_id", [None])[0]
    except ValueError:
        return None
    modal_id = str(modal_id or "").strip()
    return modal_id if _DIGIT_ID_RE.fullmatch(modal_id) else None


def extract_work_id(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Extract a real platform work id without deriving identity from text."""

    explicit = str(row.get("work_id") or "").strip()
    if explicit:
        return explicit, "explicit:work_id"

    packages = []
    for field in ("source_package_json", "raw_json"):
        value = _json(row.get(field), {})
        if isinstance(value, (dict, list)):
            packages.append((field, value))

    for field, package in packages:
        for wanted in ("work_id", "aweme_id"):
            for key, value in _walk_json(package):
                candidate = str(value or "").strip()
                if key == wanted and candidate:
                    return candidate, f"json:{field}:{wanted}"
        for key, value in _walk_json(package):
            candidate = str(value or "").strip()
            if key == "id" and _DIGIT_ID_RE.fullmatch(candidate):
                return candidate, f"json:{field}:id"

    for field in ("source_url", "source_key", "work_short_url", "video_url"):
        found = _id_from_url(row.get(field))
        if found:
            return found, f"url:{field}"

    source_key = str(row.get("source_key") or "").strip()
    if _DIGIT_ID_RE.fullmatch(source_key):
        return source_key, "explicit:source_key"

    for field, package in packages:
        for key, value in _walk_json(package):
            if key.endswith("url") or key.endswith("uri") or key in {"share_link", "source_link"}:
                found = _id_from_url(value)
                if found:
                    return found, f"json-url:{field}:{key}"
    return None, None


FINAL_SCHEMA = """
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    report_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE source_authors (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_author_id TEXT NOT NULL,
    uid TEXT,
    account_id TEXT,
    display_name TEXT,
    signature TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    ip_location TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    work_count INTEGER,
    total_favorited INTEGER,
    raw_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(platform, platform_author_id)
);

CREATE TABLE source_works (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_work_id TEXT NOT NULL,
    author_id TEXT,
    source_url TEXT,
    short_url TEXT,
    title TEXT,
    caption_text TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    published_at TEXT,
    duration_ms INTEGER,
    cover_url TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(platform, platform_work_id),
    FOREIGN KEY(author_id) REFERENCES source_authors(id)
);

CREATE TABLE source_observations (
    id TEXT PRIMARY KEY,
    source_work_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    UNIQUE(source_table, source_row_id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id)
);

CREATE TABLE material_transcriptions (
    id TEXT PRIMARY KEY,
    source_work_id TEXT NOT NULL,
    identity_key TEXT NOT NULL UNIQUE CHECK(length(trim(identity_key)) > 0),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    audio_sha256 TEXT,
    transcript_text TEXT NOT NULL,
    language TEXT,
    options_json TEXT NOT NULL DEFAULT '{}',
    provider_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_work_id) REFERENCES source_works(id)
);

CREATE TABLE provider_call_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id)
);

CREATE TABLE provider_call_cache (
    provider TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    operation TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(provider, request_fingerprint)
);

CREATE TABLE collection_candidates_v3 (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_work_id TEXT NOT NULL,
    status TEXT NOT NULL,
    selection_reason TEXT,
    skip_reason TEXT,
    skip_detail TEXT,
    threshold_mode TEXT,
    material_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, source_work_id),
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id),
    FOREIGN KEY(material_id) REFERENCES collected_materials(id)
);

CREATE TABLE collected_materials_v3 (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    role_id TEXT,
    source_role_id TEXT,
    source_work_id TEXT NOT NULL,
    transcription_id TEXT,
    clean_title TEXT,
    summary_text TEXT,
    hook_text TEXT,
    core_claim TEXT,
    content_type TEXT,
    oral_script_pattern TEXT,
    audience TEXT,
    emotion_trigger TEXT,
    risk_level TEXT,
    content_structure_json TEXT NOT NULL DEFAULT '[]',
    key_points_json TEXT NOT NULL DEFAULT '[]',
    rewrite_angles_json TEXT NOT NULL DEFAULT '[]',
    usable_quotes_json TEXT NOT NULL DEFAULT '[]',
    risk_notes_json TEXT NOT NULL DEFAULT '[]',
    recommended_platforms_json TEXT NOT NULL DEFAULT '[]',
    next_collection_keywords_json TEXT NOT NULL DEFAULT '[]',
    material_eligibility_json TEXT NOT NULL DEFAULT '{}',
    eligibility_status TEXT NOT NULL DEFAULT 'accepted',
    eligibility_provider TEXT NOT NULL DEFAULT 'local-rules',
    eligibility_version TEXT NOT NULL DEFAULT 'material-eligibility-v1',
    eligibility_reason_json TEXT NOT NULL DEFAULT '[]',
    content_form TEXT,
    knowledge_core_score REAL NOT NULL DEFAULT 0,
    oral_script_fit_score REAL NOT NULL DEFAULT 0,
    ip_fit_score REAL NOT NULL DEFAULT 0,
    reject_reason TEXT,
    material_understanding_json TEXT NOT NULL DEFAULT '{}',
    understanding_provider TEXT NOT NULL DEFAULT 'codex-agent',
    understanding_model TEXT NOT NULL DEFAULT 'gpt-5.5',
    sample_pool_clues_json TEXT NOT NULL DEFAULT '[]',
    understanding_status TEXT NOT NULL DEFAULT 'pending',
    status TEXT NOT NULL DEFAULT 'collected',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES collection_runs(id),
    FOREIGN KEY(task_id) REFERENCES collection_tasks(id),
    FOREIGN KEY(role_id) REFERENCES ip_roles(id),
    FOREIGN KEY(source_work_id) REFERENCES source_works(id),
    FOREIGN KEY(transcription_id) REFERENCES material_transcriptions(id)
);
"""


class CollectionSchemaV3Migrator:
    """Rebuild collection storage in a separate SQLite file and prove parity."""

    def __init__(self, source_path: Path | str):
        self.source_path = Path(source_path).expanduser().resolve()

    def migrate(
        self,
        destination_path: Path | str | None = None,
        *,
        replace: bool = False,
        recovery_path: Path | str | None = None,
    ) -> dict[str, Any]:
        if not self.source_path.is_file():
            raise FileNotFoundError(self.source_path)
        if replace and recovery_path is None:
            raise ValueError("recovery_path is required for atomic replacement")

        owned_temp: tempfile.TemporaryDirectory[str] | None = None
        if destination_path is None:
            owned_temp = tempfile.TemporaryDirectory(prefix="mcn-schema-v3-")
            destination = Path(owned_temp.name) / "mcn_ops.v3.sqlite"
        else:
            destination = Path(destination_path).expanduser().resolve()
        if destination == self.source_path:
            raise ValueError("destination must differ from source")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        report: dict[str, Any] = {
            "migration": COLLECTION_SCHEMA_V3,
            "status": "running",
            "source": str(self.source_path),
            "destination": None if owned_temp else str(destination),
            "replace_requested": replace,
            "started_at": _now(),
            "unresolved": [],
            "checks": {},
        }
        migration_record_created = False
        try:
            self._backup_read_only(destination)
            with sqlite3.connect(destination) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = OFF")
                if self._already_migrated(conn):
                    report["status"] = "already_migrated"
                    self._validate_final(conn, report)
                else:
                    self._rebuild(conn, report)
                    self._validate_final(conn, report)
                    if not report["checks"].get("passed"):
                        raise MigrationError("collection schema v3 reconciliation failed", report)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at, report_json) VALUES (?, ?, ?)",
                        (COLLECTION_SCHEMA_V3, _now(), json.dumps(report, ensure_ascii=False, sort_keys=True)),
                    )
                    conn.commit()
                    migration_record_created = True
                    report["status"] = "validated"

            if replace:
                recovery = Path(recovery_path).expanduser().resolve()
                report["status"] = "replaced"
                report["recovery"] = str(recovery)
                report["destination"] = str(self.source_path)
                report["completed_at"] = _now()
                if migration_record_created:
                    self._update_migration_report(destination, report)
                self._atomic_replace(destination, recovery)
            elif owned_temp:
                report["status"] = "validated_dry_run" if report["status"] == "validated" else report["status"]
                report["completed_at"] = _now()
            else:
                report["completed_at"] = _now()
                if migration_record_created:
                    self._update_migration_report(destination, report)
            return report
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)
            report["completed_at"] = _now()
            if isinstance(exc, MigrationError):
                exc.report.update(report)
                raise
            raise MigrationError(str(exc), report) from exc
        finally:
            if owned_temp is not None:
                owned_temp.cleanup()

    def _backup_read_only(self, destination: Path) -> None:
        uri = self.source_path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as source, sqlite3.connect(destination) as target:
            source.backup(target)

    @staticmethod
    def _already_migrated(conn: sqlite3.Connection) -> bool:
        if "schema_migrations" not in _tables(conn):
            return False
        return conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (COLLECTION_SCHEMA_V3,)
        ).fetchone() is not None

    def _rebuild(self, conn: sqlite3.Connection, report: dict[str, Any]) -> None:
        existing = _tables(conn)
        required_legacy = {"collection_candidates", "collected_materials"}
        missing = sorted(required_legacy - existing)
        if missing:
            raise MigrationError(f"missing legacy tables: {', '.join(missing)}", report)

        snapshots = {
            table: _rows(conn, table)
            for table in (
                "collection_candidates",
                "collected_materials",
                "douyin_authors",
                "douyin_author_videos",
                "mxnzp_call_logs",
                "mxnzp_call_cache",
            )
        }
        report["before"] = {table: len(rows) for table, rows in snapshots.items()}

        resolved: dict[tuple[str, str], tuple[str, str]] = {}
        for table in ("collection_candidates", "collected_materials", "douyin_author_videos"):
            for row in snapshots[table]:
                work_id, evidence = extract_work_id(row)
                row_id = str(row.get("id") or row.get("source_key") or "")
                if not work_id:
                    report["unresolved"].append({"table": table, "row_id": row_id})
                else:
                    resolved[(table, row_id)] = (work_id, str(evidence))
        if report["unresolved"]:
            raise MigrationError("one or more legacy rows have no authoritative work id", report)

        author_ids = {
            str(row.get("sec_uid") or "").strip()
            for row in snapshots["douyin_authors"]
            if str(row.get("sec_uid") or "").strip()
        }
        author_ids.update(
            str(row.get("author_sec_uid") or "").strip()
            for row in snapshots["collected_materials"]
            if str(row.get("author_sec_uid") or "").strip()
        )
        report["expected"] = {
            "source_authors": len(author_ids),
            "source_works": len({value[0] for value in resolved.values()}),
            "source_observations": sum(
                len(snapshots[table])
                for table in ("collection_candidates", "collected_materials", "douyin_author_videos")
            ),
            "material_transcriptions": sum(
                1 for row in snapshots["collected_materials"] if str(row.get("transcript_text") or "").strip()
            ),
        }

        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.executescript(FINAL_SCHEMA)
            self._insert_authors(conn, snapshots)
            self._insert_works_and_observations(conn, snapshots, resolved)
            transcription_ids = self._insert_transcriptions(conn, snapshots["collected_materials"], resolved)
            self._insert_provider_history(conn, snapshots)
            self._insert_candidates(conn, snapshots["collection_candidates"], resolved)
            self._insert_materials(conn, snapshots["collected_materials"], resolved, transcription_ids)

            conn.execute("DROP TABLE collection_candidates")
            conn.execute("DROP TABLE collected_materials")
            conn.execute("ALTER TABLE collection_candidates_v3 RENAME TO collection_candidates")
            conn.execute("ALTER TABLE collected_materials_v3 RENAME TO collected_materials")
            for table in LEGACY_TABLES:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.executescript(
                """
                CREATE INDEX idx_source_works_author ON source_works(author_id);
                CREATE INDEX idx_source_observations_work ON source_observations(source_work_id, observed_at);
                CREATE INDEX idx_material_transcriptions_work ON material_transcriptions(source_work_id);
                CREATE INDEX idx_provider_call_logs_run ON provider_call_logs(run_id, created_at);
                CREATE INDEX idx_collection_candidates_run_id ON collection_candidates(run_id);
                CREATE INDEX idx_collection_candidates_status ON collection_candidates(status);
                CREATE INDEX idx_collected_materials_run_id ON collected_materials(run_id);
                CREATE INDEX idx_collected_materials_role_id ON collected_materials(role_id);
                """
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def _author_id(sec_uid: str) -> str:
        return f"srcauth:douyin:{sec_uid}"

    @staticmethod
    def _work_id(work_id: str) -> str:
        return f"srcwork:douyin:{work_id}"

    def _insert_authors(self, conn: sqlite3.Connection, snapshots: Mapping[str, list[dict[str, Any]]]) -> None:
        now = _now()
        profiles: dict[str, dict[str, Any]] = {}
        for row in snapshots["douyin_authors"]:
            sec_uid = str(row.get("sec_uid") or "").strip()
            if sec_uid:
                profiles[sec_uid] = row
        for row in snapshots["collected_materials"]:
            sec_uid = str(row.get("author_sec_uid") or "").strip()
            if sec_uid and sec_uid not in profiles:
                profiles[sec_uid] = {
                    "sec_uid": sec_uid,
                    "nickname": row.get("author_name"),
                    "douyin_id": row.get("author_douyin_id"),
                    "profile_url": row.get("author_profile_url"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
        for sec_uid, row in profiles.items():
            conn.execute(
                """
                INSERT INTO source_authors(
                    id, platform, platform_author_id, uid, account_id, display_name,
                    signature, avatar_url, profile_url, ip_location, follower_count,
                    following_count, work_count, total_favorited, raw_json,
                    first_seen_at, last_seen_at
                ) VALUES (?, 'douyin', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._author_id(sec_uid), sec_uid, row.get("uid"), row.get("douyin_id"),
                    row.get("nickname") or row.get("author_name"), row.get("signature"),
                    row.get("avatar_url"), row.get("profile_url") or row.get("author_profile_url"),
                    row.get("ip_location"), row.get("follower_count"), row.get("following_count"),
                    row.get("aweme_count"), row.get("total_favorited"),
                    _json_text(row.get("raw_json"), {}), row.get("created_at") or now,
                    row.get("updated_at") or row.get("fetched_at") or now,
                ),
            )

    def _insert_works_and_observations(
        self,
        conn: sqlite3.Connection,
        snapshots: Mapping[str, list[dict[str, Any]]],
        resolved: Mapping[tuple[str, str], tuple[str, str]],
    ) -> None:
        now = _now()
        seen: set[str] = set()
        author_by_work = {
            str(row.get("work_id")): str(row.get("author_sec_uid"))
            for row in snapshots["douyin_author_videos"]
            if row.get("work_id") and row.get("author_sec_uid")
        }
        for table in ("douyin_author_videos", "collected_materials", "collection_candidates"):
            for row in snapshots[table]:
                row_id = str(row.get("id") or row.get("source_key") or "")
                work_id, evidence = resolved[(table, row_id)]
                source_work_id = self._work_id(work_id)
                package = _json(row.get("source_package_json"), {})
                raw = _json(row.get("raw_json"), {})
                sec_uid = str(
                    row.get("author_sec_uid")
                    or (package.get("author_sec_uid") if isinstance(package, dict) else "")
                    or author_by_work.get(work_id)
                    or ""
                ).strip()
                author_id = self._author_id(sec_uid) if sec_uid else None
                if author_id and conn.execute("SELECT 1 FROM source_authors WHERE id = ?", (author_id,)).fetchone() is None:
                    author_id = None
                source_url = row.get("source_url")
                if not source_url and isinstance(package, dict):
                    source_url = package.get("source_link") or package.get("source_url")
                title = row.get("title")
                caption = row.get("caption_text") or row.get("platform_caption")
                created = row.get("created_at") or now
                updated = row.get("updated_at") or created
                if source_work_id not in seen:
                    conn.execute(
                        """
                        INSERT INTO source_works(
                            id, platform, platform_work_id, author_id, source_url, short_url,
                            title, caption_text, hashtags_json, published_at, duration_ms,
                            cover_url, raw_json, first_seen_at, last_seen_at
                        ) VALUES (?, 'douyin', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source_work_id, work_id, author_id, source_url, row.get("work_short_url"),
                            title, caption, _json_text(row.get("hashtags_json"), []), row.get("post_time"),
                            row.get("duration_ms"), row.get("cover_url"), _json_text(raw, {}), created, updated,
                        ),
                    )
                    seen.add(source_work_id)
                else:
                    conn.execute(
                        """
                        UPDATE source_works SET
                            author_id = COALESCE(author_id, ?), source_url = COALESCE(source_url, ?),
                            short_url = COALESCE(short_url, ?), title = COALESCE(title, ?),
                            caption_text = COALESCE(caption_text, ?), published_at = COALESCE(published_at, ?),
                            duration_ms = COALESCE(duration_ms, ?), cover_url = COALESCE(cover_url, ?),
                            last_seen_at = CASE WHEN last_seen_at > ? THEN last_seen_at ELSE ? END
                        WHERE id = ?
                        """,
                        (author_id, source_url, row.get("work_short_url"), title, caption, row.get("post_time"),
                         row.get("duration_ms"), row.get("cover_url"), updated, updated, source_work_id),
                    )
                metrics = row.get("metrics_json")
                if not metrics and isinstance(package, dict):
                    metrics = package.get("public_metrics")
                conn.execute(
                    """
                    INSERT INTO source_observations(
                        id, source_work_id, provider, observation_type, source_table,
                        source_row_id, metrics_json, payload_json, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"obs:{table}:{row_id}", source_work_id, "legacy-mxnzp",
                        "author_video" if table == "douyin_author_videos" else "collection",
                        table, row_id, _json_text(metrics, {}),
                        json.dumps({"identity_evidence": evidence}, ensure_ascii=False, sort_keys=True), updated,
                    ),
                )

    def _insert_transcriptions(
        self,
        conn: sqlite3.Connection,
        materials: list[dict[str, Any]],
        resolved: Mapping[tuple[str, str], tuple[str, str]],
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in materials:
            transcript = str(row.get("transcript_text") or "")
            if not transcript.strip():
                continue
            material_id = str(row["id"])
            work_id = resolved[("collected_materials", material_id)][0]
            transcription_id = f"transcript:legacy:{material_id}"
            identity_key = f"legacy:material:{material_id}"
            conn.execute(
                """
                INSERT INTO material_transcriptions(
                    id, source_work_id, identity_key, provider, model, transcript_text,
                    options_json, provider_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'legacy-mxnzp', 'unknown', ?, '{}', '{}', ?, ?)
                """,
                (transcription_id, self._work_id(work_id), identity_key, transcript,
                 row.get("created_at") or _now(), row.get("updated_at") or _now()),
            )
            result[material_id] = transcription_id
        return result

    @staticmethod
    def _insert_provider_history(conn: sqlite3.Connection, snapshots: Mapping[str, list[dict[str, Any]]]) -> None:
        for row in snapshots["mxnzp_call_logs"]:
            conn.execute(
                """
                INSERT INTO provider_call_logs(
                    id, run_id, provider, operation, request_fingerprint, status,
                    error, duration_ms, cache_hit, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["id"], row.get("run_id"), row.get("provider") or "mxnzp",
                 row.get("tool_name") or "unknown", row["request_fingerprint"], row["status"],
                 row.get("error"), row.get("duration_ms") or 0, row.get("cache_hit") or 0,
                 row.get("created_at") or _now()),
            )
        for row in snapshots["mxnzp_call_cache"]:
            conn.execute(
                """
                INSERT INTO provider_call_cache(
                    provider, request_fingerprint, operation, response_json,
                    created_at, updated_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row.get("provider") or "mxnzp", row["request_fingerprint"],
                 row.get("tool_name") or "unknown", row["response_json"],
                 row.get("created_at") or _now(), row.get("updated_at") or _now(),
                 row.get("hit_count") or 0),
            )

    def _insert_candidates(
        self,
        conn: sqlite3.Connection,
        rows: list[dict[str, Any]],
        resolved: Mapping[tuple[str, str], tuple[str, str]],
    ) -> None:
        for row in rows:
            row_id = str(row["id"])
            work_id = resolved[("collection_candidates", row_id)][0]
            conn.execute(
                """
                INSERT INTO collection_candidates_v3(
                    id, run_id, task_id, role_id, source_work_id, status,
                    selection_reason, skip_reason, skip_detail, threshold_mode,
                    material_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, row["run_id"], row.get("task_id"), row.get("role_id"), self._work_id(work_id),
                 row["status"], row.get("selection_reason"), row.get("skip_reason"),
                 row.get("skip_detail"), row.get("threshold_mode"), row.get("material_id"),
                 row["created_at"], row["updated_at"]),
            )

    def _insert_materials(
        self,
        conn: sqlite3.Connection,
        rows: list[dict[str, Any]],
        resolved: Mapping[tuple[str, str], tuple[str, str]],
        transcription_ids: Mapping[str, str],
    ) -> None:
        defaults: dict[str, Any] = {
            "content_structure_json": "[]",
            "key_points_json": "[]",
            "rewrite_angles_json": "[]",
            "usable_quotes_json": "[]",
            "risk_notes_json": "[]",
            "recommended_platforms_json": "[]",
            "next_collection_keywords_json": "[]",
            "material_eligibility_json": "{}",
            "eligibility_status": "accepted",
            "eligibility_provider": "local-rules",
            "eligibility_version": "material-eligibility-v1",
            "eligibility_reason_json": "[]",
            "knowledge_core_score": 0,
            "oral_script_fit_score": 0,
            "ip_fit_score": 0,
            "material_understanding_json": "{}",
            "understanding_provider": "codex-agent",
            "understanding_model": "unknown",
            "sample_pool_clues_json": "[]",
            "understanding_status": "pending",
            "status": "collected",
        }
        columns = [
            "id", "run_id", "task_id", "role_id", "source_role_id", "clean_title",
            "summary_text", "hook_text", "core_claim", "content_type", "oral_script_pattern",
            "audience", "emotion_trigger", "risk_level", "content_structure_json", "key_points_json",
            "rewrite_angles_json", "usable_quotes_json", "risk_notes_json", "recommended_platforms_json",
            "next_collection_keywords_json", "material_eligibility_json", "eligibility_status",
            "eligibility_provider", "eligibility_version", "eligibility_reason_json", "content_form",
            "knowledge_core_score", "oral_script_fit_score", "ip_fit_score", "reject_reason",
            "material_understanding_json", "understanding_provider", "understanding_model",
            "sample_pool_clues_json", "understanding_status", "status", "created_at", "updated_at",
        ]
        insert_columns = columns[:5] + ["source_work_id", "transcription_id"] + columns[5:]
        placeholders = ", ".join("?" for _ in insert_columns)
        sql = f"INSERT INTO collected_materials_v3({', '.join(insert_columns)}) VALUES ({placeholders})"
        for row in rows:
            material_id = str(row["id"])
            work_id = resolved[("collected_materials", material_id)][0]
            values = [row.get(column, defaults.get(column)) for column in columns[:5]]
            values.extend([self._work_id(work_id), transcription_ids.get(material_id)])
            values.extend(
                row.get(column) if row.get(column) is not None else defaults.get(column)
                for column in columns[5:]
            )
            conn.execute(sql, values)

    def _validate_final(self, conn: sqlite3.Connection, report: dict[str, Any]) -> None:
        conn.execute("PRAGMA foreign_keys = ON")
        tables = _tables(conn)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
        legacy_tables = sorted(tables & LEGACY_TABLES)
        missing_tables = sorted(REQUIRED_TABLES - tables)
        candidate_legacy_columns = sorted(_columns(conn, "collection_candidates") & LEGACY_CANDIDATE_COLUMNS)
        material_legacy_columns = sorted(_columns(conn, "collected_materials") & LEGACY_MATERIAL_COLUMNS)
        blank_identities = _count_where(conn, "material_transcriptions", "length(trim(identity_key)) = 0")
        duplicate_identities = int(conn.execute(
            "SELECT COUNT(*) FROM (SELECT identity_key FROM material_transcriptions GROUP BY identity_key HAVING COUNT(*) > 1)"
        ).fetchone()[0])

        before = report.get("before", {})
        after = {
            table: _count(conn, table)
            for table in (
                "collection_candidates", "collected_materials", "source_authors", "source_works",
                "source_observations", "material_transcriptions", "provider_call_logs", "provider_call_cache",
            )
            if table in tables
        }
        parity = {
            "collection_candidates": before.get("collection_candidates", after.get("collection_candidates")) == after.get("collection_candidates"),
            "collected_materials": before.get("collected_materials", after.get("collected_materials")) == after.get("collected_materials"),
            "provider_call_logs": before.get("mxnzp_call_logs", after.get("provider_call_logs")) == after.get("provider_call_logs"),
            "provider_call_cache": before.get("mxnzp_call_cache", after.get("provider_call_cache")) == after.get("provider_call_cache"),
        }
        for table, expected_count in report.get("expected", {}).items():
            parity[table] = expected_count == after.get(table)
        checks = {
            "integrity_check": integrity,
            "foreign_key_violations": foreign_keys,
            "legacy_tables": legacy_tables,
            "missing_required_tables": missing_tables,
            "legacy_candidate_columns": candidate_legacy_columns,
            "legacy_material_columns": material_legacy_columns,
            "blank_transcription_identities": blank_identities,
            "duplicate_transcription_identities": duplicate_identities,
            "row_parity": parity,
        }
        checks["passed"] = (
            integrity == "ok"
            and not foreign_keys
            and not legacy_tables
            and not missing_tables
            and not candidate_legacy_columns
            and not material_legacy_columns
            and blank_identities == 0
            and duplicate_identities == 0
            and all(parity.values())
            and not report.get("unresolved")
        )
        report["after"] = after
        report["checks"] = checks

    def _atomic_replace(self, destination: Path, recovery: Path) -> None:
        if recovery.exists():
            raise FileExistsError(recovery)
        if recovery.parent.resolve() != self.source_path.parent.resolve():
            raise ValueError("recovery_path must be in the source directory for atomic rollback")
        if destination.parent.resolve() != self.source_path.parent.resolve():
            raise ValueError("destination must be in the source directory for atomic replacement")
        recovery.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.source_path, recovery)
        try:
            os.replace(destination, self.source_path)
        except Exception:
            os.replace(recovery, self.source_path)
            raise

    @staticmethod
    def _update_migration_report(database: Path, report: Mapping[str, Any]) -> None:
        with sqlite3.connect(database) as conn:
            conn.execute(
                "UPDATE schema_migrations SET report_json = ? WHERE version = ?",
                (json.dumps(dict(report), ensure_ascii=False, sort_keys=True), COLLECTION_SCHEMA_V3),
            )
            conn.commit()


def _count_where(conn: sqlite3.Connection, table: str, where: str) -> int:
    if table not in _tables(conn):
        return -1
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {where}').fetchone()[0])


def migrate_collection_schema_v3(
    source_path: Path | str,
    destination_path: Path | str | None = None,
    *,
    replace: bool = False,
    recovery_path: Path | str | None = None,
) -> dict[str, Any]:
    """Public integration API; replacement is opt-in and requires a recovery path."""

    return CollectionSchemaV3Migrator(source_path).migrate(
        destination_path,
        replace=replace,
        recovery_path=recovery_path,
    )
