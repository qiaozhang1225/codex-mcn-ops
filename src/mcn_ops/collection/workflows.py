from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..store import Store
from .douyin_login_cookie import login_and_fetch_douyin_cookie
from .mock_tools import build_mock_source_registry
from .mxnzp_client import MxnzpConfig, MxnzpConfigError, MxnzpDouyinProClient
from .mxnzp_tools import build_mxnzp_douyin_registry
from .runner import (
    CollectionConfig,
    TopicCollectionRunner,
    engagement_score,
    metric_value,
    request_fingerprint,
)
from .understanding import build_material_understanding, validate_understanding


LOCAL_UNDERSTANDING_PROVIDER = "local-rules"
LOCAL_UNDERSTANDING_MODEL = "material-understanding-rules-v2"
TARGET_UNDERSTANDING_PROVIDER = "codex-agent"
TARGET_UNDERSTANDING_MODEL = "gpt-5-codex"


@dataclass
class CollectionPolicy:
    viral_like_floor: int = 10000
    min_duration_seconds: int = 20
    max_duration_seconds: int = 300
    super_like_threshold: int = 100000
    max_search_pages: int = 3
    page_size: int = 10
    stop_after_nonviral_pages: int = 2


class CollectionTaskOrchestrator:
    def __init__(self, store: Store) -> None:
        self.store = store

    def run_keyword_task(
        self,
        *,
        topic: str,
        target_count: int,
        policy: CollectionPolicy | None = None,
        tool_provider: str = "mock",
        keywords: list[str] | None = None,
        related_keywords: list[str] | None = None,
        role_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        topic = topic.strip()
        if not topic:
            raise ValueError("--topic is required")
        if target_count < 1:
            raise ValueError("--target-count must be >= 1")
        role_profile = self.store.get_ip_role(role_id) if role_id else None
        command = f"collect task keyword --topic {topic} --target-count {target_count}"
        parsed = {
            "entrypoint": "keyword",
            "topic": topic,
            "target_count": target_count,
            "tool_provider": tool_provider,
            "role_id": role_id,
            "keywords": _unique_strings([topic, *(keywords or [])]),
            "related_keywords": _unique_strings(related_keywords or []),
            "policy": asdict(policy),
            "target_understanding": _target_understanding(),
        }
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=command,
                target_scope="keyword",
                target_count_per_role=target_count,
                topic=topic,
                parsed=parsed,
            )
        tools = build_mxnzp_douyin_registry(include_user_post_tools=False) if tool_provider == "mxnzp" else build_mock_source_registry()
        runner = TopicCollectionRunner(tools, self.store)
        queue = _unique_strings([topic, *(keywords or []), *(related_keywords or []), *_role_keywords(role_profile)])
        exhausted_keywords: list[str] = []
        run_summaries: list[dict[str, Any]] = []
        error: str | None = None
        try:
            while _task_saved_count(self.build_task_report(task_id)) < target_count and queue:
                keyword = queue.pop(0)
                if keyword in exhausted_keywords:
                    continue
                remaining = max(1, target_count - _task_saved_count(self.build_task_report(task_id)))
                result = runner.run(
                    CollectionConfig(
                        topic=keyword,
                        target_count=remaining,
                        like_floor=policy.viral_like_floor,
                        super_like_threshold=policy.super_like_threshold,
                        min_duration_seconds=policy.min_duration_seconds,
                        max_duration_seconds=policy.max_duration_seconds,
                        tool_provider=tool_provider,
                        max_search_pages=policy.max_search_pages,
                        page_size=policy.page_size,
                        task_id=task_id,
                        role_id=role_id,
                        role_profile=role_profile,
                        search_keywords=[keyword],
                        understanding_provider=LOCAL_UNDERSTANDING_PROVIDER,
                        understanding_model=LOCAL_UNDERSTANDING_MODEL,
                    )
                )
                exhausted_keywords.append(keyword)
                run_summaries.append(result.to_dict())
                report = self.build_task_report(task_id)
                queue.extend(
                    keyword
                    for keyword in _next_keywords_from_report(report)
                    if keyword not in exhausted_keywords and keyword not in queue
                )
            report = self.build_task_report(task_id)
            saved_count = _task_saved_count(report)
            status = "completed" if saved_count >= target_count else "partial"
            summary = {
                "entrypoint": "keyword",
                "target_count": target_count,
                "saved_count": saved_count,
                "remaining_count": max(target_count - saved_count, 0),
                "exhausted_keywords": exhausted_keywords,
                "runs": run_summaries,
                "understanding": report["understanding_summary"],
            }
            self.store.finish_collection_task(task_id, status, summary)
            return self.build_task_report(task_id)
        except Exception as exc:
            error = str(exc)
            self.store.finish_collection_task(
                task_id,
                "failed",
                {"entrypoint": "keyword", "runs": run_summaries, "error": error},
                error=error,
            )
            raise

    def run_author_task(
        self,
        *,
        name: str | None = None,
        sec_uid: str | None = None,
        policy: CollectionPolicy | None = None,
        like_floor: int | None = None,
        materialize_top: int = 0,
        max_pages: int = 0,
        sort_type: int = 1,
        skip_expand: bool = False,
        login_cookie: bool = False,
        no_cache: bool = False,
        refresh_existing_understanding: bool = False,
        task_id: str | None = None,
        finish_task: bool = True,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        floor = like_floor if like_floor is not None else policy.viral_like_floor
        label = name or sec_uid or "douyin_author"
        parsed = {
            "entrypoint": "author",
            "name": name,
            "sec_uid": sec_uid,
            "like_floor": floor,
            "materialize_top": materialize_top,
            "max_pages": max_pages,
            "sort_type": sort_type,
            "skip_expand": skip_expand,
            "policy": asdict(policy),
            "target_understanding": _target_understanding(),
        }
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=f"collect task author --name {label} --like-floor {floor}",
                target_scope="author",
                target_count_per_role=materialize_top,
                topic=f"{label} 爆款文案",
                parsed=parsed,
            )
        run_id = self.store.create_collection_run(
            task_id=task_id,
            role_id=None,
            topic=f"{label} 爆款文案",
            target_count=materialize_top,
            like_floor=floor,
            super_like_threshold=policy.super_like_threshold,
            tool_provider="mxnzp_author_task",
        )
        materialized: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        expand_summary: dict[str, Any] = {"skipped": skip_expand}
        try:
            client: MxnzpDouyinProClient | None = None
            author = self._resolve_author(sec_uid=sec_uid, name=name)
            if author is None and skip_expand:
                raise KeyError(f"douyin author not found: {label}")
            if author is None:
                client = self._build_mxnzp_client(login_cookie=login_cookie)
                author = self._search_and_store_author(client, run_id=run_id, name=name or label, use_cache=not no_cache)
            if author is None:
                raise KeyError(f"douyin author not found: {label}")
            if not skip_expand:
                client = client or self._build_mxnzp_client(login_cookie=login_cookie)
                expand_summary = self._expand_author_videos(
                    client,
                    run_id=run_id,
                    author=author,
                    like_floor=floor,
                    min_duration_seconds=policy.min_duration_seconds,
                    max_duration_seconds=policy.max_duration_seconds,
                    max_pages=max_pages,
                    sort_type=sort_type,
                    stop_after_nonviral_pages=policy.stop_after_nonviral_pages,
                    use_cache=not no_cache,
                )
            materialized, skipped = self._materialize_author_videos(
                run_id=run_id,
                task_id=task_id,
                author=author,
                like_floor=floor,
                min_duration_seconds=policy.min_duration_seconds,
                max_duration_seconds=policy.max_duration_seconds,
                materialize_top=materialize_top,
                client=client,
                use_cache=not no_cache,
                refresh_existing_understanding=refresh_existing_understanding,
            )
            run_status = "completed" if materialized else "empty"
            self.store.finish_collection_run(
                run_id,
                run_status,
                {
                    "entrypoint": "author",
                    "author": _author_summary(author),
                    "expand": expand_summary,
                    "materialized": materialized,
                    "skipped": skipped,
                },
            )
            if finish_task:
                report = self.build_task_report(task_id)
                self.store.finish_collection_task(
                    task_id,
                    "completed" if materialized else "empty",
                    {
                        "entrypoint": "author",
                        "author": _author_summary(author),
                        "materialized_count": len(materialized),
                        "skipped_count": len(skipped),
                        "understanding": report["understanding_summary"],
                    },
                )
            return self.build_task_report(task_id)
        except Exception as exc:
            self.store.finish_collection_run(
                run_id,
                "failed",
                {"entrypoint": "author", "materialized": materialized, "skipped": skipped, "expand": expand_summary},
                error=str(exc),
            )
            if finish_task:
                self.store.finish_collection_task(
                    task_id,
                    "failed",
                    {"entrypoint": "author", "materialized": materialized, "skipped": skipped, "error": str(exc)},
                    error=str(exc),
                )
            raise

    def run_discovered_authors_task(
        self,
        *,
        min_appearances: int = 2,
        top_authors: int = 10,
        like_floor: int | None = None,
        materialize_top: int = 0,
        max_pages: int = 0,
        sort_type: int = 1,
        skip_expand: bool = False,
        login_cookie: bool = False,
        no_cache: bool = False,
        dry_run: bool = False,
        policy: CollectionPolicy | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        policy = policy or CollectionPolicy()
        floor = like_floor if like_floor is not None else policy.viral_like_floor
        discovered = discover_source_authors(self.store, min_appearances=min_appearances)[:top_authors]
        parsed = {
            "entrypoint": "discovered_authors",
            "min_appearances": min_appearances,
            "top_authors": top_authors,
            "like_floor": floor,
            "materialize_top": materialize_top,
            "max_pages": max_pages,
            "sort_type": sort_type,
            "skip_expand": skip_expand,
            "dry_run": dry_run,
            "authors": discovered,
            "policy": asdict(policy),
            "target_understanding": _target_understanding(),
        }
        if task_id is None:
            task_id = self.store.create_collection_task(
                command=f"collect task discover-authors --min-appearances {min_appearances} --like-floor {floor}",
                target_scope="discovered_authors",
                target_count_per_role=materialize_top,
                topic="discovered source authors",
                parsed=parsed,
            )
        if dry_run:
            self.store.finish_collection_task(
                task_id,
                "completed",
                {"entrypoint": "discovered_authors", "authors": discovered, "dry_run": True},
            )
            return self.build_task_report(task_id)
        author_results: list[dict[str, Any]] = []
        try:
            for author in discovered:
                report = self.run_author_task(
                    sec_uid=author.get("author_sec_uid"),
                    name=author.get("author_name"),
                    policy=policy,
                    like_floor=floor,
                    materialize_top=materialize_top,
                    max_pages=max_pages,
                    sort_type=sort_type,
                    skip_expand=skip_expand,
                    login_cookie=login_cookie,
                    no_cache=no_cache,
                    task_id=task_id,
                    finish_task=False,
                )
                author_results.append(
                    {
                        "author_sec_uid": author.get("author_sec_uid"),
                        "author_name": author.get("author_name"),
                        "saved_count": _task_saved_count(report),
                    }
                )
            report = self.build_task_report(task_id)
            self.store.finish_collection_task(
                task_id,
                "completed",
                {
                    "entrypoint": "discovered_authors",
                    "authors": discovered,
                    "author_results": author_results,
                    "understanding": report["understanding_summary"],
                },
            )
            return self.build_task_report(task_id)
        except Exception as exc:
            self.store.finish_collection_task(
                task_id,
                "failed",
                {"entrypoint": "discovered_authors", "authors": discovered, "author_results": author_results, "error": str(exc)},
                error=str(exc),
            )
            raise

    def resume_task(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_collection_task(task_id)
        if not task:
            raise KeyError(f"collection task not found: {task_id}")
        parsed = task.get("parsed") or {}
        policy = CollectionPolicy(**{**asdict(CollectionPolicy()), **(parsed.get("policy") or {})})
        entrypoint = parsed.get("entrypoint") or task.get("target_scope")
        if entrypoint == "keyword":
            return self.run_keyword_task(
                topic=str(parsed.get("topic") or task.get("topic") or ""),
                target_count=int(parsed.get("target_count") or task.get("target_count_per_role") or 1),
                policy=policy,
                tool_provider=str(parsed.get("tool_provider") or "mock"),
                keywords=list(parsed.get("keywords") or []),
                related_keywords=list(parsed.get("related_keywords") or []),
                role_id=parsed.get("role_id"),
                task_id=task_id,
            )
        if entrypoint == "author":
            return self.run_author_task(
                name=parsed.get("name"),
                sec_uid=parsed.get("sec_uid"),
                policy=policy,
                like_floor=parsed.get("like_floor"),
                materialize_top=int(parsed.get("materialize_top") or 0),
                max_pages=int(parsed.get("max_pages") or 0),
                sort_type=int(parsed.get("sort_type") or 1),
                skip_expand=bool(parsed.get("skip_expand")),
                task_id=task_id,
            )
        if entrypoint == "discovered_authors":
            return self.run_discovered_authors_task(
                min_appearances=int(parsed.get("min_appearances") or 2),
                top_authors=int(parsed.get("top_authors") or 10),
                like_floor=parsed.get("like_floor"),
                materialize_top=int(parsed.get("materialize_top") or 0),
                max_pages=int(parsed.get("max_pages") or 0),
                sort_type=int(parsed.get("sort_type") or 1),
                skip_expand=bool(parsed.get("skip_expand")),
                dry_run=bool(parsed.get("dry_run")),
                policy=policy,
                task_id=task_id,
            )
        raise ValueError(f"unsupported task entrypoint: {entrypoint}")

    def build_task_report(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_collection_task(task_id)
        if not task:
            raise KeyError(f"collection task not found: {task_id}")
        runs = self.store.list_collection_runs(task_id=task_id)
        candidates = self.store.list_collection_candidates(task_id=task_id)
        created_materials = self.store.list_collected_materials(task_id=task_id)
        material_by_id = {material["id"]: material for material in created_materials}
        existing_reused: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.get("status") != "existing_reused" or not candidate.get("material_id"):
                continue
            material = self.store.get_collected_material(str(candidate["material_id"]))
            if material and material["id"] not in material_by_id:
                material_by_id[material["id"]] = material
                existing_reused.append(material)
        for run in runs:
            summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
            for item in summary.get("materialized") or []:
                if not isinstance(item, dict) or not str(item.get("status") or "").startswith("existing_"):
                    continue
                material_id = item.get("material_id")
                if not material_id or material_id in material_by_id:
                    continue
                material = self.store.get_collected_material(str(material_id))
                if material:
                    material_by_id[material["id"]] = material
                    existing_reused.append(material)
        saved_materials = list(material_by_id.values())
        skipped = [
            candidate
            for candidate in candidates
            if candidate.get("status") in {"rejected", "below_threshold", "skipped"}
        ]
        source_authors = discover_source_authors_from_records(saved_materials, candidates)
        if not source_authors and isinstance((task.get("parsed") or {}).get("authors"), list):
            source_authors = list((task.get("parsed") or {}).get("authors") or [])
        return {
            "task": task,
            "runs": runs,
            "target_count": _target_count(task),
            "saved_count": len(saved_materials),
            "created_material_count": len(created_materials),
            "existing_reused_count": len(existing_reused),
            "remaining_count": max(_target_count(task) - len(saved_materials), 0) if _target_count(task) else 0,
            "saved_materials": saved_materials,
            "skipped_candidates": skipped,
            "source_authors_discovered": source_authors,
            "understanding_summary": _understanding_summary(saved_materials),
            "next_recommended_keywords": _next_keywords_from_materials(saved_materials),
            "next_recommended_authors": _next_authors_from_materials(saved_materials),
            "api_call_summary": self.store.task_call_summary(task_id),
        }

    def _build_mxnzp_client(self, *, login_cookie: bool) -> MxnzpDouyinProClient:
        try:
            config = MxnzpConfig.from_env()
        except MxnzpConfigError as exc:
            raise MxnzpConfigError(
                f"{exc} Run `mcn collect douyin-login-cookie --write-env` when a logged-in Douyin cookie is required."
            ) from exc
        if login_cookie and not config.douyin_cookie:
            login_result = login_and_fetch_douyin_cookie()
            if not login_result.cookie_valid:
                raise MxnzpConfigError(login_result.error or "failed to fetch a valid logged-in Douyin cookie")
            config.douyin_cookie = login_result.cookie
        return MxnzpDouyinProClient(config)

    def _call_mxnzp(
        self,
        client: MxnzpDouyinProClient,
        *,
        run_id: str,
        method_key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        arguments = {"params": params or {}, "body": body or {}}
        fingerprint = request_fingerprint(method_key, arguments)
        started = time.monotonic()
        if use_cache:
            cached = self.store.get_cached_collection_call(fingerprint)
            if cached is not None:
                self.store.log_mxnzp_call(
                    run_id=run_id,
                    tool_name=method_key,
                    request_fingerprint=fingerprint,
                    status="ok",
                    duration_ms=_elapsed_ms(started),
                    cache_hit=True,
                )
                cached = dict(cached)
                cached["cache_hit"] = True
                return cached
        try:
            result = client.call(method_key, params=params, body=body, use_cache=use_cache)
        except Exception as exc:
            self.store.log_mxnzp_call(
                run_id=run_id,
                tool_name=method_key,
                request_fingerprint=fingerprint,
                status="error",
                duration_ms=_elapsed_ms(started),
                cache_hit=False,
                error=str(exc),
            )
            raise
        status = "ok" if result.get("ok", True) else "error"
        if use_cache and status == "ok":
            self.store.put_cached_collection_call(method_key, fingerprint, result)
        self.store.log_mxnzp_call(
            run_id=run_id,
            tool_name=method_key,
            request_fingerprint=fingerprint,
            status=status,
            duration_ms=_elapsed_ms(started),
            cache_hit=bool(result.get("cache_hit")),
            error=str(result.get("error")) if status == "error" and result.get("error") else None,
        )
        return result

    def _resolve_author(self, *, sec_uid: str | None, name: str | None) -> dict[str, Any] | None:
        if sec_uid:
            return self.store.get_douyin_author(sec_uid)
        if not name:
            return None
        matches = [author for author in self.store.list_douyin_authors() if author.get("nickname") == name]
        if not matches:
            matches = [author for author in self.store.list_douyin_authors() if name in str(author.get("nickname") or "")]
        if len(matches) > 1:
            names = ", ".join(str(author.get("nickname")) for author in matches[:5])
            raise ValueError(f"multiple douyin authors matched {name!r}: {names}; use --sec-uid")
        return matches[0] if matches else None

    def _search_and_store_author(
        self,
        client: MxnzpDouyinProClient,
        *,
        run_id: str,
        name: str,
        use_cache: bool,
    ) -> dict[str, Any] | None:
        result = self._call_mxnzp(client, run_id=run_id, method_key="user_search", params={"keyword": name}, use_cache=use_cache)
        normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
        items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
        candidates = [item for item in items if isinstance(item, dict)]
        exact = [item for item in candidates if item.get("nickname") == name]
        picked = (exact or candidates)[0] if candidates else None
        if not picked:
            return None
        sec_uid = self.store.upsert_douyin_author(picked, raw=picked.get("raw") if isinstance(picked.get("raw"), dict) else picked)
        return self.store.get_douyin_author(sec_uid)

    def _expand_author_videos(
        self,
        client: MxnzpDouyinProClient,
        *,
        run_id: str,
        author: dict[str, Any],
        like_floor: int,
        min_duration_seconds: int,
        max_duration_seconds: int,
        max_pages: int,
        sort_type: int,
        stop_after_nonviral_pages: int,
        use_cache: bool,
    ) -> dict[str, Any]:
        cursor = ""
        page_limit = max_pages if max_pages > 0 else 1000
        pages: list[dict[str, Any]] = []
        saved_video_ids: list[str] = []
        seen_cursors: set[str] = set()
        nonviral_page_streak = 0
        stop_reason = "max_pages"
        for page_number in range(1, page_limit + 1):
            result = self._call_mxnzp(
                client,
                run_id=run_id,
                method_key="user_post",
                params={"userId": author["sec_uid"], "sortType": sort_type, "cursor": cursor},
                use_cache=use_cache,
            )
            normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
            items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
            packages = normalized.get("source_packages") if isinstance(normalized.get("source_packages"), list) else []
            page_videos: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                source_package = packages[index] if index < len(packages) and isinstance(packages[index], dict) else {}
                video = _author_video_from_normalized_item(item, source_package)
                page_videos.append(video)
                saved_video_ids.append(
                    self.store.upsert_douyin_author_video(
                        author["sec_uid"],
                        video,
                        raw=item.get("raw") if isinstance(item.get("raw"), dict) else None,
                    )
                )
            paging = result.get("paging") if isinstance(result.get("paging"), dict) else {}
            next_cursor = str(paging.get("cursor") or "")
            has_next = bool(paging.get("has_next"))
            page_viral_count = len(
                _rank_author_videos(
                    page_videos,
                    like_floor=like_floor,
                    min_duration_seconds=min_duration_seconds,
                    max_duration_seconds=max_duration_seconds,
                )
            )
            nonviral_page_streak = nonviral_page_streak + 1 if page_viral_count == 0 else 0
            pages.append(
                {
                    "page": page_number,
                    "fetched_count": len(items),
                    "saved_count": len(page_videos),
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
            if stop_after_nonviral_pages > 0 and nonviral_page_streak >= stop_after_nonviral_pages:
                stop_reason = "nonviral_page_streak"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return {
            "pages": pages,
            "saved_count": len(set(saved_video_ids)),
            "total_stored_count": len(self.store.list_douyin_author_videos(author["sec_uid"])),
            "stop_reason": stop_reason,
        }

    def _materialize_author_videos(
        self,
        *,
        run_id: str,
        task_id: str,
        author: dict[str, Any],
        like_floor: int,
        min_duration_seconds: int,
        max_duration_seconds: int,
        materialize_top: int,
        client: MxnzpDouyinProClient | None,
        use_cache: bool,
        refresh_existing_understanding: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        ranked = _rank_author_videos(
            self.store.list_douyin_author_videos(author["sec_uid"]),
            like_floor=like_floor,
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
        )
        selected = ranked[:materialize_top] if materialize_top > 0 else ranked
        materialized: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for video in selected:
            existing = _find_collected_material_by_work_id(self.store, str(video.get("work_id") or ""))
            if existing:
                status = "existing_preserved"
                if refresh_existing_understanding:
                    understanding = build_material_understanding(
                        existing,
                        provider=LOCAL_UNDERSTANDING_PROVIDER,
                        model=LOCAL_UNDERSTANDING_MODEL,
                    )
                    validate_understanding(understanding)
                    self.store.update_material_understanding(
                        existing["id"],
                        understanding=understanding,
                        provider=LOCAL_UNDERSTANDING_PROVIDER,
                        model=LOCAL_UNDERSTANDING_MODEL,
                    )
                    self.store.log_material_understanding(
                        run_id=existing.get("run_id") or run_id,
                        material_id=existing["id"],
                        provider=LOCAL_UNDERSTANDING_PROVIDER,
                        model=LOCAL_UNDERSTANDING_MODEL,
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
            client = client or self._build_mxnzp_client(login_cookie=False)
            extract_result = self._call_mxnzp(
                client,
                run_id=run_id,
                method_key="video_to_text_v2",
                body={"url": source_url},
                use_cache=use_cache,
            )
            normalized = extract_result.get("normalized") if isinstance(extract_result.get("normalized"), dict) else {}
            transcript_text = str(normalized.get("text") or (normalized.get("source_package") or {}).get("transcript_text") or "").strip()
            if not transcript_text:
                skipped.append({"work_id": video.get("work_id"), "title": video.get("title"), "reason": "empty_transcript"})
                continue
            source_package = _source_package_from_author_video(author, video)
            source_package["task_id"] = task_id
            extract_package = normalized.get("source_package") if isinstance(normalized.get("source_package"), dict) else {}
            _merge_source_package(source_package, extract_package)
            source_package["transcript_text"] = transcript_text
            understanding = build_material_understanding(
                source_package,
                provider=LOCAL_UNDERSTANDING_PROVIDER,
                model=LOCAL_UNDERSTANDING_MODEL,
            )
            validate_understanding(understanding)
            source_package["material_understanding"] = understanding
            source_package["understanding_status"] = str(understanding.get("status") or "draft_local_understanding")
            material_id = self.store.insert_collected_material(
                run_id=run_id,
                source_package=source_package,
                material_understanding=understanding,
                raw={"author": _author_summary(author), "author_video": video, "video_to_text_v2_result": extract_result},
            )
            self.store.log_material_understanding(
                run_id=run_id,
                material_id=material_id,
                provider=LOCAL_UNDERSTANDING_PROVIDER,
                model=LOCAL_UNDERSTANDING_MODEL,
                status="ok",
                output=understanding,
            )
            materialized.append(
                {
                    "material_id": material_id,
                    "work_id": video.get("work_id"),
                    "title": video.get("title"),
                    "status": "created_draft_understanding",
                }
            )
        return materialized, skipped


def discover_source_authors(store: Store, *, min_appearances: int = 2) -> list[dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    _add_material_authors(authors, store.list_collected_materials())
    _add_candidate_authors(authors, store.list_collection_candidates())
    for author in store.list_douyin_authors():
        videos = store.list_douyin_author_videos(author["sec_uid"])
        key = _author_key(author.get("sec_uid"), author.get("nickname"))
        record = authors.setdefault(key, _blank_author_record(author.get("sec_uid"), author.get("nickname")))
        record["author_profile_url"] = record.get("author_profile_url") or author.get("profile_url")
        record["follower_count"] = author.get("follower_count")
        record["has_profile"] = True
        for video in videos:
            score = _score_from_metrics(video.get("metrics") or {})
            record["appearances"] += 1
            record["scores"].append(score)
    for record in authors.values():
        scores = record.pop("scores", [])
        record["max_engagement_score"] = max(scores) if scores else 0
        record["avg_engagement_score"] = int(sum(scores) / len(scores)) if scores else 0
    return [
        record
        for record in sorted(
            authors.values(),
            key=lambda item: (
                int(item.get("appearances") or 0),
                int(item.get("max_engagement_score") or 0),
                int(item.get("avg_engagement_score") or 0),
                bool(item.get("has_profile")),
                int(item.get("follower_count") or 0),
            ),
            reverse=True,
        )
        if int(record.get("appearances") or 0) >= min_appearances
    ]


def discover_source_authors_from_records(materials: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    _add_material_authors(authors, materials)
    _add_candidate_authors(authors, candidates)
    for record in authors.values():
        scores = record.pop("scores", [])
        record["max_engagement_score"] = max(scores) if scores else 0
        record["avg_engagement_score"] = int(sum(scores) / len(scores)) if scores else 0
    return sorted(
        authors.values(),
        key=lambda item: (
            int(item.get("appearances") or 0),
            int(item.get("max_engagement_score") or 0),
            int(item.get("avg_engagement_score") or 0),
        ),
        reverse=True,
    )


def format_task_show(report: dict[str, Any]) -> str:
    task = report["task"]
    understanding = report["understanding_summary"]
    return "\n".join(
        [
            f"Task {task['id']} [{task['status']}]",
            f"scope={task['target_scope']} topic={task.get('topic') or ''}",
            f"saved={report['saved_count']} created={report['created_material_count']} reused={report['existing_reused_count']} remaining={report['remaining_count']}",
            f"runs={len(report['runs'])} skipped={len(report['skipped_candidates'])} api_calls={report['api_call_summary']['total_calls']} cache_hits={report['api_call_summary']['cache_hits']}",
            f"understanding final={understanding['final_codex_count']} draft={understanding['draft_local_count']} pending_codex={understanding['pending_codex_understanding_count']}",
        ]
    )


def format_task_report_markdown(report: dict[str, Any]) -> str:
    task = report["task"]
    lines = [
        f"# Collection Task Report: {task['id']}",
        "",
        f"- scope: {task['target_scope']}",
        f"- status: {task['status']}",
        f"- topic: {task.get('topic') or ''}",
        f"- target_count: {report['target_count']}",
        f"- saved_count: {report['saved_count']}",
        f"- created_material_count: {report['created_material_count']}",
        f"- existing_reused_count: {report['existing_reused_count']}",
        f"- remaining_count: {report['remaining_count']}",
        "",
        "## Understanding",
        "",
    ]
    understanding = report["understanding_summary"]
    lines.extend(
        [
            f"- final_codex_count: {understanding['final_codex_count']}",
            f"- draft_local_count: {understanding['draft_local_count']}",
            f"- pending_codex_understanding_count: {understanding['pending_codex_understanding_count']}",
        ]
    )
    if understanding["pending_codex_understanding_count"]:
        lines.append("- note: 有素材仍是本地规则草稿，待 Codex 深度理解。")
    lines.extend(["", "## Saved Materials", ""])
    for material in report["saved_materials"]:
        lines.append(
            f"- {material['id']} | {material.get('understanding_provider')}/{material.get('understanding_model')}/{material.get('understanding_status')} | "
            f"{material.get('title') or material.get('clean_title') or ''}"
        )
    lines.extend(["", "## Skipped Candidates", ""])
    for candidate in report["skipped_candidates"][:50]:
        lines.append(
            f"- {candidate.get('status')} | {candidate.get('skip_reason') or ''} | {candidate.get('title') or ''}"
        )
    lines.extend(["", "## Source Authors Discovered", ""])
    for author in report["source_authors_discovered"][:30]:
        lines.append(
            f"- {author.get('author_name') or ''} | sec_uid={author.get('author_sec_uid') or ''} | appearances={author.get('appearances')}"
        )
    lines.extend(["", "## Next Recommendations", ""])
    lines.append("- keywords: " + ", ".join(report["next_recommended_keywords"][:20]))
    lines.append(
        "- authors: "
        + ", ".join(
            str(author.get("author_name") or author.get("author_sec_uid") or "")
            for author in report["next_recommended_authors"][:20]
        )
    )
    lines.extend(["", "## API Calls", ""])
    call_summary = report["api_call_summary"]
    lines.append(f"- total_calls: {call_summary['total_calls']}")
    lines.append(f"- cache_hits: {call_summary['cache_hits']}")
    for item in call_summary["by_tool"]:
        lines.append(f"- {item['tool_name']} {item['status']}: {item['count']} calls, {item['cache_hits']} cache hits")
    return "\n".join(lines).rstrip() + "\n"


def _author_summary(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "sec_uid": author.get("sec_uid"),
        "uid": author.get("uid"),
        "douyin_id": author.get("douyin_id"),
        "nickname": author.get("nickname"),
        "profile_url": author.get("profile_url"),
        "follower_count": author.get("follower_count"),
        "aweme_count": author.get("aweme_count"),
        "total_favorited": author.get("total_favorited"),
    }


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
    source_package = dict(video.get("source_package") or {})
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    defaults = {
        "source_type": "mxnzp_douyin_author",
        "source_platform": "douyin",
        "source_link": video.get("source_url"),
        "title": video.get("title"),
        "clean_title": video.get("title"),
        "platform_caption": video.get("title"),
        "caption_text": video.get("caption_text") or video.get("title"),
        "hashtags": video.get("hashtags") or [],
        "author_name": author.get("nickname"),
        "author_sec_uid": author.get("sec_uid"),
        "author_profile_url": author.get("profile_url"),
        "author_douyin_id": author.get("douyin_id"),
        "work_id": video.get("work_id"),
        "post_time": video.get("post_time"),
        "duration_ms": video.get("duration_ms"),
        "cover_url": video.get("cover_url"),
        "public_metrics": {
            "digg_count": metrics.get("digg_count") or video.get("likes"),
            "collect_count": metrics.get("collect_count") or video.get("collects"),
            "comment_count": metrics.get("comment_count") or video.get("comments"),
            "share_count": metrics.get("share_count") or video.get("shares"),
            "play_count": metrics.get("play_count"),
        },
        "collection_notes": ["author_hot_work"],
    }
    for key, value in defaults.items():
        if source_package.get(key) in (None, "", []):
            source_package[key] = value
    return source_package


def _merge_source_package(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if value in (None, "", []):
            continue
        if key in {"title", "clean_title", "platform_caption", "caption_text"} and base.get(key):
            continue
        if base.get(key) in (None, "", []):
            base[key] = value


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
                "source_package": video.get("source_package") if isinstance(video.get("source_package"), dict) else {},
                "hashtags": video.get("hashtags") or [],
                "caption_text": video.get("caption_text"),
                "cover_url": video.get("cover_url"),
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


def _target_understanding() -> dict[str, str]:
    return {"provider": TARGET_UNDERSTANDING_PROVIDER, "model": TARGET_UNDERSTANDING_MODEL, "status": "success"}


def _target_count(task: dict[str, Any]) -> int:
    value = task.get("target_count_per_role")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _task_saved_count(report: dict[str, Any]) -> int:
    return int(report.get("saved_count") or 0)


def _understanding_summary(materials: list[dict[str, Any]]) -> dict[str, Any]:
    final_codex_count = 0
    draft_local_count = 0
    for material in materials:
        provider = str(material.get("understanding_provider") or "")
        model = str(material.get("understanding_model") or "")
        status = str(material.get("understanding_status") or "")
        if provider == TARGET_UNDERSTANDING_PROVIDER and model == TARGET_UNDERSTANDING_MODEL and status == "success":
            final_codex_count += 1
        elif provider == LOCAL_UNDERSTANDING_PROVIDER or status == "draft_local_understanding":
            draft_local_count += 1
    return {
        "total": len(materials),
        "final_codex_count": final_codex_count,
        "draft_local_count": draft_local_count,
        "pending_codex_understanding_count": max(len(materials) - final_codex_count, 0),
    }


def _next_keywords_from_report(report: dict[str, Any]) -> list[str]:
    return _unique_strings(report.get("next_recommended_keywords") or [])


def _next_keywords_from_materials(materials: list[dict[str, Any]]) -> list[str]:
    keywords: list[str] = []
    for material in materials:
        keywords.extend(material.get("next_collection_keywords") or [])
        understanding = material.get("material_understanding") or {}
        keywords.extend(understanding.get("next_collection_keywords") or [])
    return _unique_strings(keywords)


def _next_authors_from_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    authors = discover_source_authors_from_records(materials, [])
    return [author for author in authors if author.get("author_sec_uid") or author.get("author_name")]


def _role_keywords(role_profile: dict[str, Any] | None) -> list[str]:
    if not role_profile:
        return []
    return _unique_strings(
        [
            *(role_profile.get("search_keywords") or []),
            *(role_profile.get("target_directions") or []),
            *(role_profile.get("preferred_content") or []),
        ]
    )


def _add_material_authors(authors: dict[str, dict[str, Any]], materials: list[dict[str, Any]]) -> None:
    for material in materials:
        sec_uid = material.get("author_sec_uid")
        name = material.get("author_name")
        if not sec_uid and not name:
            continue
        key = _author_key(sec_uid, name)
        record = authors.setdefault(key, _blank_author_record(sec_uid, name))
        record["author_profile_url"] = record.get("author_profile_url") or material.get("author_profile_url")
        record["appearances"] += 1
        record["scores"].append(_score_from_metrics(material.get("metrics") or {}))


def _add_candidate_authors(authors: dict[str, dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        source_package = candidate.get("source_package") if isinstance(candidate.get("source_package"), dict) else {}
        sec_uid = source_package.get("author_sec_uid")
        name = source_package.get("author_name") or candidate.get("author_name")
        if not sec_uid and not name:
            continue
        key = _author_key(sec_uid, name)
        record = authors.setdefault(key, _blank_author_record(sec_uid, name))
        record["author_profile_url"] = record.get("author_profile_url") or source_package.get("author_profile_url")
        record["appearances"] += 1
        record["scores"].append(_score_from_metrics(candidate.get("metrics") or source_package.get("public_metrics") or {}))


def _blank_author_record(sec_uid: Any, name: Any) -> dict[str, Any]:
    return {
        "author_sec_uid": sec_uid,
        "author_name": name,
        "author_profile_url": None,
        "appearances": 0,
        "scores": [],
        "max_engagement_score": 0,
        "avg_engagement_score": 0,
        "has_profile": False,
        "follower_count": None,
    }


def _author_key(sec_uid: Any, name: Any) -> str:
    return str(sec_uid or name or "").strip()


def _score_from_metrics(metrics: dict[str, Any]) -> int:
    return engagement_score({"source_package": {"public_metrics": metrics}})


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
