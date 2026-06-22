from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .adb import AdbClient
from .adapters import list_platforms
from .collection.api_manifest import catalog_as_dict, load_manifest_from_markdown
from .collection.douyin_cookie import fetch_douyin_cookie
from .collection.douyin_login_cookie import login_and_fetch_douyin_cookie, write_env_cookie
from .collection.mock_tools import build_mock_source_registry
from .collection.mxnzp_client import MxnzpConfig, MxnzpDouyinProClient
from .collection.mxnzp_tools import build_mxnzp_douyin_registry
from .collection.runner import CollectionConfig, TopicCollectionRunner, engagement_score, metric_value
from .collection.tools import parse_json_object
from .collection.understanding import build_material_understanding, evaluate_role_match, validate_understanding
from .feishu import build_publish_job_payload, write_payload
from .publisher import PublishRunner
from .report import build_daily_report
from .store import DEFAULT_DB_PATH, Store, loads


def json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcn", description="Codex MCN Ops CLI")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--adb-path", default="adb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the SQLite ledger")

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

    collect_parser = subparsers.add_parser("collect", help="Material collection commands")
    collect_sub = collect_parser.add_subparsers(dest="collect_command", required=True)

    catalog = collect_sub.add_parser("catalog", help="Inspect the local mxnzp API manifest")
    catalog.add_argument("--json", action="store_true")
    catalog.add_argument("--exposed-only", action="store_true")

    mxnzp_call = collect_sub.add_parser("mxnzp-call", help="Call one local mxnzp adapter method directly")
    mxnzp_call.add_argument("method_key")
    mxnzp_call.add_argument("--params", default="{}")
    mxnzp_call.add_argument("--body", default="{}")
    mxnzp_call.add_argument("--no-cache", action="store_true")
    mxnzp_call.add_argument("--auto-cookie", action="store_true", help="Try to fetch a Douyin homepage cookie for cookie-required methods")
    mxnzp_call.add_argument("--login-cookie", action="store_true", help="Open a browser login flow when a long Douyin cookie is required")
    mxnzp_call.add_argument("--allow-short-auto-cookie", action="store_true", help="Send the auto-fetched cookie even when it fails the length heuristic")
    mxnzp_call.add_argument("--json", action="store_true")

    douyin_cookie = collect_sub.add_parser("douyin-cookie", help="Fetch a Douyin homepage cookie")
    douyin_cookie.add_argument("--url", default="https://www.douyin.com")
    douyin_cookie.add_argument("--min-length", type=int, default=100)
    douyin_cookie.add_argument("--show-cookie", action="store_true")
    douyin_cookie.add_argument("--json", action="store_true")

    douyin_login_cookie = collect_sub.add_parser("douyin-login-cookie", help="Open browser login and fetch a logged-in Douyin cookie")
    douyin_login_cookie.add_argument("--browser-path")
    douyin_login_cookie.add_argument("--profile-dir", default="data/browser-profiles/douyin-cookie")
    douyin_login_cookie.add_argument("--timeout-seconds", type=float, default=300.0)
    douyin_login_cookie.add_argument("--poll-seconds", type=float, default=3.0)
    douyin_login_cookie.add_argument("--min-length", type=int, default=100)
    douyin_login_cookie.add_argument("--write-env", action="store_true")
    douyin_login_cookie.add_argument("--env-path", default=".env.local")
    douyin_login_cookie.add_argument("--show-cookie", action="store_true")
    douyin_login_cookie.add_argument("--close-browser", action="store_true")
    douyin_login_cookie.add_argument("--json", action="store_true")

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
    author_expand.add_argument("--max-pages", type=int, default=20, help="Use 0 to continue until MXNZP reports no next page")
    author_expand.add_argument("--like-floor", type=int, default=5000)
    author_expand.add_argument("--min-duration-seconds", type=int, default=20)
    author_expand.add_argument("--max-duration-seconds", type=int, default=300)
    author_expand.add_argument("--top", type=int, default=20)
    author_expand.add_argument("--stop-after-nonviral-pages", type=int, default=2, help="Use 0 to disable early stop")
    author_expand.add_argument("--login-cookie", action="store_true")
    author_expand.add_argument("--no-cache", action="store_true")
    author_expand.add_argument("--json", action="store_true")

    role = collect_sub.add_parser("role", help="Manage IP role profiles")
    role_sub = role.add_subparsers(dest="role_command", required=True)
    role_upsert = role_sub.add_parser("upsert", help="Create or update an IP role")
    role_upsert.add_argument("--name", required=True)
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
    role_list.add_argument("--json", action="store_true")
    role_show = role_sub.add_parser("show", help="Show one IP role")
    role_show.add_argument("--role-id")
    role_show.add_argument("--name")
    role_show.add_argument("--json", action="store_true")
    role_import = role_sub.add_parser("import", help="Import roles from a JSON file")
    role_import.add_argument("--file", required=True)
    role_import.add_argument("--json", action="store_true")
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
    collect_run.add_argument("--tool-provider", choices=["mock", "mxnzp"], default="mock")
    collect_run.add_argument("--max-search-pages", type=int, default=3)
    collect_run.add_argument("--page-size", type=int, default=5)
    collect_run.add_argument("--role-id")
    collect_run.add_argument("--search-keyword", action="append", default=[])
    collect_run.add_argument("--json", action="store_true")

    understand = collect_sub.add_parser("understand", help="Write Codex material understanding JSON")
    understand.add_argument("--run-id")
    understand.add_argument("--material-id")
    understand.add_argument("--role-id", action="append", default=[])
    understand.add_argument("--skip-role-match", action="store_true")
    understand.add_argument("--provider", default="local-rules")
    understand.add_argument("--model", default="material-understanding-rules-v2")
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
    if args.collect_command == "catalog":
        methods = load_manifest_from_markdown()
        if args.exposed_only:
            methods = [method for method in methods if method.model_exposed]
        payload = catalog_as_dict(methods)
        if args.json:
            json_print(payload)
        else:
            for method in payload["methods"]:
                print(f"{method['key']}\t{method['http_method']}\t{method['group']}\t{method['title']}")
        return 0

    if args.collect_command == "mxnzp-call":
        config = MxnzpConfig.from_env()
        client = MxnzpDouyinProClient(config)
        params = parse_json_object(args.params)
        body = parse_json_object(args.body)
        needs_cookie = args.method_key == "user_post" and "cookie" not in params and "cookie" not in body and not config.douyin_cookie
        if args.login_cookie and needs_cookie:
            if not args.json:
                print("请在打开的浏览器窗口登录抖音；登录成功后本命令会自动检测长 cookie。", file=sys.stderr)
            login_result = login_and_fetch_douyin_cookie()
            if not login_result.cookie_valid:
                raise ValueError(login_result.error or "failed to fetch a valid logged-in Douyin cookie")
            params["cookie"] = login_result.cookie
        elif args.auto_cookie and args.method_key == "user_post" and "cookie" not in params and "cookie" not in body:
            cookie_result = fetch_douyin_cookie()
            if not cookie_result.cookie:
                raise ValueError(f"failed to fetch Douyin cookie: {cookie_result.error or 'empty cookie'}")
            if not cookie_result.cookie_valid and not args.allow_short_auto_cookie:
                raise ValueError(
                    "auto-fetched Douyin cookie is too short to look logged in; "
                    "provide DOUYIN_COOKIE or retry with --allow-short-auto-cookie for diagnostics"
                )
            params["cookie"] = cookie_result.cookie
        payload = client.call(
            args.method_key,
            params=params,
            body=body,
            use_cache=not args.no_cache,
        )
        json_print(payload)
        return 0

    if args.collect_command == "douyin-cookie":
        result = fetch_douyin_cookie(url=args.url, min_cookie_length=args.min_length)
        payload = result.to_dict(include_cookie=args.show_cookie)
        if args.json:
            json_print(payload)
        else:
            if args.show_cookie and result.cookie:
                print(result.cookie)
            else:
                print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.collect_command == "douyin-login-cookie":
        if not args.json:
            print("请在打开的浏览器窗口登录抖音；登录成功后本命令会自动检测长 cookie。", file=sys.stderr)
        result = login_and_fetch_douyin_cookie(
            browser_path=args.browser_path,
            profile_dir=args.profile_dir,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            min_cookie_length=args.min_length,
            close_browser=args.close_browser,
        )
        if args.write_env and result.cookie_valid:
            env_path = write_env_cookie(result.cookie, env_path=args.env_path)
            result = replace(result, written_env_path=str(env_path))
        payload = result.to_dict(include_cookie=args.show_cookie)
        if args.json:
            json_print(payload)
        else:
            if args.show_cookie and result.cookie:
                print(result.cookie)
            else:
                print(json.dumps(payload, ensure_ascii=False))
        return 0 if result.cookie_valid else 1

    if args.collect_command == "author":
        return handle_collect_author(args, store)

    if args.collect_command == "role":
        return handle_collect_role(args, store)

    if args.collect_command == "run":
        role_profile = store.get_ip_role(args.role_id) if args.role_id else None
        tools = _build_collection_tools(args.tool_provider)
        runner = TopicCollectionRunner(tools, store)
        result = runner.run(
            CollectionConfig(
                topic=args.topic,
                target_count=args.target_count,
                like_floor=args.like_floor,
                super_like_threshold=args.super_like_threshold,
                min_duration_seconds=args.min_duration_seconds,
                max_duration_seconds=args.max_duration_seconds,
                tool_provider=args.tool_provider,
                max_search_pages=args.max_search_pages,
                page_size=args.page_size,
                role_id=args.role_id,
                role_profile=role_profile,
                search_keywords=args.search_keyword,
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
        config = MxnzpConfig.from_env()
        cookie = None
        if args.login_cookie and not config.douyin_cookie:
            if not args.json:
                print("请在打开的浏览器窗口登录抖音；登录成功后本命令会自动检测长 cookie。", file=sys.stderr)
            login_result = login_and_fetch_douyin_cookie()
            if not login_result.cookie_valid:
                raise ValueError(login_result.error or "failed to fetch a valid logged-in Douyin cookie")
            cookie = login_result.cookie
        client = MxnzpDouyinProClient(config)
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
            }
            if cookie:
                params["cookie"] = cookie
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


def handle_collect_role(args: argparse.Namespace, store: Store) -> int:
    if args.role_command == "upsert":
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
            json_print({"role_id": role_id})
        else:
            print(role_id)
        return 0

    if args.role_command == "list":
        roles = store.list_ip_roles(enabled_only=args.enabled_only)
        if args.json:
            json_print({"roles": roles})
        else:
            for role in roles:
                enabled = "enabled" if role["enabled"] else "disabled"
                print(f"{role['id']}\t{enabled}\t{role['name']}\t{role['positioning']}")
        return 0

    if args.role_command == "show":
        role = store.get_ip_role(args.role_id, name=args.name)
        if not role:
            raise KeyError("role not found")
        json_print(role)
        return 0

    if args.role_command == "import":
        raw = Path(args.file).read_text(encoding="utf-8")
        decoded = json.loads(raw)
        roles = decoded.get("roles", decoded) if isinstance(decoded, dict) else decoded
        if not isinstance(roles, list):
            raise ValueError("role import file must be a JSON array or {\"roles\": [...]}")
        imported: list[str] = []
        for item in roles:
            if not isinstance(item, dict):
                raise ValueError("each role must be a JSON object")
            imported.append(
                store.upsert_ip_role(
                    name=str(item["name"]),
                    positioning=str(item.get("positioning") or ""),
                    target_directions=list(item.get("target_directions") or []),
                    search_keywords=list(item.get("search_keywords") or []),
                    avoid_directions=list(item.get("avoid_directions") or []),
                    preferred_content=list(item.get("preferred_content") or []),
                    forbidden_content=list(item.get("forbidden_content") or []),
                    enabled=bool(item.get("enabled", True)),
                )
            )
        if args.json:
            json_print({"role_ids": imported})
        else:
            print("\n".join(imported))
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
            matches.append({"match_id": match_id, "material_id": material["id"], **match})
        if args.json:
            json_print({"matches": matches})
        else:
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

    raise ValueError(args.material_command)


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
        if args.command == "adb":
            return handle_adb(args)
        if args.command == "content":
            store.init_db()
            return handle_content(args, store)
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
    if getattr(args, "collect_command", None) in {"catalog", "mxnzp-call", "douyin-cookie", "douyin-login-cookie"}:
        return False
    if getattr(args, "collect_command", None) == "author" and getattr(args, "author_command", None) in {"list", "videos"}:
        return False
    return True


def _build_collection_tools(provider: str):
    if provider == "mxnzp":
        return build_mxnzp_douyin_registry()
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
        matches.append({"match_id": match_id, "material_id": material["id"], "role_id": role["id"], **match})
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
