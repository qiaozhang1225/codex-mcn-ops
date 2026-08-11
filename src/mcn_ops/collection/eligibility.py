from __future__ import annotations

import re
from typing import Any


ELIGIBILITY_PROVIDER = "local-rules"
ELIGIBILITY_VERSION = "material-eligibility-v1"


def evaluate_material_eligibility(
    material: dict[str, Any],
    *,
    role_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = str(material.get("clean_title") or material.get("title") or "").strip()
    caption = str(material.get("caption_text") or material.get("platform_caption") or "").strip()
    transcript = str(material.get("transcript_text") or "").strip()
    author = str(material.get("author_name") or "").strip()
    text = " ".join([title, caption, transcript, author])
    normalized = re.sub(r"\s+", "", text)

    content_form = _content_form(normalized)
    reasons: list[str] = []
    reject_reason = ""

    evidence_text = transcript if len(re.sub(r"\s+", "", transcript)) >= 20 else caption
    knowledge_core_score = _knowledge_core_score(normalized, evidence_text)
    oral_script_fit_score = _oral_script_fit_score(normalized, evidence_text)
    ip_fit_score = _ip_fit_score(normalized, role_profile)

    transcript_len = max(len(re.sub(r"\s+", "", transcript)), len(re.sub(r"\s+", "", caption)))
    if transcript_len < 20:
        reject_reason = "missing_or_short_transcript"
        reasons.append("原文案为空或过短，不能支撑素材理解和二创判断。")

    strong_ritual_hits = _hits(normalized, STRONG_RITUAL_TERMS)
    ritual_hits = _hits(normalized, RITUAL_TERMS)
    buddhist_hits = _hits(normalized, BUDDHIST_TERMS)
    if not reject_reason and strong_ritual_hits:
        reject_reason = "ritual_action"
        reasons.append("主体是仪式动作、祈愿或玄学操作，不属于知识型口播素材。")
    elif not reject_reason and ritual_hits and knowledge_core_score < 0.65:
        reject_reason = "ritual_action"
        reasons.append("包含明显仪式动作且缺少可复述的知识解释链。")

    non_knowledge_hits = _hits(normalized, NON_KNOWLEDGE_TERMS)
    hard_non_knowledge_hits = _hits(normalized, HARD_NON_KNOWLEDGE_TERMS)
    if not reject_reason and hard_non_knowledge_hits:
        reject_reason = "non_knowledge_content"
        reasons.append("主体是生活剧情、宠物、亲子或泛娱乐场景，不适合作为知识型博主口播底稿。")
    elif not reject_reason and non_knowledge_hits and knowledge_core_score < 0.7:
        reject_reason = "non_knowledge_content"
        reasons.append("主体更像剧情、生活片段、互动内容或垂类场景，不适合作为知识型博主口播底稿。")

    interaction_hits = _hits(normalized, INTERACTION_TERMS)
    if not reject_reason and len(interaction_hits) >= 2 and knowledge_core_score < 0.65:
        reject_reason = "interactive_or_emotional_prompt"
        reasons.append("内容主要依赖互动、祝福或情绪引导，不是知识传播型文案。")

    if not reject_reason and knowledge_core_score < 0.4:
        reject_reason = "weak_knowledge_core"
        reasons.append("没有明确观点、解释链、判断逻辑或知识内核。")

    if not reject_reason and oral_script_fit_score < 0.35 and knowledge_core_score < 0.45:
        reject_reason = "poor_oral_script_fit"
        reasons.append("口播结构弱，难以直接沉淀为知识分享型文案底稿。")

    status = "rejected" if reject_reason else "accepted"
    if not reasons:
        reasons.append("具备可复述观点或解释链，适合作为知识分享型口播素材继续理解。")
    if status == "accepted" and buddhist_hits:
        reasons.append("含佛教色彩词，后续二创时应转译为道家/国学表达。")

    return {
        "eligibility_status": status,
        "eligibility_provider": ELIGIBILITY_PROVIDER,
        "eligibility_version": ELIGIBILITY_VERSION,
        "reject_reason": reject_reason,
        "reasons": reasons,
        "content_form": content_form,
        "knowledge_core_score": round(knowledge_core_score, 3),
        "oral_script_fit_score": round(oral_script_fit_score, 3),
        "ip_fit_score": round(ip_fit_score, 3),
        "matched_terms": {
            "ritual": ritual_hits,
            "strong_ritual": strong_ritual_hits,
            "buddhist": buddhist_hits,
            "non_knowledge": non_knowledge_hits,
            "hard_non_knowledge": hard_non_knowledge_hits,
            "interaction": interaction_hits,
        },
    }


def is_material_eligible(eligibility: dict[str, Any]) -> bool:
    return str(eligibility.get("eligibility_status") or "") == "accepted"


def rejected_status_for_eligibility(eligibility: dict[str, Any]) -> str:
    reason = str(eligibility.get("reject_reason") or "")
    if reason in {"ritual_action", "interactive_or_emotional_prompt", "non_knowledge_content"}:
        return "eligibility_rejected"
    if reason == "missing_or_short_transcript":
        return "missing_transcript"
    return "eligibility_rejected"


def _content_form(text: str) -> str:
    if _hits(text, STRONG_RITUAL_TERMS) or _hits(text, RITUAL_TERMS):
        return "仪式动作"
    if _hits(text, NON_KNOWLEDGE_TERMS):
        return "剧情互动"
    if _hits(text, BUDDHIST_TERMS):
        return "佛教色彩"
    if any(term in text for term in ["祝福", "好运", "接好运", "祈愿"]):
        return "祝福念诵"
    if any(term in text for term in ["征兆", "信号", "预兆"]):
        return "征兆判断"
    if _list_marker_count(text) >= 2:
        return "方法清单"
    if any(term in text for term in ["道德经", "庄子", "老子", "无为而治", "上善若水"]):
        return "认知观点"
    return "知识口播"


def _knowledge_core_score(text: str, transcript: str) -> float:
    hits = _hits(text, KNOWLEDGE_TERMS)
    explain_hits = _hits(text, EXPLANATION_TERMS)
    list_count = _list_marker_count(text)
    length = len(re.sub(r"\s+", "", transcript))
    score = 0.12 * len(hits) + 0.08 * len(explain_hits) + 0.06 * min(list_count, 4)
    if 80 <= length <= 1200:
        score += 0.18
    elif length >= 40:
        score += 0.08
    if _hits(text, STRONG_RITUAL_TERMS):
        score -= 0.35
    if _hits(text, NON_KNOWLEDGE_TERMS):
        score -= 0.2
    return max(0.0, min(1.0, score))


def _oral_script_fit_score(text: str, transcript: str) -> float:
    compact = re.sub(r"\s+", "", transcript)
    sentence_count = len([part for part in re.split(r"[。！？!?]", transcript) if part.strip()])
    score = 0.0
    if 80 <= len(compact) <= 1200:
        score += 0.35
    elif 40 <= len(compact) <= 1600:
        score += 0.2
    if sentence_count >= 3:
        score += 0.2
    if _list_marker_count(text) >= 2:
        score += 0.15
    if any(term in text for term in ["为什么", "其实", "真正", "本质", "不是", "而是", "记住"]):
        score += 0.15
    if "@" in text:
        score -= 0.15
    if _hits(text, STRONG_RITUAL_TERMS):
        score -= 0.25
    return max(0.0, min(1.0, score))


def _ip_fit_score(text: str, role_profile: dict[str, Any] | None) -> float:
    if not role_profile:
        return 0.0
    positive_terms = (
        list(role_profile.get("search_keywords") or [])
        + list(role_profile.get("target_directions") or [])
        + list(role_profile.get("fit_themes") or [])
    )
    avoid_terms = (
        list(role_profile.get("avoid_directions") or [])
        + list(role_profile.get("avoid_themes") or [])
        + list(role_profile.get("forbidden_content") or [])
        + list(role_profile.get("forbidden_expressions") or [])
    )
    matched = _hits(text, positive_terms)
    avoided = _hits(text, avoid_terms)
    score = min(1.0, 0.25 + 0.12 * len(matched))
    if avoided:
        score -= min(0.6, 0.18 * len(avoided))
    return max(0.0, min(1.0, score))


def _list_marker_count(text: str) -> int:
    markers = ["第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八", "第九", "一是", "二是", "三是"]
    return sum(1 for marker in markers if marker in text)


def _hits(text: str, terms: list[str]) -> list[str]:
    return _unique([term for term in terms if term and term in text])


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


STRONG_RITUAL_TERMS = [
    "倒一杯",
    "自来水",
    "吐三口气",
    "弹三下",
    "大晴天找个开阔地",
    "迎着太阳深吸一口气",
    "开天眼",
    "梦中传道",
    "双手合十",
]

RITUAL_TERMS = [
    "默念",
    "念三遍",
    "口诀",
    "咒",
    "咒语",
    "结印",
    "手诀",
    "清水",
    "晒太阳",
    "许愿",
    "祈福",
    "祈祷",
    "接好运",
    "转运小妙招",
    "玄学转运",
    "放三样",
    "口袋放",
    "硬币",
    "七粒米",
    "盐",
]

BUDDHIST_TERMS = ["菩萨", "佛法", "念佛", "禅修", "功德", "五台山", "佛家"]

HARD_NON_KNOWLEDGE_TERMS = ["爸爸带娃", "带娃", "养宠", "宠物", "萌萌", "霸总", "亲吻"]

NON_KNOWLEDGE_TERMS = [
    "爸爸带娃",
    "带娃",
    "养宠",
    "萌萌",
    "霸总",
    "亲吻",
    "充电宝",
    "包假的",
    "二创版",
    "剧情",
    "搞笑",
    "宠物",
]

INTERACTION_TERMS = [
    "刷到这条",
    "留下一句",
    "评论区",
    "点赞",
    "收藏",
    "转发",
    "跟着做",
    "照着做",
    "不要划走",
    "接好运",
]

KNOWLEDGE_TERMS = [
    "道德经",
    "庄子",
    "老子",
    "王阳明",
    "曾国藩",
    "了凡四训",
    "古人",
    "国学",
    "道家",
    "修行",
    "修心",
    "无为而治",
    "上善若水",
    "道法自然",
    "不争",
    "顺其自然",
    "本质",
    "规律",
    "逻辑",
    "原因",
    "认知",
    "处世",
    "分寸",
    "边界",
    "人性",
    "守财",
    "贵人",
    "财运",
    "征兆",
    "知识型",
    "口播",
    "观点",
    "解释",
    "选题",
    "账号",
    "内容",
    "内容团队",
    "内容生产",
    "信息",
    "资料搬运工",
    "解释路径",
    "路径",
    "沉淀",
    "流程",
    "创业",
    "表达",
    "可信任",
    "资产",
]

EXPLANATION_TERMS = [
    "为什么",
    "因为",
    "所以",
    "其实",
    "真正",
    "关键",
    "不是",
    "而是",
    "也就是说",
    "换句话说",
    "核心",
]
