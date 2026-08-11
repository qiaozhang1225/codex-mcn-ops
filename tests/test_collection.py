from __future__ import annotations

from pathlib import Path

from mcn_ops.collection.douyin.contracts import build_provider_result
from mcn_ops.collection.eligibility import evaluate_material_eligibility
from mcn_ops.collection.mock_tools import build_mock_source_registry
from mcn_ops.collection.runner import (
    CollectionConfig,
    LoggedToolExecutor,
    TopicCollectionRunner,
    filter_candidates_for_duration,
    should_continue_search_pages,
)
from mcn_ops.collection.tools import ToolRegistry, ToolSpec
from mcn_ops.collection.workflows import CollectionTaskOrchestrator
from mcn_ops.collection.understanding import (
    RULES_UNDERSTANDING_MODEL,
    RULES_UNDERSTANDING_PROVIDER,
    build_material_understanding,
    evaluate_role_match,
)
from mcn_ops.store import Store


def test_search_prefilter_rejects_out_of_range_duration() -> None:
    candidates = [
        {"source_package": {"title": "太短", "duration_seconds": 12}},
        {"source_package": {"title": "刚好", "duration_seconds": 60}},
        {"source_package": {"title": "太长", "duration_ms": 360000}},
    ]

    accepted, skipped = filter_candidates_for_duration(candidates, min_seconds=20, max_seconds=300)

    assert [item["source_package"]["title"] for item in accepted] == ["刚好"]
    assert [item["reason"] for item in skipped] == ["duration_too_short", "duration_too_long"]


def test_search_pagination_stops_when_target_buffer_is_enough() -> None:
    config = CollectionConfig(topic="财运", target_count=2, like_floor=100)
    candidates = [
        {
            "source_package": {
                "title": f"财运方法 {index}",
                "platform_caption": "财运方法",
                "duration_seconds": 60,
                "public_metrics": {"digg_count": 1000, "collect_count": 500, "share_count": 300},
            }
        }
        for index in range(4)
    ]

    assert should_continue_search_pages(candidates, candidates[-2:], config) is False


def test_transcription_bypasses_outer_url_cache_for_model_aware_provider_cache() -> None:
    class FakeStore:
        def __init__(self):
            self.cache_reads = 0

        def get_cached_collection_call(self, fingerprint):
            self.cache_reads += 1
            return {"ok": True, "normalized": {"text": "stale outer cache"}}

        def put_cached_collection_call(self, *args, **kwargs):
            raise AssertionError("transcription must not be written to the outer URL-only cache")

        def log_collection_call(self, **kwargs):
            return "log-1"

    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            name="douyin_extract_video_text",
            description="test",
            parameters={},
            handler=lambda arguments: {"ok": True, "provider": "aliyun", "normalized": {"text": "fresh"}},
        )
    )
    store = FakeStore()

    result = LoggedToolExecutor(tools, store, "run-1", provider="direct").run(
        "douyin_extract_video_text", {"url": "https://v.douyin.com/example"}
    )

    assert result["normalized"]["text"] == "fresh"
    assert store.cache_reads == 0


def test_author_transcription_bypasses_outer_url_cache() -> None:
    class FakeStore:
        def __init__(self):
            self.cache_reads = 0

        def get_cached_collection_call(self, fingerprint):
            self.cache_reads += 1
            return {"ok": True, "normalized": {"text": "stale"}}

        def put_cached_collection_call(self, *args, **kwargs):
            raise AssertionError("author transcription must rely on the model-aware ASR cache")

        def log_collection_call(self, **kwargs):
            return "log-1"

    class FakeProvider:
        provider_name = "direct"

        def call(self, method_key, params=None, body=None, use_cache=True):
            return {"ok": True, "provider": "aliyun", "normalized": {"text": "fresh"}}

    store = FakeStore()
    result = CollectionTaskOrchestrator(store)._call_provider(
        FakeProvider(),
        run_id="run-1",
        method_key="video_to_text_v2",
        body={"url": "https://v.douyin.com/example"},
    )

    assert result["normalized"]["text"] == "fresh"
    assert store.cache_reads == 0


def test_author_task_bootstraps_sec_uid_and_accepts_browser_aggregated_posts(tmp_path: Path) -> None:
    class FakeBrowserProvider:
        provider_name = "direct"
        browser_pagination = True

        def __init__(self) -> None:
            self.calls = []

        def call(self, method_key, params=None, body=None, use_cache=True):
            self.calls.append((method_key, params))
            assert method_key == "user_post"
            return build_provider_result(
                provider="direct",
                method_key=method_key,
                normalized={
                    "items": [
                        {
                            "id": "3333333333333333333",
                            "caption": "低赞测试作品",
                            "author_name": "目标作者",
                            "author_sec_uid": "MS4.target",
                            "duration": 60000,
                            "metrics": {"digg_count": 10},
                        }
                    ],
                    "source_packages": [
                        {
                            "source_link": "https://www.douyin.com/video/3333333333333333333",
                            "work_id": "3333333333333333333",
                            "title": "低赞测试作品",
                            "author_name": "目标作者",
                            "author_sec_uid": "MS4.target",
                            "duration_ms": 60000,
                            "public_metrics": {"digg_count": 10},
                        }
                    ],
                },
                paging={
                    "has_next": True,
                    "cursor": "20",
                    "offset": "20",
                    "search_id": None,
                    "page": None,
                    "raw": {
                        "browser_aggregated": True,
                        "pages_captured": 2,
                        "stop_reason": "idle_scroll_limit",
                    },
                },
            )

    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    provider = FakeBrowserProvider()
    orchestrator = CollectionTaskOrchestrator(store)
    orchestrator._build_collection_provider = lambda **kwargs: provider  # type: ignore[method-assign]

    report = orchestrator.run_author_task(
        sec_uid="MS4.target",
        name="目标作者",
        like_floor=10000,
        max_pages=5,
        materialize_top=1,
        data_provider="direct",
        transcription_provider="aliyun",
    )

    assert store.get_douyin_author("MS4.target")["nickname"] == "目标作者"
    assert len(store.list_douyin_author_videos("MS4.target")) == 1
    assert provider.calls == [
        (
            "user_post",
            {"userId": "MS4.target", "sortType": 1, "cursor": "", "max_pages": 5},
        )
    ]
    assert report["runs"][0]["summary"]["expand"]["stop_reason"] == "idle_scroll_limit"
    traversal = report["runs"][0]["summary"]["expand"]
    assert traversal["captured_pages"] == 2
    assert traversal["has_next"] is True
    assert traversal["request_satisfied"] is False
    assert traversal["source_exhausted"] is False


def test_direct_author_name_requires_locally_resolved_identity(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    orchestrator = CollectionTaskOrchestrator(store)
    orchestrator._build_collection_provider = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("Direct user_search must not run")
    )

    try:
        orchestrator.run_author_task(name="未解析作者", data_provider="direct")
    except KeyError as exc:
        assert "resolve a verified sec_uid" in str(exc)
    else:
        raise AssertionError("unresolved author name must fail closed")


def test_resume_legacy_paid_task_fails_closed_to_direct_and_aliyun(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    task_id = store.create_collection_task(
        command="legacy task",
        target_scope="keyword",
        target_count_per_role=1,
        topic="财运",
        parsed={
            "entrypoint": "keyword",
            "topic": "财运",
            "target_count": 1,
            "tool_provider": "mxnzp",
            "transcription_provider": "provider",
            "allow_paid_fallback": True,
        },
    )
    captured: dict[str, object] = {}
    orchestrator = CollectionTaskOrchestrator(store)

    def run_keyword_task(**kwargs):
        captured.update(kwargs)
        return {"task_id": kwargs["task_id"]}

    orchestrator.run_keyword_task = run_keyword_task  # type: ignore[method-assign]

    assert orchestrator.resume_task(task_id) == {"task_id": task_id}
    assert captured["tool_provider"] == "direct"
    assert captured["transcription_provider"] == "aliyun"
    assert captured["allow_paid_fallback"] is False


def test_keyword_detail_verification_backfills_and_reports_traversal(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    packages = [
        {
            "source_link": "https://www.douyin.com/video/111",
            "work_id": "111",
            "title": "财运候选一",
            "platform_caption": "财运候选一",
            "duration_ms": 60000,
            "public_metrics": {"digg_count": 1000},
        },
        {
            "source_link": "https://www.douyin.com/video/222",
            "work_id": "222",
            "title": "财运候选二",
            "platform_caption": "财运候选二",
            "duration_ms": 60000,
            "public_metrics": {"digg_count": 900},
        },
    ]
    tools = ToolRegistry()

    def search(_arguments):
        return build_provider_result(
            provider="direct",
            method_key="video_search",
            normalized={"source_packages": packages},
            paging={
                "has_next": True,
                "cursor": "cursor-3",
                "offset": "cursor-3",
                "search_id": "search-1",
                "page": None,
                "raw": {"browser_aggregated": True, "pages_captured": 3, "stop_reason": "max_pages"},
            },
        )

    def detail(arguments):
        work_id = arguments["url"].rsplit("/", 1)[-1]
        calls.append(("detail", work_id))
        package = dict(next(item for item in packages if item["work_id"] == work_id))
        package["public_metrics"] = {"digg_count": 10 if work_id == "111" else 800}
        return build_provider_result(
            provider="direct",
            method_key="detail_v4",
            normalized={"source_package": package},
        )

    def transcribe(arguments):
        work_id = arguments["url"].rsplit("/", 1)[-1]
        calls.append(("asr", work_id))
        return build_provider_result(
            provider="aliyun",
            method_key="video_to_text_v2",
            normalized={
                "text": "财运不是仪式，而是理解守财边界、行动方式和长期关系。",
                "source_package": {"transcript_text": "财运不是仪式，而是理解守财边界、行动方式和长期关系。"},
            },
        )

    for name, handler in [
        ("douyin_search_videos", search),
        ("douyin_fetch_video_detail", detail),
        ("douyin_extract_video_text", transcribe),
    ]:
        tools.register(ToolSpec(name=name, description="test", parameters={}, handler=handler))

    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    result = TopicCollectionRunner(tools, store).run(
        CollectionConfig(
            topic="财运",
            target_count=1,
            like_floor=100,
            super_like_threshold=10000,
            tool_provider="direct",
            max_search_pages=3,
        )
    )

    assert result.status == "completed"
    assert result.selected_count == 2
    assert calls == [("detail", "111"), ("detail", "222"), ("asr", "222")]
    assert result.traversal == {
        "captured_pages": 3,
        "captured_items": 2,
        "has_next": True,
        "request_satisfied": True,
        "source_exhausted": False,
        "stop_reason": "max_pages",
        "goal_satisfied": True,
        "saved_count": 1,
        "target_count": 1,
    }
    assert "mxnzp_call_summary" not in result.to_dict()
    assert result.to_dict()["collection_call_summary"]["total_calls"] == 4


def test_mock_collection_run_writes_materials(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    runner = TopicCollectionRunner(build_mock_source_registry(), store)

    result = runner.run(
        CollectionConfig(
            topic="知识型口播",
            target_count=2,
            like_floor=1,
            super_like_threshold=100000,
            tool_provider="mock",
            max_search_pages=2,
        )
    )

    materials = store.list_collected_materials(run_id=result.run_id)
    report = store.build_collection_report(result.run_id)

    assert result.status == "completed"
    assert len(materials) == 2
    assert materials[0]["understanding_provider"] == "codex-agent"
    assert materials[0]["understanding_model"] == "gpt-5.5"
    assert materials[0]["understanding_status"] == "success"
    assert materials[0]["eligibility_status"] == "accepted"
    assert materials[0]["knowledge_core_score"] > 0
    assert report["saved_count"] == 2


def test_collection_run_status_separates_partial_and_empty_from_goal(tmp_path: Path) -> None:
    partial_store = Store(tmp_path / "partial.sqlite")
    partial_store.init_db()
    partial = TopicCollectionRunner(build_mock_source_registry(), partial_store).run(
        CollectionConfig(topic="知识型口播", target_count=10, like_floor=1, max_search_pages=3)
    )
    empty_store = Store(tmp_path / "empty.sqlite")
    empty_store.init_db()
    empty = TopicCollectionRunner(build_mock_source_registry(), empty_store).run(
        CollectionConfig(topic="知识型口播", target_count=1, like_floor=10**12, max_search_pages=1)
    )

    assert partial.status == "partial"
    assert partial.traversal["goal_satisfied"] is False
    assert empty.status == "empty"
    assert empty.traversal["goal_satisfied"] is False


def test_material_eligibility_rejects_ritual_action_without_knowledge_core() -> None:
    result = evaluate_material_eligibility(
        {
            "clean_title": "玄学转运小妙招",
            "platform_caption": "玄学转运小妙招 #财运",
            "transcript_text": "倒一杯自来水，往水里面吐三口气，然后用食指和中指搅几圈，再默念口诀三遍。",
        }
    )

    assert result["eligibility_status"] == "rejected"
    assert result["reject_reason"] == "ritual_action"
    assert result["content_form"] == "仪式动作"


def test_material_eligibility_keeps_knowledge_talk_with_buddhist_risk_term() -> None:
    result = evaluate_material_eligibility(
        {
            "clean_title": "普通人到底如何提高财运",
            "platform_caption": "普通人到底如何提高财运 #财运 #国学智慧",
            "transcript_text": "普通人提高财运，关键不是求神拜佛，而是理解守财、贵人、分寸和因果。为什么有人一有钱就守不住？因为他破坏了关系边界，也把真正帮助自己的人往外推。有些人把家人叫作人间菩萨，这个说法可以转成福报和德行的表达。",
        }
    )

    assert result["eligibility_status"] == "accepted"
    assert result["reject_reason"] == ""
    assert result["content_form"] == "佛教色彩"
    assert "菩萨" in result["matched_terms"]["buddhist"]


def test_codex_understanding_generates_summary_not_opening_clip() -> None:
    understanding = build_material_understanding(
        {
            "clean_title": "财运来了有什么征兆？",
            "platform_caption": "财运来了有什么征兆？ #财运 #玄学",
            "transcript_text": "财运来了有什么特征？第一，你会突然遇到贵人。第二，做事会越来越顺。第三，你会更愿意主动行动。记住不要把好运只理解成玄学。",
            "hashtags": ["财运", "玄学"],
        }
    )

    assert understanding["topic_summary"] != "财运来了有什么特征？"
    assert "围绕「财运征兆」展开" in understanding["topic_summary"]
    assert understanding["audience"] == "对财运转运、民俗玄学和自我状态改善话题感兴趣的人群"
    assert understanding["understanding_provider"] == "codex-agent"
    assert understanding["understanding_model"] == "gpt-5.5"
    assert understanding["status"] == "success"


def test_rules_understanding_is_explicit_fallback_draft() -> None:
    understanding = build_material_understanding(
        {
            "clean_title": "财运来了有什么征兆？",
            "platform_caption": "财运来了有什么征兆？ #财运 #玄学",
            "transcript_text": "财运来了有什么特征？第一，你会突然遇到贵人。第二，做事会越来越顺。",
            "hashtags": ["财运", "玄学"],
        },
        provider=RULES_UNDERSTANDING_PROVIDER,
        model=RULES_UNDERSTANDING_MODEL,
    )

    assert understanding["understanding_provider"] == "local-rules"
    assert understanding["understanding_model"] == "material-understanding-rules-v2"
    assert understanding["status"] == "draft_local_understanding"


def test_role_match_rejects_non_collected_material_status() -> None:
    match = evaluate_role_match(
        {
            "status": "role_boundary_mismatch",
            "title": "道家修行",
            "summary_text": "命中关键词但已被人工标记为边界不适配。",
        },
        {"search_keywords": ["道家修行"]},
    )

    assert match["decision"] == "rejected"
    assert match["fit_score"] == 0.0
    assert match["avoidance_notes"] == ["role_boundary_mismatch"]
