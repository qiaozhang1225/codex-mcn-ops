from __future__ import annotations

from typing import Any

from .tools import ToolExecutionError, ToolRegistry, ToolSpec


def build_mock_source_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="collect_source_candidates",
            description="Search a mock local source collection for spoken-video copywriting candidates.",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["keyword", "page", "page_size"],
            },
            handler=collect_source_candidates,
        )
    )
    return registry


def collect_source_candidates(arguments: dict[str, Any]) -> dict[str, Any]:
    keyword = str(arguments.get("keyword", "")).strip()
    page = arguments.get("page")
    page_size = arguments.get("page_size")
    if not keyword:
        raise ToolExecutionError("keyword is required.")
    if not isinstance(page, int) or page < 1:
        raise ToolExecutionError("page must be an integer >= 1.")
    if not isinstance(page_size, int) or page_size < 1 or page_size > 5:
        raise ToolExecutionError("page_size must be an integer between 1 and 5.")

    ranked = _rank_candidates(keyword, MOCK_SOURCE_CANDIDATES)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "ok": True,
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
        "has_next": end < len(ranked),
        "next_page": page + 1 if end < len(ranked) else None,
        "total_available": len(ranked),
        "candidates": ranked[start:end],
    }


def _rank_candidates(keyword: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = keyword.lower()

    def score(candidate: dict[str, Any]) -> tuple[int, int]:
        haystack = " ".join(
            str(candidate.get(field, ""))
            for field in ["title", "raw_text", "transcript_text", "topic_tag"]
        ).lower()
        metrics = candidate.get("visible_metrics") or {}
        likes = int(metrics.get("likes") or 0)
        return (1 if lowered in haystack else 0, likes)

    return sorted(candidates, key=score, reverse=True)


MOCK_SOURCE_CANDIDATES: list[dict[str, Any]] = [
    {
        "title": "一个人做知识型口播，先别急着找爆款选题",
        "source_url": "mock://source/001",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "解释型内容研究员",
        "duration_seconds": 78,
        "visible_metrics": {"likes": 128000, "favorites": 9400, "comments": 880, "shares": 640, "views": 391200},
        "raw_text": "一个人做知识型口播，最先要解决的不是选题数量，而是你到底用什么观点被观众记住。",
        "transcript_text": "先确定观点锚点，再找选题，才能避免每天追热点但账号没有识别度。",
        "topic_tag": "知识型口播",
    },
    {
        "title": "创业者做个人 IP，要先把重复表达变成资产",
        "source_url": "mock://source/002",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "创业表达顾问",
        "duration_seconds": 91,
        "visible_metrics": {"likes": 87000, "favorites": 5100, "comments": 410, "shares": 370, "views": 180030},
        "raw_text": "创业者做 IP 不是每天换一种说法，而是把同一套判断反复讲到别人能复述。",
        "transcript_text": "重复不是偷懒，稳定的表达结构会变成账号资产。",
        "topic_tag": "创业 IP",
    },
    {
        "title": "内容团队为什么越勤奋越像资料搬运工",
        "source_url": "mock://source/003",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "内容流程教练",
        "duration_seconds": 64,
        "visible_metrics": {"likes": 6500, "favorites": 900, "comments": 260, "shares": 190, "views": 91220},
        "raw_text": "如果只收集信息，不建立自己的解释路径，内容团队会越来越像资料搬运工。",
        "transcript_text": "收集的价值不在数量，而在能否沉淀出自己的解释路径。",
        "topic_tag": "内容生产",
    },
    {
        "title": "知识型账号的第一性原理是可信任的解释",
        "source_url": "mock://source/004",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "解释型内容研究员",
        "duration_seconds": 82,
        "visible_metrics": {"likes": 173000, "favorites": 12800, "comments": 1020, "shares": 930, "views": 508910},
        "raw_text": "知识型账号不是给答案，而是让观众相信你有一套稳定的解释世界的方法。",
        "transcript_text": "可信任的解释，比单条爆款更重要。",
        "topic_tag": "知识型口播",
    },
    {
        "title": "从选题库到观点库，MCN 一人公司要换一个管理对象",
        "source_url": "mock://source/005",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "一人 MCN 方法论",
        "duration_seconds": 105,
        "visible_metrics": {"likes": 18000, "favorites": 1600, "comments": 310, "shares": 580, "views": 140090},
        "raw_text": "一个人做 MCN，不应该只管理选题库，而应该管理观点库、案例库和表达结构。",
        "transcript_text": "把管理对象从选题换成观点，生产压力会明显下降。",
        "topic_tag": "MCN 一人公司",
    },
    {
        "title": "口播 IP 的差异化，不来自人设标签",
        "source_url": "mock://source/006",
        "source_type": "mock_api",
        "source_platform": "mock-video",
        "author_name": "解释型内容研究员",
        "duration_seconds": 73,
        "visible_metrics": {"likes": 116000, "favorites": 7800, "comments": 590, "shares": 440, "views": 267710},
        "raw_text": "口播 IP 的差异化不来自人设标签，而来自你长期如何解释同一类问题。",
        "transcript_text": "长期解释同一类问题，才会形成账号差异化。",
        "topic_tag": "口播 IP",
    },
]
