from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..store import Store
from .tools import ToolExecutionError, ToolRegistry
from .understanding import build_material_understanding, validate_understanding


@dataclass
class CollectionConfig:
    topic: str
    target_count: int = 3
    like_floor: int = 5000
    super_like_threshold: int = 100000
    min_duration_seconds: int = 20
    max_duration_seconds: int = 300
    tool_provider: str = "mock"
    max_search_pages: int = 3
    page_size: int = 5
    task_id: str | None = None
    role_id: str | None = None
    role_profile: dict[str, Any] | None = None
    search_keywords: list[str] = field(default_factory=list)
    understanding_provider: str = "local-rules"
    understanding_model: str = "material-understanding-rules-v2"
    reuse_existing: bool = True


@dataclass
class CollectionResult:
    run_id: str
    topic: str
    status: str
    saved_material_ids: list[str] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    candidate_count: int = 0
    selected_count: int = 0
    threshold_mode: str = "floor"
    repeated_author_clues: list[dict[str, Any]] = field(default_factory=list)
    call_summary: dict[str, Any] = field(default_factory=dict)
    understanding_success_count: int = 0
    existing_reused_material_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "topic": self.topic,
            "status": self.status,
            "saved_count": len(self.saved_material_ids),
            "saved_material_ids": self.saved_material_ids,
            "skipped": self.skipped,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "threshold_mode": self.threshold_mode,
            "repeated_author_clues": self.repeated_author_clues,
            "mxnzp_call_summary": self.call_summary,
            "understanding_success_count": self.understanding_success_count,
            "existing_reused_count": len(self.existing_reused_material_ids),
            "existing_reused_material_ids": self.existing_reused_material_ids,
        }


class LoggedToolExecutor:
    def __init__(self, tools: ToolRegistry, store: Store, run_id: str) -> None:
        self.tools = tools
        self.store = store
        self.run_id = run_id

    def run(self, tool_name: str, arguments: dict[str, Any], use_cache: bool = True) -> dict[str, Any]:
        fingerprint = request_fingerprint(tool_name, arguments)
        started = time.monotonic()
        if use_cache:
            cached = self.store.get_cached_collection_call(fingerprint)
            if cached is not None:
                self.store.log_mxnzp_call(
                    run_id=self.run_id,
                    tool_name=tool_name,
                    request_fingerprint=fingerprint,
                    status="ok",
                    duration_ms=_elapsed_ms(started),
                    cache_hit=True,
                )
                return cached

        try:
            result = self.tools.run(tool_name, arguments)
        except ToolExecutionError as exc:
            self.store.log_mxnzp_call(
                run_id=self.run_id,
                tool_name=tool_name,
                request_fingerprint=fingerprint,
                status="error",
                duration_ms=_elapsed_ms(started),
                cache_hit=False,
                error=str(exc),
            )
            raise

        status = "ok" if result.get("ok", True) else "error"
        if use_cache and status == "ok":
            self.store.put_cached_collection_call(tool_name, fingerprint, result)
        self.store.log_mxnzp_call(
            run_id=self.run_id,
            tool_name=tool_name,
            request_fingerprint=fingerprint,
            status=status,
            duration_ms=_elapsed_ms(started),
            cache_hit=bool(result.get("cache_hit")),
            error=str(result.get("error")) if status == "error" and result.get("error") else None,
        )
        return result


class TopicCollectionRunner:
    def __init__(self, tools: ToolRegistry, store: Store) -> None:
        self.tools = tools
        self.store = store

    def run(self, config: CollectionConfig) -> CollectionResult:
        topic = config.topic.strip()
        if not topic:
            raise ValueError("topic is required.")
        if config.target_count < 1:
            raise ValueError("target_count must be >= 1.")

        run_id = self.store.create_collection_run(
            task_id=config.task_id,
            role_id=config.role_id,
            topic=topic,
            target_count=config.target_count,
            like_floor=config.like_floor,
            super_like_threshold=config.super_like_threshold,
            tool_provider=config.tool_provider,
        )
        executor = LoggedToolExecutor(self.tools, self.store, run_id)
        try:
            discovered = dedupe_candidates(self._search_candidates(executor, config))
            for candidate in discovered:
                candidate = self._candidate_with_context(candidate, config)
                self.store.upsert_collection_candidate(run_id, candidate, status="discovered")

            duration_candidates, duration_skipped = filter_candidates_for_duration(
                discovered,
                min_seconds=config.min_duration_seconds,
                max_seconds=config.max_duration_seconds,
            )
            role_candidates, role_skipped = filter_candidates_for_role(duration_candidates, config.role_profile)
            candidates, relevance_skipped = filter_candidates_for_relevance(role_candidates, config.role_profile, topic)
            for skipped in duration_skipped + role_skipped + relevance_skipped:
                matched = _candidate_by_skip(discovered, skipped)
                if matched:
                    self.store.upsert_collection_candidate(
                        run_id,
                        matched,
                        status="rejected",
                        skip_reason=str(skipped.get("reason") or "rejected"),
                        skip_detail=str(skipped.get("detail") or ""),
                    )

            repeated_author_clues = repeated_authors(candidates)
            selected, threshold_mode = select_viral_candidates(
                candidates,
                target_count=config.target_count,
                like_floor=config.like_floor,
                super_like_threshold=config.super_like_threshold,
            )
            selected_keys = {_candidate_key(candidate) for candidate in selected}
            skipped: list[dict[str, Any]] = duration_skipped + role_skipped + relevance_skipped
            for candidate in candidates:
                if _candidate_key(candidate) in selected_keys:
                    self.store.upsert_collection_candidate(
                        run_id,
                        candidate,
                        status="selected",
                        selection_reason=_selection_reason(candidate, threshold_mode),
                        threshold_mode=threshold_mode,
                    )
                else:
                    self.store.upsert_collection_candidate(
                        run_id,
                        candidate,
                        status="below_threshold",
                        skip_reason="below_threshold",
                        skip_detail=_threshold_skip_detail(candidate, config, threshold_mode),
                        threshold_mode=threshold_mode,
                    )

            saved_material_ids: list[str] = []
            existing_reused_material_ids: list[str] = []
            understanding_success_count = 0
            for candidate in selected:
                existing = find_existing_material_for_candidate(self.store, candidate) if config.reuse_existing else None
                if existing:
                    material_id = str(existing["id"])
                    saved_material_ids.append(material_id)
                    existing_reused_material_ids.append(material_id)
                    self.store.upsert_collection_candidate(
                        run_id,
                        candidate,
                        status="existing_reused",
                        selection_reason=_selection_reason(candidate, threshold_mode),
                        skip_reason="existing_material",
                        skip_detail="Matched an existing collected material by work_id, source_url, or title+author.",
                        threshold_mode=threshold_mode,
                        material_id=material_id,
                    )
                    continue
                try:
                    transcript_text, extract_result = self._extract_text(executor, candidate)
                except ToolExecutionError as exc:
                    skipped.append(_skip(candidate, "video_to_text_failed", str(exc)))
                    self.store.upsert_collection_candidate(
                        run_id,
                        candidate,
                        status="skipped",
                        skip_reason="video_to_text_failed",
                        skip_detail=str(exc),
                        threshold_mode=threshold_mode,
                    )
                    continue
                if not transcript_text.strip():
                    skipped.append(_skip(candidate, "video_to_text_empty", "Extracted text is empty."))
                    self.store.upsert_collection_candidate(
                        run_id,
                        candidate,
                        status="skipped",
                        skip_reason="video_to_text_empty",
                        skip_detail="Extracted text is empty.",
                        threshold_mode=threshold_mode,
                    )
                    continue

                source_package = enrich_source_package(
                    source_package=dict(candidate["source_package"]),
                    candidate=candidate,
                    extract_result=extract_result,
                    transcript_text=transcript_text,
                    repeated_author_clues=repeated_author_clues,
                )
                source_package["task_id"] = config.task_id
                source_package["role_id"] = config.role_id
                source_package = self._resolve_short_link(executor, source_package)
                material_understanding = build_material_understanding(
                    source_package,
                    provider=config.understanding_provider,
                    model=config.understanding_model,
                )
                validate_understanding(material_understanding)
                source_package["material_understanding"] = material_understanding
                source_package["understanding_status"] = str(material_understanding.get("status") or "success")
                material_id = self.store.insert_collected_material(
                    run_id=run_id,
                    source_package=source_package,
                    material_understanding=material_understanding,
                    raw={"candidate": candidate.get("raw", {}), "extract_result": extract_result},
                )
                self.store.log_material_understanding(
                    run_id=run_id,
                    material_id=material_id,
                    provider=config.understanding_provider,
                    model=config.understanding_model,
                    status="ok",
                    output=material_understanding,
                )
                understanding_success_count += 1
                saved_material_ids.append(material_id)
                candidate["source_package"] = source_package
                self.store.upsert_collection_candidate(
                    run_id,
                    candidate,
                    status="saved",
                    selection_reason=_selection_reason(candidate, threshold_mode),
                    threshold_mode=threshold_mode,
                    material_id=material_id,
                )

            call_summary = self.store.collection_call_summary(run_id)
            result = CollectionResult(
                run_id=run_id,
                topic=topic,
                status="completed",
                saved_material_ids=saved_material_ids,
                skipped=skipped,
                candidate_count=len(discovered),
                selected_count=len(selected),
                threshold_mode=threshold_mode,
                repeated_author_clues=repeated_author_clues,
                call_summary=call_summary,
                understanding_success_count=understanding_success_count,
                existing_reused_material_ids=existing_reused_material_ids,
            )
            self.store.finish_collection_run(run_id, "completed", result.to_dict())
            return result
        except Exception as exc:
            summary = {"run_id": run_id, "topic": topic, "error": str(exc), "call_summary": self.store.collection_call_summary(run_id)}
            self.store.finish_collection_run(run_id, "failed", summary, error=str(exc))
            raise

    def _candidate_with_context(self, candidate: dict[str, Any], config: CollectionConfig) -> dict[str, Any]:
        source_package = candidate.setdefault("source_package", {})
        source_package["task_id"] = config.task_id
        source_package["role_id"] = config.role_id
        return candidate

    def _search_candidates(self, executor: LoggedToolExecutor, config: CollectionConfig) -> list[dict[str, Any]]:
        if self.tools.has("douyin_search_videos"):
            return self._search_mxnzp_candidates(executor, config)
        return self._search_mock_candidates(executor, config)

    def _search_mxnzp_candidates(self, executor: LoggedToolExecutor, config: CollectionConfig) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        keywords = _unique_strings(config.search_keywords or [config.topic])
        for keyword in keywords:
            offset = "0"
            search_id = ""
            for _page in range(max(1, config.max_search_pages)):
                result = executor.run(
                    "douyin_search_videos",
                    {"keyword": keyword, "offset": offset, "search_id": search_id},
                )
                page_candidates: list[dict[str, Any]] = []
                for candidate in candidates_from_mxnzp_result(result):
                    notes = list(candidate.setdefault("source_package", {}).get("collection_notes") or [])
                    notes.append({"type": "search_keyword", "value": keyword})
                    candidate["source_package"]["collection_notes"] = notes
                    page_candidates.append(candidate)
                candidates.extend(page_candidates)
                paging = result.get("paging") or {}
                if not paging.get("has_next"):
                    break
                if not should_continue_search_pages(candidates, page_candidates, config):
                    break
                offset = str(paging.get("offset") or paging.get("cursor") or offset)
                search_id = str(paging.get("search_id") or search_id)
                if not offset and not search_id:
                    break
        return candidates

    def _search_mock_candidates(self, executor: LoggedToolExecutor, config: CollectionConfig) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for page in range(1, config.max_search_pages + 1):
            result = executor.run(
                "collect_source_candidates",
                {"keyword": config.topic, "page": page, "page_size": config.page_size},
            )
            candidates.extend(candidates_from_mock_result(result))
            if not result.get("has_next"):
                break
        return candidates

    def _extract_text(self, executor: LoggedToolExecutor, candidate: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        source_package = candidate["source_package"]
        source_link = source_package.get("source_link")
        if self.tools.has("douyin_extract_video_text"):
            if not source_link:
                raise ToolExecutionError("Candidate has no source link for video_to_text.")
            result = executor.run("douyin_extract_video_text", {"url": source_link})
            normalized = result.get("normalized") or {}
            text = str(normalized.get("text") or normalized.get("source_package", {}).get("transcript_text") or "")
            return text, result
        text = str(source_package.get("transcript_text") or candidate.get("raw", {}).get("transcript_text") or "")
        if not text:
            raise ToolExecutionError("Mock candidate has no transcript_text.")
        return text, {"ok": True, "method_key": "mock_text", "cache_hit": False}

    def _resolve_short_link(self, executor: LoggedToolExecutor, source_package: dict[str, Any]) -> dict[str, Any]:
        work_id = source_package.get("work_id")
        if not work_id or not self.tools.has("douyin_resolve_share_link"):
            return source_package
        try:
            result = executor.run("douyin_resolve_share_link", {"work_id": str(work_id)})
        except ToolExecutionError as exc:
            notes = list(source_package.get("collection_notes") or [])
            notes.append({"type": "short_link_failed", "detail": str(exc)})
            source_package["collection_notes"] = notes
            return source_package

        normalized = result.get("normalized") or {}
        if normalized.get("short_url"):
            source_package["work_short_url"] = normalized["short_url"]
        return source_package


def request_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps({"tool_name": tool_name, "arguments": arguments}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def find_existing_material_for_candidate(store: Store, candidate: dict[str, Any]) -> dict[str, Any] | None:
    source_package = candidate.get("source_package") or {}
    work_id = str(source_package.get("work_id") or "").strip()
    source_url = str(source_package.get("source_link") or "").strip()
    title = str(source_package.get("clean_title") or source_package.get("title") or "").strip()
    author = str(source_package.get("author_sec_uid") or source_package.get("author_name") or "").strip()
    title_author_key = (title, author) if title and author else None
    for material in store.list_collected_materials():
        if work_id and str(material.get("work_id") or "").strip() == work_id:
            return material
        if source_url and str(material.get("source_url") or "").strip() == source_url:
            return material
        if title_author_key:
            existing_title = str(material.get("clean_title") or material.get("title") or "").strip()
            existing_author = str(material.get("author_sec_uid") or material.get("author_name") or "").strip()
            if (existing_title, existing_author) == title_author_key:
                return material
    return None


def select_viral_candidates(
    candidates: list[dict[str, Any]],
    target_count: int,
    like_floor: int,
    super_like_threshold: int,
) -> tuple[list[dict[str, Any]], str]:
    ranked = sorted(candidates, key=viral_sort_key, reverse=True)
    super_candidates = [
        candidate for candidate in ranked if metric_value(candidate_metrics(candidate), "digg_count", "likes") >= super_like_threshold
    ]
    if len(super_candidates) >= target_count:
        return super_candidates[:target_count], "super"
    floor_candidates = [
        candidate for candidate in ranked if metric_value(candidate_metrics(candidate), "digg_count", "likes") >= like_floor
    ]
    return floor_candidates[:target_count], "floor"


def should_continue_search_pages(
    all_candidates: list[dict[str, Any]],
    latest_page_candidates: list[dict[str, Any]],
    config: CollectionConfig,
) -> bool:
    qualified = prefilter_candidates_for_transcription(all_candidates, config)
    page_qualified = prefilter_candidates_for_transcription(latest_page_candidates, config)
    target_buffer = max(config.target_count, config.target_count * 2)
    if len(qualified) >= target_buffer:
        return False
    if len(qualified) >= config.target_count and not page_qualified:
        return False
    return bool(page_qualified)


def prefilter_candidates_for_transcription(
    candidates: list[dict[str, Any]],
    config: CollectionConfig,
) -> list[dict[str, Any]]:
    duration_candidates, _ = filter_candidates_for_duration(
        candidates,
        min_seconds=config.min_duration_seconds,
        max_seconds=config.max_duration_seconds,
    )
    relevant_candidates, _ = filter_candidates_for_relevance(duration_candidates, config.role_profile, config.topic)
    return [
        candidate
        for candidate in sorted(relevant_candidates, key=viral_sort_key, reverse=True)
        if is_promising_for_transcription(candidate, config)
    ]


def is_promising_for_transcription(candidate: dict[str, Any], config: CollectionConfig) -> bool:
    metrics = candidate_metrics(candidate)
    likes = metric_value(metrics, "digg_count", "likes")
    return likes >= config.like_floor or engagement_score(candidate) >= max(config.like_floor * 2, 1)


def engagement_score(candidate: dict[str, Any]) -> int:
    metrics = candidate_metrics(candidate)
    likes = metric_value(metrics, "digg_count", "likes")
    collects = metric_value(metrics, "collect_count", "favorites", "favorite_count")
    comments = metric_value(metrics, "comment_count", "comments")
    shares = metric_value(metrics, "share_count", "shares")
    return likes + collects * 3 + comments * 2 + shares * 4


def viral_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, int]:
    metrics = candidate_metrics(candidate)
    return (
        engagement_score(candidate),
        metric_value(metrics, "share_count", "shares"),
        metric_value(metrics, "collect_count", "favorites", "favorite_count"),
        metric_value(metrics, "comment_count", "comments"),
        metric_value(metrics, "digg_count", "likes"),
    )


def candidate_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    return dict(candidate.get("source_package", {}).get("public_metrics") or {})


def metric_value(metrics: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = metrics.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def repeated_authors(candidates: list[dict[str, Any]], min_count: int = 2) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    author_meta: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        source_package = candidate.get("source_package") or {}
        author_name = source_package.get("author_name")
        author_sec_uid = source_package.get("author_sec_uid")
        identity_key = author_sec_uid or author_name
        if not identity_key:
            continue
        key = str(identity_key)
        counts[key] = counts.get(key, 0) + 1
        author_meta[key] = {
            "author_name": author_name,
            "author_sec_uid": author_sec_uid,
            "author_profile_url": source_package.get("author_profile_url"),
        }
    return [
        {"type": "head_ip_author", **author_meta[key], "candidate_count": count}
        for key, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count >= min_count
    ]


def filter_candidates_for_duration(
    candidates: list[dict[str, Any]],
    *,
    min_seconds: int,
    max_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        duration = candidate_duration_seconds(candidate)
        if duration is None:
            accepted.append(candidate)
            continue
        if duration < min_seconds:
            skipped.append(_skip(candidate, "duration_too_short", f"视频时长 {duration:.1f}s 低于 {min_seconds}s。"))
            continue
        if duration > max_seconds:
            skipped.append(_skip(candidate, "duration_too_long", f"视频时长 {duration:.1f}s 超过 {max_seconds}s。"))
            continue
        accepted.append(candidate)
    return accepted, skipped


def candidate_duration_seconds(candidate: dict[str, Any]) -> float | None:
    source_package = candidate.get("source_package") or {}
    for key in ["duration_seconds", "duration_s"]:
        value = source_package.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    value = source_package.get("duration_ms")
    if value not in (None, ""):
        try:
            return float(value) / 1000
        except (TypeError, ValueError):
            pass
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
    value = raw.get("duration_seconds")
    if value not in (None, ""):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    value = raw.get("duration")
    if value not in (None, ""):
        try:
            return float(value) / 1000
        except (TypeError, ValueError):
            pass
    return None


def filter_candidates_for_role(
    candidates: list[dict[str, Any]],
    role_profile: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not role_profile:
        return candidates, []
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    avoid_terms = list(role_profile.get("avoid_directions") or []) + list(role_profile.get("forbidden_content") or [])
    for candidate in candidates:
        source_package = candidate.get("source_package") or {}
        text = " ".join(
            str(value or "")
            for value in [
                source_package.get("title"),
                source_package.get("platform_caption"),
                source_package.get("author_name"),
            ]
        )
        hit_terms = [term for term in avoid_terms if term and term in text]
        if hit_terms:
            skipped.append(
                {
                    **_skip(candidate, "role_prefilter_rejected", "命中角色排除方向或禁区内容。"),
                    "matched_avoid_terms": hit_terms,
                    "role_name": role_profile.get("name"),
                }
            )
            continue
        accepted.append(candidate)
    return accepted, skipped


def filter_candidates_for_relevance(
    candidates: list[dict[str, Any]],
    role_profile: dict[str, Any] | None,
    topic: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        source_package = candidate.get("source_package") or {}
        haystack = " ".join(
            str(value or "")
            for value in [
                source_package.get("title"),
                source_package.get("platform_caption"),
                source_package.get("author_name"),
                source_package.get("transcript_text"),
            ]
        )
        positive_terms = _topic_terms(topic)
        if role_profile:
            positive_terms.extend(role_profile.get("search_keywords") or [])
            positive_terms.extend(role_profile.get("target_directions") or [])
        if any(term and term in haystack for term in positive_terms):
            accepted.append(candidate)
            continue
        skipped.append(_skip(candidate, "candidate_relevance_rejected", "未命中主题或角色关键词。"))
    return accepted, skipped


def candidates_from_mock_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in result.get("candidates") or []:
        metrics = item.get("visible_metrics") or {}
        candidates.append(
            {
                "source_package": {
                    "source_type": item.get("source_type") or "mock_api",
                    "source_platform": item.get("source_platform") or "mock-video",
                    "source_link": item.get("source_url"),
                    "title": item.get("title"),
                    "platform_caption": item.get("raw_text") or item.get("title"),
                    "transcript_text": item.get("transcript_text") or item.get("raw_text") or "",
                    "author_name": item.get("author_name"),
                    "duration_seconds": item.get("duration_seconds"),
                    "public_metrics": {
                        "likes": metrics.get("likes"),
                        "favorites": metrics.get("favorites"),
                        "comments": metrics.get("comments"),
                        "shares": metrics.get("shares"),
                        "views": metrics.get("views"),
                    },
                    "collection_notes": [],
                },
                "raw": item,
            }
        )
    return candidates


def candidates_from_mxnzp_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = result.get("normalized") or {}
    packages = normalized.get("source_packages") or []
    candidates: list[dict[str, Any]] = []
    for package in packages:
        source_package = dict(package)
        metrics = dict(source_package.get("public_metrics") or {})
        source_package["public_metrics"] = {
            "digg_count": metrics.get("digg_count") or metrics.get("likes"),
            "collect_count": metrics.get("collect_count") or metrics.get("favorites"),
            "comment_count": metrics.get("comment_count") or metrics.get("comments"),
            "share_count": metrics.get("share_count") or metrics.get("shares"),
            "play_count": metrics.get("play_count") or metrics.get("views"),
        }
        if package.get("duration") not in (None, ""):
            source_package["duration_ms"] = package.get("duration")
            try:
                source_package["duration_seconds"] = float(package["duration"]) / 1000
            except (TypeError, ValueError):
                pass
        source_package.setdefault("collection_notes", [])
        candidates.append({"source_package": source_package, "raw": package})
    return candidates


def enrich_source_package(
    source_package: dict[str, Any],
    candidate: dict[str, Any],
    extract_result: dict[str, Any],
    transcript_text: str,
    repeated_author_clues: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_extract = extract_result.get("normalized") if isinstance(extract_result, dict) else {}
    extract_package = (normalized_extract or {}).get("source_package") or {}
    enriched = dict(source_package)
    for key, value in extract_package.items():
        if value in (None, "", []):
            continue
        if enriched.get(key) in (None, "", []):
            enriched[key] = value
    enriched["transcript_text"] = transcript_text
    enriched["sample_pool_clues"] = [
        clue for clue in repeated_author_clues if clue.get("author_name") == enriched.get("author_name")
    ]
    return enriched


def _candidate_key(candidate: dict[str, Any]) -> str:
    source_package = candidate.get("source_package") or {}
    return str(
        source_package.get("source_link")
        or source_package.get("work_id")
        or source_package.get("title")
        or json.dumps(source_package, ensure_ascii=False, sort_keys=True)
    )


def _candidate_by_skip(candidates: list[dict[str, Any]], skipped: dict[str, Any]) -> dict[str, Any] | None:
    key = skipped.get("source_key") or skipped.get("source_url") or skipped.get("title")
    for candidate in candidates:
        source_package = candidate.get("source_package") or {}
        if key in {
            _candidate_key(candidate),
            source_package.get("source_link"),
            source_package.get("title"),
        }:
            return candidate
    return None


def _skip(candidate: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    source_package = candidate.get("source_package") or {}
    return {
        "source_key": _candidate_key(candidate),
        "source_url": source_package.get("source_link"),
        "title": source_package.get("title"),
        "reason": reason,
        "detail": detail,
    }


def _selection_reason(candidate: dict[str, Any], threshold_mode: str) -> str:
    metrics = candidate_metrics(candidate)
    label = "超级爆款阈值" if threshold_mode == "super" else "基础爆款阈值"
    return f"达到{label}，点赞 {metric_value(metrics, 'digg_count', 'likes')}，收藏 {metric_value(metrics, 'collect_count', 'favorites')}。"


def _threshold_skip_detail(candidate: dict[str, Any], config: CollectionConfig, threshold_mode: str) -> str:
    metrics = candidate_metrics(candidate)
    threshold = config.super_like_threshold if threshold_mode == "super" else config.like_floor
    return f"点赞 {metric_value(metrics, 'digg_count', 'likes')} 低于当前阈值 {threshold}。"


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _topic_terms(topic: str) -> list[str]:
    normalized = str(topic or "").strip()
    terms = [normalized] if normalized else []
    terms.extend([part for part in re.split(r"[\s,，、/]+", normalized) if len(part) >= 2])
    known_terms = [
        "知识型",
        "口播",
        "个人 IP",
        "创业 IP",
        "内容生产",
        "观点库",
        "选题",
        "账号",
        "MCN",
    ]
    terms.extend([term for term in known_terms if term and term in normalized])
    return _unique_strings(terms)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
