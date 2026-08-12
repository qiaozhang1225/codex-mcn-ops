from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .adb import AdbClient
from .adapters import list_platforms
from .collection.douyin.doctor import DoctorCheck, run_doctor
from .collection.douyin.direct.client import cookie_looks_authenticated
from .collection.douyin.factory import (
    build_collection_provider,
    build_data_provider,
    build_transcription_provider,
    load_local_env,
)
from .collection.douyin.registry import build_douyin_registry
from .collection.mock_tools import build_mock_source_registry
from .collection.runner import CollectionConfig, TopicCollectionRunner, engagement_score, metric_value
from .collection.tools import parse_json_object
from .collection.understanding import (
    DEFAULT_UNDERSTANDING_MODEL,
    DEFAULT_UNDERSTANDING_PROVIDER,
    build_material_understanding,
    evaluate_role_match,
    validate_understanding,
)
from .collection.workflows import (
    CollectionPolicy,
    CollectionTaskOrchestrator,
    format_task_report_markdown,
    format_task_show,
)
from .creation import (
    CREATION_STAGES,
    DEFAULT_CREATION_MODEL,
    DEFAULT_CREATION_PROVIDER,
    apply_learning_update,
    build_creation_context_packet,
    build_creation_task_report,
    confirm_creation_stage,
    create_creation_task,
    export_creation_task_markdown,
    format_creation_task_report_markdown,
    generate_learning_update_proposals,
    run_creation_stage,
)
from .feishu import build_publish_job_payload, write_payload
from .migrations import migrate_collection_schema_v3, migrate_material_inventory_v1
from .publisher import PublishRunner
from .report import build_daily_report
from .store import DEFAULT_DB_PATH, Store, loads


def json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _add_douyin_provider_args(parser: argparse.ArgumentParser, *, include_transcription: bool = False) -> None:
    parser.add_argument("--provider", choices=["direct"], default="direct")
    parser.set_defaults(allow_paid_fallback=False)
    if include_transcription:
        parser.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcn", description="Codex MCN Ops CLI")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--adb-path", default="adb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the SQLite ledger")

    db_parser = subparsers.add_parser("db", help="Database validation and explicit migrations")
    db_sub = db_parser.add_subparsers(dest="db_command", required=True)
    db_migrate_v3 = db_sub.add_parser(
        "migrate-collection-schema-v3",
        help="Rebuild the collection schema in a validated database copy",
    )
    db_migrate_v3.add_argument("--destination")
    db_migrate_v3.add_argument("--replace", action="store_true")
    db_migrate_v3.add_argument("--recovery-path")
    db_migrate_v3.add_argument("--json", action="store_true")
    db_migrate_inventory = db_sub.add_parser(
        "migrate-material-inventory-v1",
        help="Add the reviewed IP-role material inventory schema to an existing v3 database",
    )
    db_migrate_inventory.add_argument("--json", action="store_true")

    adb_parser = subparsers.add_parser("adb", help="ADB device utilities")
    adb_sub = adb_parser.add_subparsers(dest="adb_command", required=True)
    adb_sub.add_parser("devices", help="List connected Android devices")
    adb_doctor = adb_sub.add_parser("doctor", help="Check ADB and selected device")
    adb_doctor.add_argument("--device")

    content_parser = subparsers.add_parser("content", help="Content package utilities")
    content_sub = content_parser.add_subparsers(dest="content_command", required=True)
    create_content = content_sub.add_parser("create", help="Create a content package")
    create_content.add_argument("--title", required=True)
    create_content.add_argument("--body", required=True)
    create_content.add_argument("--media", action="append", default=[])
    create_content.add_argument("--cover")
    create_content.add_argument("--hashtag", action="append", default=[])
    create_content.add_argument("--json", action="store_true")

    create_parser = subparsers.add_parser("create", help="High-level creation workflow commands")
    create_sub = create_parser.add_subparsers(dest="create_command", required=True)

    create_task = create_sub.add_parser("task", help="Manage creation tasks")
    create_task_sub = create_task.add_subparsers(dest="create_task_command", required=True)
    create_task_new = create_task_sub.add_parser("new", help="Create a new IP creation task")
    create_task_new.add_argument("--role-id", required=True)
    create_task_new.add_argument("--topic", required=True)
    create_task_new.add_argument("--goal", required=True)
    create_task_new.add_argument("--platform", required=True, choices=list_platforms())
    create_task_new.add_argument("--target-count", type=int, default=1)
    create_task_new.add_argument("--provider", default=DEFAULT_CREATION_PROVIDER)
    create_task_new.add_argument("--model", default=DEFAULT_CREATION_MODEL)
    create_task_new.add_argument("--allow-reuse-material", action="store_true")
    create_task_new.add_argument("--json", action="store_true")
    create_task_run = create_task_sub.add_parser("run", help="Run one creation task stage")
    create_task_run.add_argument("--task-id", required=True)
    create_task_run.add_argument("--stage", required=True, choices=CREATION_STAGES)
    create_task_run.add_argument("--knowledge-root", default="knowledge")
    create_task_run.add_argument("--json", action="store_true")
    create_task_confirm = create_task_sub.add_parser("confirm", help="Confirm one creation task stage")
    create_task_confirm.add_argument("--task-id", required=True)
    create_task_confirm.add_argument("--stage", required=True, choices=CREATION_STAGES)
    create_task_confirm.add_argument("--json", action="store_true")
    create_task_retry = create_task_sub.add_parser("retry", help="Retry one creation task stage with a note")
    create_task_retry.add_argument("--task-id", required=True)
    create_task_retry.add_argument("--stage", required=True, choices=CREATION_STAGES)
    create_task_retry.add_argument("--note", required=True)
    create_task_retry.add_argument("--knowledge-root", default="knowledge")
    create_task_retry.add_argument("--json", action="store_true")
    create_task_report = create_task_sub.add_parser("report", help="Show a creation task report")
    create_task_report.add_argument("--task-id", required=True)
    create_task_report.add_argument("--json", action="store_true")
    create_task_export = create_task_sub.add_parser("export", help="Export a creation task as Markdown")
    create_task_export.add_argument("--task-id", required=True)
    create_task_export.add_argument("--format", choices=["markdown"], default="markdown")
    create_task_export.add_argument("--output")
    create_task_export.add_argument("--json", action="store_true")

    create_feedback = create_sub.add_parser("feedback", help="Record and analyze creation feedback")
    create_feedback_sub = create_feedback.add_subparsers(dest="create_feedback_command", required=True)
    create_feedback_add = create_feedback_sub.add_parser("add", help="Add one lightweight publish or stage feedback event")
    create_feedback_add.add_argument("--content-id")
    create_feedback_add.add_argument("--platform", required=True, choices=list_platforms())
    create_feedback_add.add_argument("--metrics-json", default="{}")
    create_feedback_add.add_argument("--notice", default="")
    create_feedback_add.add_argument("--human-note", default="")
    create_feedback_add.add_argument("--judgment", default="")
    create_feedback_add.add_argument("--task-id")
    create_feedback_add.add_argument("--role-id")
    create_feedback_add.add_argument("--stage", choices=CREATION_STAGES)
    create_feedback_add.add_argument("--json", action="store_true")
    create_feedback_analyze = create_feedback_sub.add_parser("analyze", help="Summarize feedback for one IP role")
    create_feedback_analyze.add_argument("--role-id", required=True)
    create_feedback_analyze.add_argument("--json", action="store_true")

    create_learning = create_sub.add_parser("learning", help="Manage Markdown learning update proposals")
    create_learning_sub = create_learning.add_subparsers(dest="create_learning_command", required=True)
    create_learning_propose = create_learning_sub.add_parser("propose", help="Propose Markdown learning updates")
    create_learning_propose.add_argument("--role-id", required=True)
    create_learning_propose.add_argument("--knowledge-root", default="knowledge")
    create_learning_propose.add_argument("--json", action="store_true")
    create_learning_apply = create_learning_sub.add_parser("apply", help="Apply one pending Markdown learning update")
    create_learning_apply.add_argument("--proposal-id", required=True)
    create_learning_apply.add_argument("--json", action="store_true")

    create_knowledge = create_sub.add_parser("knowledge", help="Inspect creation knowledge packets")
    create_knowledge_sub = create_knowledge.add_subparsers(dest="create_knowledge_command", required=True)
    create_knowledge_packet = create_knowledge_sub.add_parser("packet", help="Show the context packet for a creation task")
    create_knowledge_packet.add_argument("--task-id", required=True)
    create_knowledge_packet.add_argument("--knowledge-root", default="knowledge")
    create_knowledge_packet.add_argument("--include-transcript", action="store_true")
    create_knowledge_packet.add_argument("--json", action="store_true")

    collect_parser = subparsers.add_parser("collect", help="Material collection commands")
    collect_sub = collect_parser.add_subparsers(dest="collect_command", required=True)

    douyin = collect_sub.add_parser("douyin", help="Use provider-neutral Douyin data and transcription commands")
    douyin_sub = douyin.add_subparsers(dest="douyin_command", required=True)
    douyin_doctor = douyin_sub.add_parser("doctor", help="Check Direct Douyin and transcription configuration")
    _add_douyin_provider_args(douyin_doctor, include_transcription=True)
    douyin_doctor.add_argument("--json", action="store_true")
    douyin_detail = douyin_sub.add_parser("detail", help="Fetch one Douyin video detail")
    douyin_detail.add_argument("url")
    _add_douyin_provider_args(douyin_detail)
    douyin_detail.add_argument("--no-cache", action="store_true")
    douyin_detail.add_argument("--json", action="store_true")
    douyin_search_video = douyin_sub.add_parser("search-video", help="Search Douyin videos")
    douyin_search_video.add_argument("--keyword", required=True)
    douyin_search_video.add_argument("--offset", default="0")
    douyin_search_video.add_argument("--search-id", default="")
    douyin_search_video.add_argument("--max-pages", type=int, default=1)
    douyin_search_video.add_argument("--max-items", type=int, default=0)
    _add_douyin_provider_args(douyin_search_video)
    douyin_search_video.add_argument("--no-cache", action="store_true")
    douyin_search_video.add_argument("--json", action="store_true")
    douyin_search_user = douyin_sub.add_parser("search-user", help="Search Douyin users")
    douyin_search_user.add_argument("--keyword", required=True)
    douyin_search_user.add_argument("--offset", default="0")
    douyin_search_user.add_argument("--search-id", default="")
    _add_douyin_provider_args(douyin_search_user)
    douyin_search_user.add_argument("--no-cache", action="store_true")
    douyin_search_user.add_argument("--json", action="store_true")
    douyin_user_posts = douyin_sub.add_parser("user-posts", help="Fetch one Douyin user's posted videos")
    douyin_user_posts.add_argument("--sec-uid", required=True)
    douyin_user_posts.add_argument("--cursor", default="0")
    douyin_user_posts.add_argument("--sort-type", type=int, choices=[0, 1], default=0)
    douyin_user_posts.add_argument("--max-pages", type=int, default=1)
    douyin_user_posts.add_argument("--max-items", type=int, default=0)
    _add_douyin_provider_args(douyin_user_posts)
    douyin_user_posts.add_argument("--no-cache", action="store_true")
    douyin_user_posts.add_argument("--json", action="store_true")
    douyin_transcribe = douyin_sub.add_parser("transcribe", help="Transcribe one Douyin video's spoken copy")
    douyin_transcribe.add_argument("url")
    _add_douyin_provider_args(douyin_transcribe, include_transcription=True)
    douyin_transcribe.add_argument("--no-cache", action="store_true")
    douyin_transcribe.add_argument("--json", action="store_true")

    task = collect_sub.add_parser("task", help="Run high-level material collection tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_keyword = task_sub.add_parser("keyword", help="Collect enough materials for one topic")
    task_keyword.add_argument("--topic", required=True)
    task_keyword.add_argument("--target-count", type=int, required=True)
    task_keyword.add_argument("--keyword", action="append", default=[])
    task_keyword.add_argument("--related-keyword", action="append", default=[])
    task_keyword.add_argument("--role-id")
    task_keyword.add_argument("--role-name")
    task_keyword.add_argument(
        "--data-provider",
        "--tool-provider",
        dest="data_provider",
        choices=["mock", "direct"],
        default="direct",
    )
    task_keyword.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")
    task_keyword.set_defaults(allow_paid_fallback=False)
    task_keyword.add_argument("--like-floor", type=int, default=10000)
    task_keyword.add_argument("--min-duration-seconds", type=int, default=20)
    task_keyword.add_argument("--max-duration-seconds", type=int, default=300)
    task_keyword.add_argument("--max-search-pages", type=int, default=3)
    task_keyword.add_argument("--page-size", type=int, default=10)
    task_keyword.add_argument("--understanding-provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    task_keyword.add_argument("--understanding-model", default=DEFAULT_UNDERSTANDING_MODEL)
    task_keyword.add_argument("--json", action="store_true")

    task_author = task_sub.add_parser("author", help="Collect viral materials from one source author")
    task_author.add_argument("--sec-uid")
    task_author.add_argument("--name")
    task_author.add_argument("--like-floor", type=int, default=10000)
    task_author.add_argument("--min-duration-seconds", type=int, default=20)
    task_author.add_argument("--max-duration-seconds", type=int, default=300)
    task_author.add_argument("--materialize-top", type=int, default=0, help="Use 0 to materialize every qualified viral video")
    task_author.add_argument("--max-pages", type=int, default=0, help="Use 0 to continue until the provider reports no next page")
    task_author.add_argument("--sort-type", type=int, choices=[0, 1], default=1)
    task_author.add_argument("--skip-expand", action="store_true")
    task_author.add_argument("--refresh-existing-understanding", action="store_true")
    task_author.add_argument("--understanding-provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    task_author.add_argument("--understanding-model", default=DEFAULT_UNDERSTANDING_MODEL)
    task_author.add_argument("--no-cache", action="store_true")
    task_author.add_argument("--json", action="store_true")
    task_author.add_argument("--data-provider", choices=["direct"], default="direct")
    task_author.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")
    task_author.set_defaults(allow_paid_fallback=False)

    task_discover = task_sub.add_parser("discover-authors", help="Discover source authors from the database and collect their viral works")
    task_discover.add_argument("--min-appearances", type=int, default=2)
    task_discover.add_argument("--top-authors", type=int, default=10)
    task_discover.add_argument("--like-floor", type=int, default=10000)
    task_discover.add_argument("--min-duration-seconds", type=int, default=20)
    task_discover.add_argument("--max-duration-seconds", type=int, default=300)
    task_discover.add_argument("--materialize-top", type=int, default=0, help="Use 0 to materialize every qualified viral video per author")
    task_discover.add_argument("--max-pages", type=int, default=0)
    task_discover.add_argument("--sort-type", type=int, choices=[0, 1], default=1)
    task_discover.add_argument("--skip-expand", action="store_true")
    task_discover.add_argument("--no-cache", action="store_true")
    task_discover.add_argument("--dry-run", action="store_true")
    task_discover.add_argument("--understanding-provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    task_discover.add_argument("--understanding-model", default=DEFAULT_UNDERSTANDING_MODEL)
    task_discover.add_argument("--json", action="store_true")
    task_discover.add_argument("--data-provider", choices=["direct"], default="direct")
    task_discover.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")
    task_discover.set_defaults(allow_paid_fallback=False)

    task_show = task_sub.add_parser("show", help="Show a collection task summary")
    task_show.add_argument("--task-id", required=True)
    task_show.add_argument("--json", action="store_true")
    task_report = task_sub.add_parser("report", help="Write a collection task report")
    task_report.add_argument("--task-id", required=True)
    task_report.add_argument("--json", action="store_true")
    task_resume = task_sub.add_parser("resume", help="Resume a collection task from stored task parameters")
    task_resume.add_argument("--task-id", required=True)
    task_resume.add_argument("--json", action="store_true")

    author = collect_sub.add_parser("author", help="Manage Douyin source authors")
    author_sub = author.add_subparsers(dest="author_command", required=True)
    author_list = author_sub.add_parser("list", help="List stored Douyin authors")
    author_list.add_argument("--json", action="store_true")
    author_videos = author_sub.add_parser("videos", help="List and rank stored videos for one Douyin author")
    author_videos.add_argument("--sec-uid")
    author_videos.add_argument("--name")
    author_videos.add_argument("--like-floor", type=int, default=5000)
    author_videos.add_argument("--min-duration-seconds", type=int, default=20)
    author_videos.add_argument("--max-duration-seconds", type=int, default=300)
    author_videos.add_argument("--top", type=int, default=20)
    author_videos.add_argument("--json", action="store_true")
    author_expand = author_sub.add_parser("expand", help="Fetch posted videos for one Douyin author and rank viral works")
    author_expand.add_argument("--sec-uid")
    author_expand.add_argument("--name")
    author_expand.add_argument("--cursor", default="")
    author_expand.add_argument("--sort-type", type=int, choices=[0, 1], default=1)
    author_expand.add_argument("--max-pages", type=int, default=20, help="Use 0 to continue until the provider reports no next page")
    author_expand.add_argument("--like-floor", type=int, default=5000)
    author_expand.add_argument("--min-duration-seconds", type=int, default=20)
    author_expand.add_argument("--max-duration-seconds", type=int, default=300)
    author_expand.add_argument("--top", type=int, default=20)
    author_expand.add_argument("--stop-after-nonviral-pages", type=int, default=2, help="Use 0 to disable early stop")
    author_expand.add_argument("--no-cache", action="store_true")
    author_expand.add_argument("--json", action="store_true")
    author_expand.add_argument("--data-provider", choices=["direct"], default="direct")
    author_expand.set_defaults(allow_paid_fallback=False)
    author_materialize = author_sub.add_parser(
        "materialize",
        help="Transcribe ranked author videos into collected materials and run material understanding",
    )
    author_materialize.add_argument("--sec-uid")
    author_materialize.add_argument("--name")
    author_materialize.add_argument("--topic")
    author_materialize.add_argument("--top", type=int, default=5)
    author_materialize.add_argument("--like-floor", type=int, default=5000)
    author_materialize.add_argument("--min-duration-seconds", type=int, default=20)
    author_materialize.add_argument("--max-duration-seconds", type=int, default=300)
    author_materialize.add_argument("--provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    author_materialize.add_argument("--model", default=DEFAULT_UNDERSTANDING_MODEL)
    author_materialize.add_argument("--duplicate-existing", action="store_true")
    author_materialize.add_argument("--refresh-existing-understanding", action="store_true")
    author_materialize.add_argument("--no-cache", action="store_true")
    author_materialize.add_argument("--json", action="store_true")
    author_materialize.add_argument("--data-provider", choices=["direct"], default="direct")
    author_materialize.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")
    author_materialize.set_defaults(allow_paid_fallback=False)

    role = collect_sub.add_parser("role", help="Manage IP role profiles")
    role_sub = role.add_subparsers(dest="role_command", required=True)
    role_upsert = role_sub.add_parser("upsert", help="Create or update an IP role")
    role_upsert.add_argument("--name")
    role_upsert.add_argument("--file", help="Read one complete role profile JSON file")
    role_upsert.add_argument("--positioning", default="")
    role_upsert.add_argument("--target-direction", action="append", default=[])
    role_upsert.add_argument("--search-keyword", action="append", default=[])
    role_upsert.add_argument("--avoid-direction", action="append", default=[])
    role_upsert.add_argument("--preferred-content", action="append", default=[])
    role_upsert.add_argument("--forbidden-content", action="append", default=[])
    role_upsert.add_argument("--disabled", action="store_true")
    role_upsert.add_argument("--json", action="store_true")
    role_list = role_sub.add_parser("list", help="List IP roles")
    role_list.add_argument("--enabled-only", action="store_true")
    role_list.add_argument("--confirmed-only", action="store_true")
    role_list.add_argument("--json", action="store_true")
    role_show = role_sub.add_parser("show", help="Show one IP role")
    role_show.add_argument("--role-id")
    role_show.add_argument("--name")
    role_show.add_argument("--json", action="store_true")
    role_import = role_sub.add_parser("import", help="Import roles from a JSON file")
    role_import.add_argument("--file", required=True)
    role_import.add_argument("--json", action="store_true")
    role_export = role_sub.add_parser("export", help="Export complete IP role profiles")
    role_export.add_argument("--file", required=True)
    role_export.add_argument("--json", action="store_true")
    role_confirm = role_sub.add_parser("confirm", help="Confirm one IP role profile and snapshot its version")
    role_confirm.add_argument("--role-id", required=True)
    role_confirm.add_argument("--change-reason", default="")
    role_confirm.add_argument("--json", action="store_true")
    role_packet = role_sub.add_parser("packet", help="Build and show one IP role persona packet")
    role_packet.add_argument("--role-id")
    role_packet.add_argument("--name")
    role_packet.add_argument("--json", action="store_true")
    role_match = role_sub.add_parser("match-existing", help="Match existing materials against one IP role")
    role_match.add_argument("--role-id", required=True)
    role_match.add_argument("--task-id")
    role_match.add_argument("--json", action="store_true")

    collect_run = collect_sub.add_parser("run", help="Run topic material collection")
    collect_run.add_argument("--topic", required=True)
    collect_run.add_argument("--target-count", type=int, default=3)
    collect_run.add_argument("--like-floor", type=int, default=5000)
    collect_run.add_argument("--super-like-threshold", type=int, default=100000)
    collect_run.add_argument("--min-duration-seconds", type=int, default=20)
    collect_run.add_argument("--max-duration-seconds", type=int, default=300)
    collect_run.add_argument(
        "--data-provider",
        "--tool-provider",
        dest="data_provider",
        choices=["mock", "direct"],
        default="direct",
    )
    collect_run.add_argument("--transcription-provider", choices=["aliyun", "none"], default="aliyun")
    collect_run.set_defaults(allow_paid_fallback=False)
    collect_run.add_argument("--max-search-pages", type=int, default=3)
    collect_run.add_argument("--page-size", type=int, default=5)
    collect_run.add_argument("--role-id")
    collect_run.add_argument("--search-keyword", action="append", default=[])
    collect_run.add_argument("--understanding-provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    collect_run.add_argument("--understanding-model", default=DEFAULT_UNDERSTANDING_MODEL)
    collect_run.add_argument("--json", action="store_true")

    understand = collect_sub.add_parser("understand", help="Write Codex material understanding JSON")
    understand.add_argument("--run-id")
    understand.add_argument("--material-id")
    understand.add_argument("--role-id", action="append", default=[])
    understand.add_argument("--skip-role-match", action="store_true")
    understand.add_argument("--provider", default=DEFAULT_UNDERSTANDING_PROVIDER)
    understand.add_argument("--model", default=DEFAULT_UNDERSTANDING_MODEL)
    understand.add_argument("--json", action="store_true")

    match = collect_sub.add_parser("match", help="Match materials against IP roles")
    match.add_argument("--run-id")
    match.add_argument("--material-id")
    match.add_argument("--role-id")
    match.add_argument("--task-id")
    match.add_argument("--json", action="store_true")

    collect_report = collect_sub.add_parser("report", help="Build a collection run report")
    collect_report.add_argument("--run-id", required=True)
    collect_report.add_argument("--json", action="store_true")

    material_parser = subparsers.add_parser("material", help="Collected material commands")
    material_sub = material_parser.add_subparsers(dest="material_command", required=True)
    material_list = material_sub.add_parser("list", help="List collected materials")
    material_list.add_argument("--run-id")
    material_list.add_argument("--role-id")
    material_list.add_argument("--status")
    material_list.add_argument("--json", action="store_true")
    material_show = material_sub.add_parser("show", help="Show one collected material")
    material_show.add_argument("--material-id", required=True)
    material_show.add_argument("--json", action="store_true")
    material_creations = material_sub.add_parser("creations", help="List material creation records")
    material_creations.add_argument("--material-id")
    material_creations.add_argument("--role-id")
    material_creations.add_argument("--content-id")
    material_creations.add_argument("--json", action="store_true")
    material_promote = material_sub.add_parser("promote", help="Promote material to a content package")
    material_promote.add_argument("--material-id", required=True)
    material_promote.add_argument("--platform", required=True, choices=list_platforms())
    material_promote.add_argument("--role-id")
    material_promote.add_argument("--task-id")
    material_promote.add_argument("--rewrite-angle")
    material_promote.add_argument("--title")
    material_promote.add_argument("--body")
    material_promote.add_argument("--hashtag", action="append", default=[])
    material_promote.add_argument("--json", action="store_true")
    material_inventory = material_sub.add_parser("inventory", help="Manage reviewed IP-role material inventory")
    material_inventory_sub = material_inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_classify = material_inventory_sub.add_parser("classify", help="Classify one material for one confirmed IP role")
    inventory_classify.add_argument("--material-id", required=True)
    inventory_classify.add_argument("--role-id", required=True)
    inventory_classify.add_argument("--topic-direction", required=True)
    inventory_classify.add_argument("--content-mechanism", required=True)
    inventory_classify.add_argument("--knowledge-subtype")
    inventory_classify.add_argument("--material-class", required=True, choices=["formal_rewrite_base", "topic_clue"])
    inventory_classify.add_argument("--primary", action="store_true", help="Use this topic as the material's only primary allocation topic")
    inventory_classify.add_argument("--review-status", required=True, choices=["pending", "reviewed", "rejected"])
    inventory_classify.add_argument("--reviewer")
    inventory_classify.add_argument("--decision-source", required=True)
    inventory_classify.add_argument("--reason", action="append", required=True)
    inventory_classify.add_argument("--json", action="store_true")
    inventory_import = material_inventory_sub.add_parser("import", help="Transactionally import reviewed classifications from JSON")
    inventory_import.add_argument("--role-id", required=True)
    inventory_import.add_argument("--file", required=True)
    inventory_import.add_argument("--json", action="store_true")
    inventory_list = material_inventory_sub.add_parser("list", help="List classified materials for one role")
    inventory_list.add_argument("--role-id", required=True)
    inventory_list.add_argument("--topic-direction")
    inventory_list.add_argument("--material-class", choices=["formal_rewrite_base", "topic_clue"])
    inventory_list.add_argument("--review-status", choices=["pending", "reviewed", "rejected"])
    inventory_list.add_argument("--include-used", action="store_true")
    inventory_list.add_argument("--json", action="store_true")
    inventory_pending = material_inventory_sub.add_parser("pending", help="List distinct accepted source works still awaiting inventory review")
    inventory_pending.add_argument("--role-id", required=True)
    inventory_pending.add_argument("--include-used", action="store_true")
    inventory_pending.add_argument("--include-pending", action="store_true")
    inventory_pending.add_argument("--include-rejected", action="store_true")
    inventory_pending.add_argument("--task-id")
    inventory_pending.add_argument("--run-id")
    inventory_pending.add_argument("--json", action="store_true")
    inventory_summary = material_inventory_sub.add_parser("summary", help="Summarize usable inventory and allocation shortages")
    inventory_summary.add_argument("--role-id", required=True)
    inventory_summary.add_argument("--allocation-file")
    inventory_summary.add_argument("--include-used", action="store_true")
    inventory_summary.add_argument("--json", action="store_true")

    publish_parser = subparsers.add_parser("publish", help="Publish workflow commands")
    publish_sub = publish_parser.add_subparsers(dest="publish_command", required=True)

    prepare = publish_sub.add_parser("prepare", help="Create a publish job for content")
    prepare.add_argument("--content-id", required=True)
    prepare.add_argument("--platform", required=True, choices=list_platforms())
    prepare.add_argument("--device")
    prepare.add_argument("--allow-submit", action="store_true", help="Default is stop before submit")
    prepare.add_argument("--json", action="store_true")

    push_assets = publish_sub.add_parser("push-assets", help="Push job media files to the selected phone")
    push_assets.add_argument("--job-id", required=True)
    push_assets.add_argument("--remote-dir", default="/sdcard/Download/codex-mcn-ops")
    push_assets.add_argument("--json", action="store_true")

    run = publish_sub.add_parser("run", help="Run an ADB publish job")
    run.add_argument("--job-id", required=True)
    run.add_argument("--device")
    run.add_argument("--platform", choices=list_platforms())
    run.add_argument("--dry-run", action="store_true", help="Plan the adapter steps without touching the phone")
    run.add_argument("--live", action="store_true", help="Allow final publish checkpoint when stop-before-submit is disabled")
    run.add_argument("--stop-before-submit", action="store_true", default=True)
    run.add_argument("--allow-submit", action="store_true")
    run.add_argument("--json", action="store_true")

    verify = publish_sub.add_parser("verify", help="Record a manual publish verification snapshot")
    verify.add_argument("--job-id", required=True)
    verify.add_argument("--result-url")
    verify.add_argument("--metric", action="append", default=[], help="key=value")
    verify.add_argument("--source", default="manual")
    verify.add_argument("--json", action="store_true")

    feishu = publish_sub.add_parser("feishu-payload", help="Write a Feishu sync payload for a job")
    feishu.add_argument("--job-id", required=True)
    feishu.add_argument("--output", required=True)

    subparsers.add_parser("platforms", help="List supported V1 platforms")

    report_parser = subparsers.add_parser("report", help="Reporting commands")
    report_sub = report_parser.add_subparsers(dest="report_command", required=True)
    daily = report_sub.add_parser("daily", help="Generate a daily Markdown report")
    daily.add_argument("--date")
    daily.add_argument("--output")
    return parser


def handle_init_db(store: Store) -> int:
    path = store.init_db()
    print(f"Initialized SQLite ledger at {path}")
    return 0


def handle_adb(args: argparse.Namespace) -> int:
    client = AdbClient(args.adb_path, getattr(args, "device", None))
    if args.adb_command == "devices":
        devices = client.devices()
        json_print([device.__dict__ for device in devices])
        return 0
    if args.adb_command == "doctor":
        json_print(client.doctor())
        return 0
    raise ValueError(args.adb_command)


def handle_content(args: argparse.Namespace, store: Store) -> int:
    if args.content_command == "create":
        content_id = store.create_content_package(
            title=args.title,
            body=args.body,
            media_paths=args.media,
            cover_path=args.cover,
            hashtags=args.hashtag,
        )
        if args.json:
            json_print({"content_id": content_id})
        else:
            print(content_id)
        return 0
    raise ValueError(args.content_command)


def handle_create(args: argparse.Namespace, store: Store) -> int:
    if args.create_command == "task":
        if args.create_task_command == "new":
            report = create_creation_task(
                store,
                role_id=args.role_id,
                topic=args.topic,
                goal=args.goal,
                platform=args.platform,
                target_count=args.target_count,
                provider=args.provider,
                model=args.model,
                allow_reuse_material=args.allow_reuse_material,
            )
            if args.json:
                json_print(report)
            else:
                print(report["task"]["id"])
            return 0

        if args.create_task_command == "run":
            result = run_creation_stage(
                store,
                args.task_id,
                stage_key=args.stage,
                knowledge_root=Path(args.knowledge_root),
            )
            if args.json:
                json_print(result)
            else:
                print(result["stage_run"]["id"])
            return 0

        if args.create_task_command == "confirm":
            report = confirm_creation_stage(store, args.task_id, stage_key=args.stage)
            if args.json:
                json_print(report)
            else:
                print(f"{args.task_id}\t{args.stage}\tconfirmed")
            return 0

        if args.create_task_command == "retry":
            result = run_creation_stage(
                store,
                args.task_id,
                stage_key=args.stage,
                knowledge_root=Path(args.knowledge_root),
                note=args.note,
            )
            if args.json:
                json_print(result)
            else:
                print(result["stage_run"]["id"])
            return 0

        if args.create_task_command == "report":
            report = build_creation_task_report(store, args.task_id)
            if args.json:
                json_print(report)
            else:
                print(format_creation_task_report_markdown(report))
            return 0

        if args.create_task_command == "export":
            markdown = export_creation_task_markdown(store, args.task_id)
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(markdown, encoding="utf-8")
                if args.json:
                    json_print({"file": str(output), "task_id": args.task_id})
                else:
                    print(output)
            elif args.json:
                json_print({"task_id": args.task_id, "markdown": markdown})
            else:
                print(markdown, end="")
            return 0

    if args.create_command == "feedback":
        if args.create_feedback_command == "add":
            metrics = parse_json_object(args.metrics_json)
            role_id = args.role_id
            task_id = args.task_id
            if args.content_id and (not role_id or not task_id):
                inferred = _infer_creation_from_content(store, args.content_id)
                role_id = role_id or inferred.get("role_id")
                task_id = task_id or inferred.get("task_id")
            if args.content_id:
                feedback_id = store.insert_creation_feedback_event(
                    content_package_id=args.content_id,
                    task_id=task_id,
                    role_id=role_id,
                    platform=args.platform,
                    metrics=metrics,
                    notice=args.notice,
                    human_note=args.human_note,
                    judgment=args.judgment,
                )
                payload = {"feedback_id": feedback_id, "feedback_type": "publish", "role_id": role_id, "task_id": task_id}
            else:
                if not task_id or not role_id or not args.stage:
                    raise ValueError("stage feedback requires --task-id, --role-id, and --stage when --content-id is omitted")
                feedback_id = store.insert_creation_stage_feedback_event(
                    task_id=task_id,
                    role_id=role_id,
                    stage_key=args.stage,
                    platform=args.platform,
                    human_note=args.human_note or args.notice,
                    judgment=args.judgment,
                    metadata={"metrics": metrics, "notice": args.notice},
                )
                payload = {"feedback_id": feedback_id, "feedback_type": "stage", "role_id": role_id, "task_id": task_id, "stage": args.stage}
            if args.json:
                json_print(payload)
            else:
                print(feedback_id)
            return 0

        if args.create_feedback_command == "analyze":
            events = store.list_creation_feedback_events(role_id=args.role_id)
            stage_events = store.list_creation_stage_feedback_events(role_id=args.role_id)
            observations = store.list_risk_term_observations(role_id=args.role_id)
            payload = {
                "role_id": args.role_id,
                "feedback_count": len(events),
                "stage_feedback_count": len(stage_events),
                "risk_observation_count": len(observations),
                "recent_feedback": events[:10],
                "recent_stage_feedback": stage_events[:10],
                "risk_terms": sorted({item["term"] for item in observations}),
            }
            if args.json:
                json_print(payload)
            else:
                print(f"feedback={payload['feedback_count']} stage_feedback={payload['stage_feedback_count']} risk_terms={len(payload['risk_terms'])}")
                for term in payload["risk_terms"]:
                    print(term)
            return 0

    if args.create_command == "learning":
        if args.create_learning_command == "propose":
            result = generate_learning_update_proposals(
                store,
                role_id=args.role_id,
                knowledge_root=Path(args.knowledge_root),
            )
            if args.json:
                json_print(result)
            else:
                print(result["update_id"])
            return 0

        if args.create_learning_command == "apply":
            result = apply_learning_update(store, args.proposal_id)
            if args.json:
                json_print(result)
            else:
                print(result["id"])
            return 0

    if args.create_command == "knowledge":
        if args.create_knowledge_command == "packet":
            packet = build_creation_context_packet(
                store,
                args.task_id,
                knowledge_root=Path(args.knowledge_root),
                include_transcript=args.include_transcript,
            )
            if args.json:
                json_print(packet)
            else:
                print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

    raise ValueError(args.create_command)


def handle_publish(args: argparse.Namespace, store: Store) -> int:
    if args.publish_command == "prepare":
        job_id = store.create_publish_job(
            content_id=args.content_id,
            platform=args.platform,
            device_serial=args.device,
            stop_before_submit=not args.allow_submit,
        )
        payload = {"job_id": job_id, "stop_before_submit": not args.allow_submit}
        if args.json:
            json_print(payload)
        else:
            print(job_id)
        return 0

    if args.publish_command == "push-assets":
        runner = PublishRunner(store, adb_path=args.adb_path)
        pushed = runner.prepare_assets(args.job_id, remote_dir=args.remote_dir)
        if args.json:
            json_print({"job_id": args.job_id, "remote_paths": pushed})
        else:
            print("\n".join(pushed))
        return 0

    if args.publish_command == "run":
        if args.device:
            job = store.get_publish_job(args.job_id)
            with store.connect() as conn:
                conn.execute(
                    "UPDATE publish_jobs SET device_serial = ?, updated_at = datetime('now') WHERE id = ?",
                    (args.device, args.job_id),
                )
        if args.platform:
            job = store.get_publish_job(args.job_id)
            if job["platform"] != args.platform:
                raise ValueError(f"job platform is {job['platform']}, not {args.platform}")
        runner = PublishRunner(store, adb_path=args.adb_path)
        stop_before_submit = False if args.allow_submit else True
        result = runner.run_job(
            args.job_id,
            dry_run=args.dry_run,
            stop_before_submit=stop_before_submit,
            live_publish=args.live,
        )
        payload = {
            "job_id": result.job_id,
            "status": result.status,
            "run_dir": str(result.run_dir),
            "message": result.message,
        }
        if args.json:
            json_print(payload)
        else:
            print(result.message)
        return 0

    if args.publish_command == "verify":
        metrics: dict[str, Any] = {}
        for item in args.metric:
            if "=" not in item:
                raise ValueError(f"metric must be key=value: {item}")
            key, value = item.split("=", 1)
            metrics[key] = value
        job = store.get_publish_job(args.job_id)
        snapshot_id = store.add_tracking_snapshot(
            publish_job_id=args.job_id,
            platform=job["platform"],
            result_url=args.result_url,
            metrics=metrics,
            source=args.source,
        )
        store.update_publish_job_status(args.job_id, "verified")
        if args.json:
            json_print({"snapshot_id": snapshot_id})
        else:
            print(snapshot_id)
        return 0

    if args.publish_command == "feishu-payload":
        job, content = store.get_job_with_content(args.job_id)
        payload = build_publish_job_payload(dict(job), dict(content))
        path = write_payload(payload, Path(args.output))
        print(path)
        return 0

    raise ValueError(args.publish_command)


def handle_collect(args: argparse.Namespace, store: Store) -> int:
    if args.collect_command == "douyin":
        return handle_collect_douyin(args)

    if args.collect_command == "task":
        return handle_collect_task(args, store)

    if args.collect_command == "author":
        return handle_collect_author(args, store)

    if args.collect_command == "role":
        return handle_collect_role(args, store)

    if args.collect_command == "run":
        role_profile = store.get_ip_role(args.role_id) if args.role_id else None
        tools = _build_collection_tools(
            args.data_provider,
            transcription_provider=args.transcription_provider,
            allow_paid_fallback=args.allow_paid_fallback,
        )
        runner = TopicCollectionRunner(tools, store)
        result = runner.run(
            CollectionConfig(
                topic=args.topic,
                target_count=args.target_count,
                like_floor=args.like_floor,
                super_like_threshold=args.super_like_threshold,
                min_duration_seconds=args.min_duration_seconds,
                max_duration_seconds=args.max_duration_seconds,
                tool_provider=args.data_provider,
                max_search_pages=args.max_search_pages,
                page_size=args.page_size,
                role_id=args.role_id,
                role_profile=role_profile,
                search_keywords=args.search_keyword,
                understanding_provider=args.understanding_provider,
                understanding_model=args.understanding_model,
            )
        )
        if args.json:
            json_print(result.to_dict())
        else:
            print(result.run_id)
        return 0

    if args.collect_command == "understand":
        materials = _select_materials(store, run_id=args.run_id, material_id=args.material_id)
        updated: list[dict[str, Any]] = []
        matches: list[dict[str, Any]] = []
        for material in materials:
            understanding = build_material_understanding(material, provider=args.provider, model=args.model)
            validate_understanding(understanding)
            store.update_material_understanding(
                material["id"],
                understanding=understanding,
                provider=args.provider,
                model=args.model,
            )
            store.log_material_understanding(
                run_id=material.get("run_id"),
                material_id=material["id"],
                provider=args.provider,
                model=args.model,
                status="ok",
                output=understanding,
            )
            updated.append({"material_id": material["id"], "topic_summary": understanding["topic_summary"]})
            refreshed = store.get_collected_material(material["id"]) or material
            if not args.skip_role_match:
                matches.extend(
                    _match_material_to_roles(
                        store,
                        refreshed,
                        role_ids=args.role_id,
                        task_id=refreshed.get("task_id"),
                    )
                )
        if args.json:
            json_print({"updated": updated, "matches": matches})
        else:
            print("\n".join(item["material_id"] for item in updated))
        return 0

    if args.collect_command == "match":
        materials = _select_materials(store, run_id=args.run_id, material_id=args.material_id)
        matches: list[dict[str, Any]] = []
        for material in materials:
            matches.extend(
                _match_material_to_roles(
                    store,
                    material,
                    role_ids=[args.role_id] if args.role_id else [],
                    task_id=args.task_id or material.get("task_id"),
                )
            )
        if args.json:
            json_print({"matches": matches})
        else:
            print("\n".join(item["match_id"] for item in matches))
        return 0

    if args.collect_command == "report":
        report = store.build_collection_report(args.run_id)
        if args.json:
            json_print(report)
        else:
            print(_format_collection_report(report))
        return 0

    raise ValueError(args.collect_command)


def handle_collect_douyin(args: argparse.Namespace) -> int:
    load_local_env()
    if args.douyin_command == "doctor":
        provider = build_data_provider(args.provider, allow_paid_fallback=args.allow_paid_fallback)
        browser_session = bool(getattr(provider, "browser_pagination", False))
        transcription = None
        transcription_error: str | None = None
        if args.transcription_provider != "none":
            try:
                transcription = build_transcription_provider(
                    args.transcription_provider,
                    data_provider=provider,
                )
            except Exception as exc:
                transcription_error = type(exc).__name__
        checks = [
            DoctorCheck(
                "douyin_auth",
                lambda: {
                    "ok": browser_session or cookie_looks_authenticated(os.environ.get("DOUYIN_COOKIE")),
                    "code": (
                        "ego_browser_session"
                        if browser_session
                        else "authenticated_cookie"
                        if cookie_looks_authenticated(os.environ.get("DOUYIN_COOKIE"))
                        else "anonymous_or_expired"
                        if os.environ.get("DOUYIN_COOKIE", "").strip()
                        else "not_configured"
                    ),
                },
            ),
            DoctorCheck(
                "ffmpeg",
                lambda: {"ok": bool(shutil.which("ffmpeg")), "code": "available" if shutil.which("ffmpeg") else "missing"},
            ),
            DoctorCheck(
                "ffprobe",
                lambda: {"ok": bool(shutil.which("ffprobe")), "code": "available" if shutil.which("ffprobe") else "missing"},
            ),
        ]
        if transcription_error:
            checks.append(
                DoctorCheck(
                    "aliyun_asr_config",
                    lambda: {"ok": False, "code": "not_configured", "error_type": transcription_error},
                )
            )
        payload = run_doctor(
            provider,
            transcription_provider=transcription,
            transcription_required=args.transcription_provider != "none",
            checks=checks,
        )
        _print_douyin_payload(payload, as_json=args.json)
        return 0 if payload["ok"] else 1

    if args.douyin_command == "transcribe":
        provider = build_collection_provider(
            args.provider,
            transcription_provider_name=args.transcription_provider,
            allow_paid_fallback=args.allow_paid_fallback,
        )
        payload = provider.call(
            "video_to_text_v2",
            body={"url": args.url},
            use_cache=not args.no_cache,
        )
        _print_douyin_payload(payload, as_json=args.json)
        return 0

    provider = build_data_provider(args.provider, allow_paid_fallback=args.allow_paid_fallback)
    if args.douyin_command == "detail":
        payload = provider.call("detail_v4", body={"url": args.url}, use_cache=not args.no_cache)
    elif args.douyin_command == "search-video":
        payload = provider.call(
            "video_search",
            params={
                "keyword": args.keyword,
                "offset": args.offset,
                "search_id": args.search_id,
                "max_pages": args.max_pages,
                "max_items": args.max_items,
            },
            use_cache=not args.no_cache,
        )
    elif args.douyin_command == "search-user":
        payload = provider.call(
            "user_search",
            params={"keyword": args.keyword, "offset": args.offset, "search_id": args.search_id},
            use_cache=not args.no_cache,
        )
    elif args.douyin_command == "user-posts":
        payload = provider.call(
            "user_post",
            params={
                "userId": args.sec_uid,
                "cursor": args.cursor,
                "sortType": args.sort_type,
                "max_pages": args.max_pages,
                "max_items": args.max_items,
            },
            use_cache=not args.no_cache,
        )
    else:
        raise ValueError(args.douyin_command)
    _print_douyin_payload(payload, as_json=args.json)
    return 0


def _print_douyin_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        json_print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False))


def handle_collect_task(args: argparse.Namespace, store: Store) -> int:
    orchestrator = CollectionTaskOrchestrator(store)
    if args.task_command == "keyword":
        role_id = args.role_id
        if args.role_name:
            role = store.get_ip_role(name=args.role_name)
            if not role:
                raise KeyError(f"role not found: {args.role_name}")
            role_id = role["id"]
        report = orchestrator.run_keyword_task(
            topic=args.topic,
            target_count=args.target_count,
            policy=_collection_policy_from_args(args),
            tool_provider=args.data_provider,
            transcription_provider=args.transcription_provider,
            allow_paid_fallback=args.allow_paid_fallback,
            keywords=args.keyword,
            related_keywords=args.related_keyword,
            role_id=role_id,
            understanding_provider=args.understanding_provider,
            understanding_model=args.understanding_model,
        )
        if args.json:
            json_print(report)
        else:
            print(format_task_show(report))
        return 0

    if args.task_command == "author":
        report = orchestrator.run_author_task(
            name=args.name,
            sec_uid=args.sec_uid,
            policy=_collection_policy_from_args(args),
            data_provider=args.data_provider,
            transcription_provider=args.transcription_provider,
            allow_paid_fallback=args.allow_paid_fallback,
            like_floor=args.like_floor,
            materialize_top=args.materialize_top,
            max_pages=args.max_pages,
            sort_type=args.sort_type,
            skip_expand=args.skip_expand,
            no_cache=args.no_cache,
            refresh_existing_understanding=args.refresh_existing_understanding,
            understanding_provider=args.understanding_provider,
            understanding_model=args.understanding_model,
        )
        if args.json:
            json_print(report)
        else:
            print(format_task_show(report))
        return 0

    if args.task_command == "discover-authors":
        report = orchestrator.run_discovered_authors_task(
            min_appearances=args.min_appearances,
            top_authors=args.top_authors,
            like_floor=args.like_floor,
            materialize_top=args.materialize_top,
            max_pages=args.max_pages,
            sort_type=args.sort_type,
            skip_expand=args.skip_expand,
            no_cache=args.no_cache,
            dry_run=args.dry_run,
            understanding_provider=args.understanding_provider,
            understanding_model=args.understanding_model,
            policy=_collection_policy_from_args(args),
            data_provider=args.data_provider,
            transcription_provider=args.transcription_provider,
            allow_paid_fallback=args.allow_paid_fallback,
        )
        if args.json:
            json_print(report)
        else:
            print(format_task_show(report))
        return 0

    if args.task_command == "show":
        report = orchestrator.build_task_report(args.task_id)
        if args.json:
            json_print(report)
        else:
            print(format_task_show(report))
        return 0

    if args.task_command == "report":
        report = orchestrator.build_task_report(args.task_id)
        if args.json:
            json_print(report)
        else:
            print(format_task_report_markdown(report))
        return 0

    if args.task_command == "resume":
        report = orchestrator.resume_task(args.task_id)
        if args.json:
            json_print(report)
        else:
            print(format_task_show(report))
        return 0

    raise ValueError(args.task_command)


def _collection_policy_from_args(args: argparse.Namespace) -> CollectionPolicy:
    return CollectionPolicy(
        viral_like_floor=int(getattr(args, "like_floor", 10000)),
        min_duration_seconds=int(getattr(args, "min_duration_seconds", 20)),
        max_duration_seconds=int(getattr(args, "max_duration_seconds", 300)),
        max_search_pages=int(getattr(args, "max_search_pages", 3)),
        page_size=int(getattr(args, "page_size", 10)),
    )


def handle_collect_author(args: argparse.Namespace, store: Store) -> int:
    if args.author_command == "list":
        authors = [_author_summary(author) for author in store.list_douyin_authors()]
        if args.json:
            json_print({"authors": authors})
        else:
            for author in authors:
                print(
                    "\t".join(
                        [
                            author.get("sec_uid") or "",
                            author.get("nickname") or "",
                            str(author.get("follower_count") or ""),
                            str(author.get("aweme_count") or ""),
                        ]
                    )
                )
        return 0

    if args.author_command == "videos":
        author = _resolve_douyin_author(store, sec_uid=args.sec_uid, name=args.name)
        videos = _rank_author_videos(
            store.list_douyin_author_videos(author["sec_uid"]),
            like_floor=args.like_floor,
            min_duration_seconds=args.min_duration_seconds,
            max_duration_seconds=args.max_duration_seconds,
        )
        payload = {"author": _author_summary(author), "videos": videos[: args.top], "viral_count": len(videos)}
        if args.json:
            json_print(payload)
        else:
            for video in payload["videos"]:
                print(f"{video['score']}\t{video['likes']}\t{video['work_id']}\t{video['title']}")
        return 0

    if args.author_command == "expand":
        author = _resolve_douyin_author(store, sec_uid=args.sec_uid, name=args.name)
        load_local_env()
        client = build_data_provider(args.data_provider, allow_paid_fallback=args.allow_paid_fallback)
        cursor = args.cursor or ""
        page_limit = args.max_pages if args.max_pages > 0 else 1000
        pages: list[dict[str, Any]] = []
        saved_video_ids: list[str] = []
        seen_cursors: set[str] = set()
        nonviral_page_streak = 0
        stop_reason = "max_pages"
        for page_number in range(1, page_limit + 1):
            params: dict[str, Any] = {
                "userId": author["sec_uid"],
                "sortType": args.sort_type,
                "cursor": cursor,
                "max_pages": args.max_pages,
            }
            result = client.call("user_post", params=params, use_cache=not args.no_cache)
            normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
            items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
            packages = normalized.get("source_packages") if isinstance(normalized.get("source_packages"), list) else []
            page_saved = 0
            page_videos: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                source_package = packages[index] if index < len(packages) and isinstance(packages[index], dict) else {}
                video = _author_video_from_normalized_item(item, source_package)
                page_videos.append(video)
                video_id = store.upsert_douyin_author_video(
                    author["sec_uid"],
                    video,
                    raw=item.get("raw") if isinstance(item.get("raw"), dict) else None,
                )
                saved_video_ids.append(video_id)
                page_saved += 1
            paging = result.get("paging") if isinstance(result.get("paging"), dict) else {}
            next_cursor = str(paging.get("cursor") or "")
            has_next = bool(paging.get("has_next"))
            page_viral_count = len(
                _rank_author_videos(
                    page_videos,
                    like_floor=args.like_floor,
                    min_duration_seconds=args.min_duration_seconds,
                    max_duration_seconds=args.max_duration_seconds,
                )
            )
            nonviral_page_streak = nonviral_page_streak + 1 if page_viral_count == 0 else 0
            pages.append(
                {
                    "page": page_number,
                    "fetched_count": len(items),
                    "saved_count": page_saved,
                    "viral_count": page_viral_count,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                    "has_next": has_next,
                }
            )
            if not has_next:
                stop_reason = "no_next_page"
                break
            if bool((paging.get("raw") or {}).get("browser_aggregated")):
                stop_reason = str((paging.get("raw") or {}).get("stop_reason") or "browser_aggregated")
                break
            if not next_cursor or next_cursor in seen_cursors:
                stop_reason = "cursor_exhausted"
                break
            if args.stop_after_nonviral_pages > 0 and nonviral_page_streak >= args.stop_after_nonviral_pages:
                stop_reason = "nonviral_page_streak"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        ranked_videos = _rank_author_videos(
            store.list_douyin_author_videos(author["sec_uid"]),
            like_floor=args.like_floor,
            min_duration_seconds=args.min_duration_seconds,
            max_duration_seconds=args.max_duration_seconds,
        )
        payload = {
            "author": _author_summary(author),
            "pages": pages,
            "saved_count": len(set(saved_video_ids)),
            "total_stored_count": len(store.list_douyin_author_videos(author["sec_uid"])),
            "viral_count": len(ranked_videos),
            "stop_reason": stop_reason,
            "top_videos": ranked_videos[: args.top],
        }
        if args.json:
            json_print(payload)
        else:
            print(f"saved={payload['saved_count']} total={payload['total_stored_count']} viral={payload['viral_count']}")
            for video in payload["top_videos"]:
                print(f"{video['score']}\t{video['likes']}\t{video['work_id']}\t{video['title']}")
        return 0

    if args.author_command == "materialize":
        author = _resolve_douyin_author(store, sec_uid=args.sec_uid, name=args.name)
        topic = args.topic or f"{author.get('nickname') or 'Douyin author'} 爆款作品"
        run_id = store.create_collection_run(
            task_id=None,
            role_id=None,
            topic=topic,
            target_count=args.top,
            like_floor=args.like_floor,
            super_like_threshold=100000,
            tool_provider=f"{args.data_provider}_author",
        )
        client = None
        ranked_videos = _rank_author_videos(
            store.list_douyin_author_videos(author["sec_uid"]),
            like_floor=args.like_floor,
            min_duration_seconds=args.min_duration_seconds,
            max_duration_seconds=args.max_duration_seconds,
        )[: args.top]
        materialized: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        try:
            for video in ranked_videos:
                existing = _find_collected_material_by_work_id(store, str(video.get("work_id") or ""))
                if existing and not args.duplicate_existing:
                    status = "existing_preserved"
                    if args.refresh_existing_understanding:
                        understanding = build_material_understanding(existing, provider=args.provider, model=args.model)
                        validate_understanding(understanding)
                        store.update_material_understanding(
                            existing["id"],
                            understanding=understanding,
                            provider=args.provider,
                            model=args.model,
                        )
                        store.log_material_understanding(
                            run_id=existing.get("run_id") or run_id,
                            material_id=existing["id"],
                            provider=args.provider,
                            model=args.model,
                            status="ok",
                            output=understanding,
                        )
                        status = "existing_understanding_refreshed"
                    materialized.append(
                        {
                            "material_id": existing["id"],
                            "work_id": video.get("work_id"),
                            "title": video.get("title"),
                            "status": status,
                        }
                    )
                    continue
                source_url = video.get("source_url")
                if not source_url:
                    skipped.append({"work_id": video.get("work_id"), "title": video.get("title"), "reason": "missing_source_url"})
                    continue
                if client is None:
                    client = build_collection_provider(
                        args.data_provider,
                        transcription_provider_name=args.transcription_provider,
                        allow_paid_fallback=args.allow_paid_fallback,
                    )
                extract_result = client.call("video_to_text_v2", body={"url": source_url}, use_cache=not args.no_cache)
                normalized = extract_result.get("normalized") if isinstance(extract_result.get("normalized"), dict) else {}
                transcript_text = str(
                    normalized.get("text")
                    or (normalized.get("source_package") or {}).get("transcript_text")
                    or ""
                ).strip()
                if not transcript_text:
                    skipped.append({"work_id": video.get("work_id"), "title": video.get("title"), "reason": "empty_transcript"})
                    continue
                source_package = _source_package_from_author_video(author, video)
                extract_package = normalized.get("source_package") if isinstance(normalized.get("source_package"), dict) else {}
                for key, value in extract_package.items():
                    if value in (None, "", []):
                        continue
                    if key in {"title", "clean_title", "platform_caption", "caption_text"} and source_package.get(key):
                        continue
                    if source_package.get(key) in (None, "", []):
                        source_package[key] = value
                source_package["transcript_text"] = transcript_text
                understanding = build_material_understanding(source_package, provider=args.provider, model=args.model)
                validate_understanding(understanding)
                source_package["material_understanding"] = understanding
                source_package["understanding_status"] = str(understanding.get("status") or "success")
                material_id = store.insert_collected_material(
                    run_id=run_id,
                    source_package=source_package,
                    material_understanding=understanding,
                    raw={"author": _author_summary(author), "author_video": video, "video_to_text_v2_result": extract_result},
                )
                store.log_material_understanding(
                    run_id=run_id,
                    material_id=material_id,
                    provider=args.provider,
                    model=args.model,
                    status="ok",
                    output=understanding,
                )
                materialized.append(
                    {
                        "material_id": material_id,
                        "work_id": video.get("work_id"),
                        "title": video.get("title"),
                        "status": "created",
                    }
                )
            status = "completed" if materialized else "empty"
            store.finish_collection_run(
                run_id,
                status=status,
                summary={"materialized": materialized, "skipped": skipped, "author": _author_summary(author)},
            )
        except Exception as exc:
            store.finish_collection_run(
                run_id,
                status="failed",
                summary={"materialized": materialized, "skipped": skipped, "author": _author_summary(author)},
                error=str(exc),
            )
            raise
        payload = {
            "run_id": run_id,
            "author": _author_summary(author),
            "materialized": materialized,
            "skipped": skipped,
        }
        if args.json:
            json_print(payload)
        else:
            print(f"run={run_id} materialized={len(materialized)} skipped={len(skipped)}")
            for item in materialized:
                print(f"{item['material_id']}\t{item['status']}\t{item['title']}")
        return 0

    raise ValueError(args.author_command)


def _author_summary(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "sec_uid": author.get("sec_uid"),
        "uid": author.get("uid"),
        "douyin_id": author.get("douyin_id"),
        "nickname": author.get("nickname"),
        "signature": author.get("signature"),
        "profile_url": author.get("profile_url"),
        "ip_location": author.get("ip_location"),
        "follower_count": author.get("follower_count"),
        "following_count": author.get("following_count"),
        "aweme_count": author.get("aweme_count"),
        "total_favorited": author.get("total_favorited"),
        "source_material_id": author.get("source_material_id"),
        "source_work_id": author.get("source_work_id"),
        "fetched_at": author.get("fetched_at"),
        "updated_at": author.get("updated_at"),
    }


def _resolve_douyin_author(store: Store, *, sec_uid: str | None = None, name: str | None = None) -> dict[str, Any]:
    if sec_uid:
        author = store.get_douyin_author(sec_uid)
        if not author:
            raise KeyError(f"douyin author not found: {sec_uid}")
        return author
    if not name:
        raise ValueError("--sec-uid or --name is required")
    matches = [author for author in store.list_douyin_authors() if author.get("nickname") == name]
    if not matches:
        matches = [author for author in store.list_douyin_authors() if name in str(author.get("nickname") or "")]
    if not matches:
        raise KeyError(f"douyin author not found: {name}")
    if len(matches) > 1:
        names = ", ".join(str(author.get("nickname")) for author in matches[:5])
        raise ValueError(f"multiple douyin authors matched {name!r}: {names}; use --sec-uid")
    return matches[0]


def _author_video_from_normalized_item(item: dict[str, Any], source_package: dict[str, Any]) -> dict[str, Any]:
    metrics = source_package.get("public_metrics") if isinstance(source_package.get("public_metrics"), dict) else item.get("metrics")
    return {
        "work_id": item.get("id") or source_package.get("work_id"),
        "source_url": source_package.get("source_link") or item.get("share_url") or item.get("short_url"),
        "title": source_package.get("title") or item.get("title"),
        "platform_caption": source_package.get("platform_caption") or item.get("caption") or item.get("title"),
        "caption": source_package.get("platform_caption") or item.get("caption") or item.get("title"),
        "post_time": source_package.get("post_time") or item.get("post_time"),
        "duration_ms": source_package.get("duration_ms") or item.get("duration"),
        "cover_url": source_package.get("cover_url") or item.get("cover_url"),
        "metrics": metrics or {},
        "source_package": source_package,
    }


def _source_package_from_author_video(author: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    return {
        "source_type": "direct_douyin_author",
        "source_platform": "douyin",
        "source_link": video.get("source_url"),
        "title": video.get("title"),
        "clean_title": video.get("title"),
        "platform_caption": video.get("title"),
        "caption_text": video.get("title"),
        "hashtags": [],
        "author_name": author.get("nickname"),
        "author_sec_uid": author.get("sec_uid"),
        "author_profile_url": author.get("profile_url"),
        "author_douyin_id": author.get("douyin_id"),
        "work_id": video.get("work_id"),
        "post_time": video.get("post_time"),
        "duration_ms": video.get("duration_ms"),
        "public_metrics": {
            "digg_count": metrics.get("digg_count") or video.get("likes"),
            "collect_count": metrics.get("collect_count") or video.get("collects"),
            "comment_count": metrics.get("comment_count") or video.get("comments"),
            "share_count": metrics.get("share_count") or video.get("shares"),
            "play_count": metrics.get("play_count"),
        },
        "collection_notes": ["author_hot_work"],
    }


def _find_collected_material_by_work_id(store: Store, work_id: str) -> dict[str, Any] | None:
    if not work_id:
        return None
    for material in store.list_collected_materials():
        if str(material.get("work_id") or "") == work_id:
            return material
    return None


def _rank_author_videos(
    videos: list[dict[str, Any]],
    *,
    like_floor: int,
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for video in videos:
        metrics = _author_video_metrics(video)
        candidate = {"source_package": {"public_metrics": metrics}}
        likes = metric_value(metrics, "digg_count", "likes")
        score = engagement_score(candidate)
        duration_ms = _optional_int(video.get("duration_ms"))
        if duration_ms is not None:
            duration_seconds = duration_ms / 1000
            if duration_seconds < min_duration_seconds or duration_seconds > max_duration_seconds:
                continue
        if likes < like_floor and score < max(like_floor * 2, 1):
            continue
        ranked.append(
            {
                "id": video.get("id"),
                "work_id": video.get("work_id"),
                "title": video.get("title"),
                "source_url": video.get("source_url"),
                "post_time": video.get("post_time"),
                "duration_ms": duration_ms,
                "likes": likes,
                "collects": metric_value(metrics, "collect_count", "favorites", "favorite_count"),
                "comments": metric_value(metrics, "comment_count", "comments"),
                "shares": metric_value(metrics, "share_count", "shares"),
                "score": score,
                "metrics": metrics,
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            int(item["score"]),
            int(item["shares"]),
            int(item["collects"]),
            int(item["comments"]),
            int(item["likes"]),
        ),
        reverse=True,
    )


def _author_video_metrics(video: dict[str, Any]) -> dict[str, Any]:
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    if metrics:
        return dict(metrics)
    source_package = video.get("source_package") if isinstance(video.get("source_package"), dict) else {}
    package_metrics = source_package.get("public_metrics") if isinstance(source_package.get("public_metrics"), dict) else {}
    return dict(package_metrics)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _read_role_json_file(file_path: str) -> Any:
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def _role_items_from_json(decoded: Any) -> list[dict[str, Any]]:
    roles = decoded.get("roles", decoded) if isinstance(decoded, dict) else decoded
    if isinstance(roles, dict):
        roles = [roles]
    if not isinstance(roles, list):
        raise ValueError("role JSON must be an object, array, or {\"roles\": [...]}")
    result: list[dict[str, Any]] = []
    for item in roles:
        if not isinstance(item, dict):
            raise ValueError("each role must be a JSON object")
        result.append(item)
    return result


def _role_text_field(item: dict[str, Any], key: str) -> str | None:
    if key not in item:
        return None
    return str(item.get(key) or "")


def _role_list_field(item: dict[str, Any], *keys: str) -> list[str] | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return [str(part) for part in value]
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        return [str(value)]
    return None


def _role_json_field(item: dict[str, Any], key: str) -> Any:
    json_key = f"{key}_json"
    if key in item:
        return item[key]
    if json_key in item:
        return item[json_key]
    return None


def _upsert_role_from_payload(
    store: Store,
    item: dict[str, Any],
    *,
    import_mode: bool = False,
) -> str:
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("role name is required")
    existing = store.get_ip_role(name=name)
    status = item.get("confirmation_status")
    if status == "confirmed":
        status = "agent_suggested"
    elif status is None and import_mode and existing is None:
        status = "agent_suggested"
    return store.upsert_ip_role(
        name=name,
        positioning=_role_text_field(item, "positioning"),
        target_directions=_role_list_field(item, "target_directions", "target_direction"),
        search_keywords=_role_list_field(item, "search_keywords", "search_keyword"),
        avoid_directions=_role_list_field(item, "avoid_directions", "avoid_direction"),
        preferred_content=_role_list_field(item, "preferred_content"),
        forbidden_content=_role_list_field(item, "forbidden_content"),
        confirmation_status=str(status) if status else None,
        role_baseline=_role_text_field(item, "role_baseline"),
        life_stage=_role_text_field(item, "life_stage"),
        core_temperament=_role_text_field(item, "core_temperament"),
        speaking_posture=_role_text_field(item, "speaking_posture"),
        target_audience=_role_json_field(item, "target_audience"),
        fit_themes=_role_list_field(item, "fit_themes"),
        avoid_themes=_role_list_field(item, "avoid_themes"),
        style_anchors=_role_json_field(item, "style_anchors"),
        expression_constraints=_role_json_field(item, "expression_constraints"),
        forbidden_expressions=_role_list_field(item, "forbidden_expressions"),
        typical_topics=_role_list_field(item, "typical_topics"),
        theme_map=_role_json_field(item, "theme_map"),
        source_evidence=_role_json_field(item, "source_evidence"),
        agent_suggestions=_role_json_field(item, "agent_suggestions"),
        notes=_role_text_field(item, "notes"),
        enabled=bool(item["enabled"]) if "enabled" in item else None,
    )


def _format_role_summary(role: dict[str, Any]) -> str:
    packet_ready = "yes" if role.get("persona_packet") else "no"
    keywords = ", ".join(role.get("search_keywords") or [])
    forbidden = ", ".join((role.get("forbidden_content") or []) + (role.get("forbidden_expressions") or []))
    lines = [
        f"id: {role['id']}",
        f"name: {role['name']}",
        f"status: {role['confirmation_status']}",
        f"enabled: {str(bool(role['enabled'])).lower()}",
        f"profile_version: {role['profile_version']}",
        f"needs_reconfirm: {str(bool(role['needs_reconfirm'])).lower()}",
        f"positioning: {role.get('positioning') or ''}",
        f"search_keywords: {keywords}",
        f"forbidden: {forbidden}",
        f"persona_packet_ready: {packet_ready}",
    ]
    return "\n".join(lines)


def handle_collect_role(args: argparse.Namespace, store: Store) -> int:
    if args.role_command == "upsert":
        if args.file:
            items = _role_items_from_json(_read_role_json_file(args.file))
            if len(items) != 1:
                raise ValueError("role upsert --file expects exactly one role object; use role import for multiple roles")
            role_id = _upsert_role_from_payload(store, items[0], import_mode=False)
        else:
            if not args.name:
                raise ValueError("--name is required unless --file is used")
            role_id = store.upsert_ip_role(
                name=args.name,
                positioning=args.positioning,
                target_directions=args.target_direction,
                search_keywords=args.search_keyword,
                avoid_directions=args.avoid_direction,
                preferred_content=args.preferred_content,
                forbidden_content=args.forbidden_content,
                enabled=not args.disabled,
            )
        if args.json:
            json_print({"role_id": role_id, "role": store.get_ip_role(role_id)})
        else:
            print(role_id)
        return 0

    if args.role_command == "list":
        roles = store.list_ip_roles(enabled_only=args.enabled_only, confirmed_only=args.confirmed_only)
        if args.json:
            json_print({"roles": roles})
        else:
            for role in roles:
                enabled = "enabled" if role["enabled"] else "disabled"
                print(
                    f"{role['id']}\t{enabled}\t{role['confirmation_status']}\t"
                    f"v{role['profile_version']}\t{role['name']}\t{role['positioning']}"
                )
        return 0

    if args.role_command == "show":
        role = store.get_ip_role(args.role_id, name=args.name)
        if not role:
            raise KeyError("role not found")
        if args.json:
            json_print(role)
        else:
            print(_format_role_summary(role))
        return 0

    if args.role_command == "import":
        roles = _role_items_from_json(_read_role_json_file(args.file))
        imported: list[str] = []
        for item in roles:
            imported.append(_upsert_role_from_payload(store, item, import_mode=True))
        if args.json:
            json_print({"role_ids": imported})
        else:
            print("\n".join(imported))
        return 0

    if args.role_command == "export":
        roles = store.export_ip_roles()
        output = Path(args.file)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"roles": roles}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if args.json:
            json_print({"file": str(output), "count": len(roles)})
        else:
            print(output)
        return 0

    if args.role_command == "confirm":
        result = store.confirm_ip_role(args.role_id, change_reason=args.change_reason)
        if args.json:
            json_print(result)
        else:
            print(f"{result['role_id']}\tv{result['profile_version']}\t{result['version_id']}")
        return 0

    if args.role_command == "packet":
        packet = store.build_ip_role_persona_packet(args.role_id, name=args.name)
        if args.json:
            json_print({"persona_packet": packet})
        else:
            print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.role_command == "match-existing":
        role = store.get_ip_role(args.role_id)
        if not role:
            raise KeyError(f"role not found: {args.role_id}")
        matches: list[dict[str, Any]] = []
        for material in store.list_collected_materials():
            match = evaluate_role_match(material, role)
            match_id = store.insert_material_role_match(
                material_id=material["id"],
                role_id=role["id"],
                task_id=args.task_id or material.get("task_id"),
                fit_score=match["fit_score"],
                decision=match["decision"],
                reasons=match["reasons"],
                matched_keywords=match["matched_keywords"],
                avoidance_notes=match["avoidance_notes"],
            )
            matches.append(
                {
                    "match_id": match_id,
                    "material_id": material["id"],
                    "role_confirmation_status": role.get("confirmation_status"),
                    "not_confirmed": role.get("confirmation_status") != "confirmed",
                    **match,
                }
            )
        if args.json:
            json_print({"matches": matches})
        else:
            if role.get("confirmation_status") != "confirmed":
                print(f"warning: role {role['id']} is {role.get('confirmation_status')}; matches are diagnostic", file=sys.stderr)
            print("\n".join(item["match_id"] for item in matches))
        return 0

    raise ValueError(args.role_command)


def handle_material(args: argparse.Namespace, store: Store) -> int:
    if args.material_command == "list":
        materials = store.list_collected_materials(run_id=args.run_id, role_id=args.role_id, status=args.status)
        if args.json:
            json_print({"materials": materials})
        else:
            for material in materials:
                print(f"{material['id']}\t{material['status']}\t{material.get('title') or ''}")
        return 0

    if args.material_command == "show":
        material = store.get_collected_material(args.material_id)
        if not material:
            raise KeyError(f"material not found: {args.material_id}")
        json_print(material)
        return 0

    if args.material_command == "creations":
        creations = store.list_material_creations(
            material_id=args.material_id,
            role_id=args.role_id,
            content_package_id=args.content_id,
        )
        if args.json:
            json_print({"creations": creations})
        else:
            for creation in creations:
                print(
                    f"{creation['id']}\t{creation['material_id']}\t{creation['role_id']}\t"
                    f"{creation['content_package_id']}\t{creation['platform']}\t{creation['status']}"
                )
        return 0

    if args.material_command == "promote":
        content_id = store.promote_material_to_content_package(
            args.material_id,
            platform=args.platform,
            role_id=args.role_id,
            task_id=args.task_id,
            rewrite_angle=args.rewrite_angle,
            title=args.title,
            body=args.body,
            hashtags=args.hashtag,
        )
        if args.json:
            json_print({"content_id": content_id, "material_id": args.material_id})
        else:
            print(content_id)
        return 0

    if args.material_command == "inventory":
        if args.inventory_command == "classify":
            classification = store.classify_material_inventory(
                material_id=args.material_id,
                role_id=args.role_id,
                topic_direction=args.topic_direction,
                content_mechanism=args.content_mechanism,
                knowledge_subtype=args.knowledge_subtype,
                material_class=args.material_class,
                is_primary=args.primary,
                review_status=args.review_status,
                reviewer=args.reviewer,
                decision_source=args.decision_source,
                classification_reasons=args.reason,
            )
            if args.json:
                json_print(classification)
            else:
                print(classification["id"])
            return 0

        if args.inventory_command == "import":
            payload = _read_json_object_or_list(Path(args.file))
            if isinstance(payload, dict):
                payload_role_id = payload.get("role_id")
                if payload_role_id is not None and str(payload_role_id) != args.role_id:
                    raise ValueError("import file role_id does not match --role-id")
                classifications = payload.get("classifications")
            else:
                classifications = payload
            imported = store.import_material_inventory(role_id=args.role_id, classifications=classifications)
            result = {"role_id": args.role_id, "imported_count": len(imported), "classifications": imported}
            if args.json:
                json_print(result)
            else:
                print(f"imported {len(imported)} classifications")
            return 0

        if args.inventory_command == "list":
            inventory = store.list_material_inventory(
                role_id=args.role_id,
                topic_direction=args.topic_direction,
                material_class=args.material_class,
                review_status=args.review_status,
                include_used=args.include_used,
            )
            if args.json:
                json_print({"role_id": args.role_id, "inventory": inventory})
            else:
                for item in inventory:
                    print(
                        f"{item['material_id']}\t{item['topic_direction']}\t{item['material_class']}\t"
                        f"{item['review_status']}\tused={str(item['used']).lower()}\t{item.get('material_title') or ''}"
                    )
            return 0

        if args.inventory_command == "pending":
            pending = store.list_pending_material_inventory(
                role_id=args.role_id,
                include_used=args.include_used,
                include_pending=args.include_pending,
                include_rejected=args.include_rejected,
                task_id=args.task_id,
                run_id=args.run_id,
            )
            result = {
                "role_id": args.role_id,
                "pending_count": len(pending),
                "distinct_source_works": len({item["source_work_id"] for item in pending}),
                "materials": pending,
            }
            if args.json:
                json_print(result)
            else:
                for item in pending:
                    print(
                        f"{item['material_id']}\t{item['source_work_id']}\t"
                        f"fit={item.get('accepted_role_match_fit_score') or ''}\t{item.get('title') or ''}"
                    )
            return 0

        if args.inventory_command == "summary":
            allocation = {
                "batch_key": None,
                "video_allocation": {},
                "formal_base_targets": {},
            }
            if args.allocation_file:
                payload = _read_json_object_or_list(Path(args.allocation_file))
                allocation = _parse_inventory_allocation(payload, role_id=args.role_id)
            summary = store.summarize_material_inventory(
                role_id=args.role_id,
                video_allocation=allocation["video_allocation"],
                formal_base_targets=allocation["formal_base_targets"],
                batch_key=allocation["batch_key"],
                include_used=args.include_used,
            )
            if args.json:
                json_print(summary)
            else:
                for topic in summary["topics"]:
                    required = topic.get("target_formal_base_count", "-")
                    shortage = topic.get("shortage", "-")
                    print(
                        f"{topic['topic_direction']}\tvideos={topic['planned_video_count']}\t"
                        f"available={topic['available_formal_rewrite_bases']}\t"
                        f"required={required}\tshortage={shortage}"
                    )
            return 0

        raise ValueError(args.inventory_command)

    raise ValueError(args.material_command)


def _read_json_object_or_list(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}: {exc.msg}") from exc


def _parse_inventory_allocation(payload: Any, *, role_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("allocation file must contain a JSON object")
    payload_role_id = str(payload.get("role_id") or "").strip()
    if not payload_role_id:
        raise ValueError("allocation file must contain role_id")
    if payload_role_id != role_id:
        raise ValueError("allocation file role_id does not match --role-id")
    batch_key = str(payload.get("batch_key") or "").strip()
    if not batch_key:
        raise ValueError("allocation file must contain batch_key")
    video_allocation = payload.get("video_allocation")
    formal_base_targets = payload.get("formal_base_targets")
    if not isinstance(video_allocation, dict) or not video_allocation:
        raise ValueError("allocation file video_allocation must be a non-empty object")
    if not isinstance(formal_base_targets, dict) or not formal_base_targets:
        raise ValueError("allocation file formal_base_targets must be a non-empty object")
    if set(video_allocation) != set(formal_base_targets):
        raise ValueError("video_allocation and formal_base_targets must contain the same topic directions")
    expected_video_total = payload.get("expected_video_total")
    if expected_video_total is not None:
        if isinstance(expected_video_total, bool) or not isinstance(expected_video_total, int) or expected_video_total < 0:
            raise ValueError("expected_video_total must be a non-negative integer")
        invalid_counts = [
            topic
            for topic, count in video_allocation.items()
            if isinstance(count, bool) or not isinstance(count, int) or count < 0
        ]
        if invalid_counts:
            raise ValueError("video_allocation counts must be non-negative integers")
        if sum(video_allocation.values()) != expected_video_total:
            raise ValueError(
                f"video_allocation total must equal expected_video_total ({expected_video_total})"
            )
    return {
        "batch_key": batch_key,
        "video_allocation": video_allocation,
        "formal_base_targets": formal_base_targets,
    }


def handle_report(args: argparse.Namespace, store: Store) -> int:
    if args.report_command == "daily":
        report = build_daily_report(store, args.date)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
            print(output)
        else:
            print(report, end="")
        return 0
    raise ValueError(args.report_command)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store(Path(args.db_path))

    try:
        if args.command == "init-db":
            return handle_init_db(store)
        if args.command == "db":
            if args.db_command == "migrate-collection-schema-v3":
                report = migrate_collection_schema_v3(
                    Path(args.db_path),
                    Path(args.destination) if args.destination else None,
                    replace=args.replace,
                    recovery_path=Path(args.recovery_path) if args.recovery_path else None,
                )
            elif args.db_command == "migrate-material-inventory-v1":
                report = migrate_material_inventory_v1(Path(args.db_path))
            else:
                raise ValueError(args.db_command)
            if args.json:
                json_print(report)
            else:
                print(json.dumps(report, ensure_ascii=False))
            return 0
        if args.command == "adb":
            return handle_adb(args)
        if args.command == "content":
            store.init_db()
            return handle_content(args, store)
        if args.command == "create":
            store.init_db()
            return handle_create(args, store)
        if args.command == "publish":
            store.init_db()
            return handle_publish(args, store)
        if args.command == "collect":
            if _collect_command_needs_db_init(args):
                store.init_db()
            return handle_collect(args, store)
        if args.command == "material":
            store.init_db()
            return handle_material(args, store)
        if args.command == "platforms":
            json_print(list_platforms())
            return 0
        if args.command == "report":
            store.init_db()
            return handle_report(args, store)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


def _collect_command_needs_db_init(args: argparse.Namespace) -> bool:
    if getattr(args, "collect_command", None) == "douyin":
        return False
    if getattr(args, "collect_command", None) == "author" and getattr(args, "author_command", None) in {"list", "videos"}:
        return False
    return True


def _infer_creation_from_content(store: Store, content_id: str) -> dict[str, str | None]:
    creations = store.list_material_creations(content_package_id=content_id)
    if creations:
        first = creations[0]
        return {"role_id": first.get("role_id"), "task_id": first.get("task_id")}
    with store.connect() as conn:
        row = conn.execute(
            "SELECT id, role_id FROM creation_tasks WHERE content_package_id = ? ORDER BY updated_at DESC, id LIMIT 1",
            (content_id,),
        ).fetchone()
    if row:
        return {"role_id": row["role_id"], "task_id": row["id"]}
    return {"role_id": None, "task_id": None}


def _build_collection_tools(
    provider: str,
    *,
    transcription_provider: str = "aliyun",
    allow_paid_fallback: bool = False,
):
    if provider == "direct":
        resolved = build_collection_provider(
            provider,
            transcription_provider_name=transcription_provider,
            allow_paid_fallback=allow_paid_fallback,
        )
        return build_douyin_registry(resolved)
    if provider == "mock":
        return build_mock_source_registry()
    raise ValueError(f"unknown collection tool provider: {provider}")


def _select_materials(
    store: Store,
    *,
    run_id: str | None = None,
    material_id: str | None = None,
) -> list[dict[str, Any]]:
    if material_id:
        material = store.get_collected_material(material_id)
        if not material:
            raise KeyError(f"material not found: {material_id}")
        return [material]
    if run_id:
        return store.list_collected_materials(run_id=run_id)
    raise ValueError("--run-id or --material-id is required")


def _match_material_to_roles(
    store: Store,
    material: dict[str, Any],
    *,
    role_ids: list[str],
    task_id: str | None,
) -> list[dict[str, Any]]:
    roles = [store.get_ip_role(role_id) for role_id in role_ids] if role_ids else store.list_ip_roles(enabled_only=True)
    matches: list[dict[str, Any]] = []
    for role in [item for item in roles if item]:
        match = evaluate_role_match(material, role)
        match_id = store.insert_material_role_match(
            material_id=material["id"],
            role_id=role["id"],
            task_id=task_id,
            fit_score=match["fit_score"],
            decision=match["decision"],
            reasons=match["reasons"],
            matched_keywords=match["matched_keywords"],
            avoidance_notes=match["avoidance_notes"],
        )
        matches.append(
            {
                "match_id": match_id,
                "material_id": material["id"],
                "role_id": role["id"],
                "role_confirmation_status": role.get("confirmation_status"),
                "not_confirmed": role.get("confirmation_status") != "confirmed",
                **match,
            }
        )
    return matches


def _format_collection_report(report: dict[str, Any]) -> str:
    run = report["run"]
    lines = [
        f"# Collection Report - {run['id']}",
        "",
        f"- topic: {run['topic']}",
        f"- status: {run['status']}",
        f"- saved: {report['saved_count']}/{run['target_count']}",
        f"- candidates: {report['candidate_count']}",
        "",
        "## Materials",
    ]
    for material in report["materials"]:
        summary = material.get("summary_text") or ""
        meta = " / ".join(
            value
            for value in [
                material.get("content_type"),
                material.get("oral_script_pattern"),
                f"risk={material.get('risk_level')}" if material.get("risk_level") else "",
            ]
            if value
        )
        detail = f" - {summary}" if summary else ""
        suffix = f" ({meta})" if meta else ""
        lines.append(f"- {material['id']} {material.get('clean_title') or material.get('title') or ''}{suffix}{detail}")
    lines.extend(["", "## Skipped"])
    for candidate in report["skipped"][:20]:
        lines.append(f"- {candidate['status']} {candidate.get('title') or ''}: {candidate.get('skip_reason') or ''}")
    if report["next_collection_keywords"]:
        lines.extend(["", "## Next Keywords", ", ".join(report["next_collection_keywords"])])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
