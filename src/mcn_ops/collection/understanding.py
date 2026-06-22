from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_UNDERSTANDING_PROVIDER = "codex-agent"
DEFAULT_UNDERSTANDING_MODEL = "gpt-5.5"
RULES_UNDERSTANDING_PROVIDER = "local-rules"
RULES_UNDERSTANDING_MODEL = "material-understanding-rules-v2"


UNDERSTANDING_FIELDS = [
    "topic_summary",
    "hook",
    "core_claim",
    "content_structure",
    "key_points",
    "content_type",
    "oral_script_pattern",
    "audience",
    "emotion_trigger",
    "risk_level",
    "rewrite_angles",
    "risk_notes",
    "usable_quotes",
    "recommended_platforms",
    "role_fit_notes",
    "next_collection_keywords",
]


def build_material_understanding(
    material: dict[str, Any],
    *,
    provider: str = DEFAULT_UNDERSTANDING_PROVIDER,
    model: str = DEFAULT_UNDERSTANDING_MODEL,
) -> dict[str, Any]:
    transcript = str(material.get("transcript_text") or "").strip()
    title = str(material.get("clean_title") or material.get("title") or "").strip()
    caption = str(material.get("platform_caption") or "").strip()
    hashtags = material.get("hashtags") or []
    text = transcript or caption or title
    sentences = _meaningful_sentences(text)
    keywords = _keywords(" ".join([title, caption, transcript, " ".join(map(str, hashtags))]))
    content_type = _infer_content_type(text)
    hook = _infer_hook(title, caption, sentences)
    core_claim = _infer_core_claim(sentences, hook)
    summary = _summarize_material(title, sentences, keywords, content_type, core_claim)
    content_structure = _infer_structure(sentences, text)
    key_points = _extract_key_points(sentences, core_claim)
    rewrite_angles = _rewrite_angles(keywords, content_type, text)
    next_keywords = keywords[:5] or [str(material.get("source_platform") or "douyin")]

    is_rules_fallback = provider == RULES_UNDERSTANDING_PROVIDER or model == RULES_UNDERSTANDING_MODEL
    return {
        "topic_summary": summary,
        "hook": _truncate(hook, 120),
        "core_claim": _truncate(core_claim, 180),
        "content_structure": content_structure,
        "key_points": key_points,
        "content_type": content_type,
        "oral_script_pattern": "-".join(content_structure),
        "audience": _infer_audience(text, keywords),
        "emotion_trigger": _infer_emotion(text),
        "risk_level": _infer_risk_level(text),
        "rewrite_angles": rewrite_angles,
        "risk_notes": _risk_notes(text),
        "usable_quotes": _usable_quotes(sentences),
        "recommended_platforms": ["douyin", "xhs", "wechat_channels", "kwai"],
        "role_fit_notes": (
            "本地规则仅完成兜底草稿；正式入选某个 IP 前需要 Codex 重新理解。"
            if is_rules_fallback
            else "Codex 已完成素材理解；用于后续按 IP 定位检索、匹配和二创判断。"
        ),
        "next_collection_keywords": next_keywords,
        "status": "draft_local_understanding" if is_rules_fallback else "success",
        "understanding_mode": "local_rules_v2" if is_rules_fallback else "codex_agent_material_understanding_v1",
        "understanding_provider": provider,
        "understanding_model": model,
    }


def validate_understanding(value: dict[str, Any]) -> None:
    missing = [field for field in UNDERSTANDING_FIELDS if field not in value]
    if missing:
        raise ValueError(f"material understanding missing fields: {', '.join(missing)}")
    if not str(value.get("topic_summary") or "").strip():
        raise ValueError("material understanding topic_summary is empty")


def evaluate_role_match(material: dict[str, Any], role: dict[str, Any]) -> dict[str, Any]:
    haystack = " ".join(
        str(value or "")
        for value in [
            material.get("title"),
            material.get("summary_text"),
            material.get("platform_caption"),
            material.get("transcript_text"),
            json.dumps(material.get("material_understanding") or {}, ensure_ascii=False),
        ]
    )
    positive_terms = (
        list(role.get("search_keywords") or [])
        + list(role.get("target_directions") or [])
        + list(role.get("preferred_content") or [])
    )
    avoid_terms = list(role.get("avoid_directions") or []) + list(role.get("forbidden_content") or [])
    matched = _unique([term for term in positive_terms if term and term in haystack])
    avoided = _unique([term for term in avoid_terms if term and term in haystack])
    if positive_terms:
        score = min(0.95, 0.45 + 0.18 * len(matched))
    else:
        score = 0.65
    if avoided:
        score = max(0.0, score - 0.45)
    decision = "accepted" if score >= 0.6 and not avoided else "rejected"
    reasons: list[str] = []
    if matched:
        reasons.append("素材命中角色关键词或目标方向。")
    if not positive_terms:
        reasons.append("角色未配置正向关键词，按通用素材默认可用。")
    if avoided:
        reasons.append("素材命中角色排除方向或禁区内容。")
    return {
        "fit_score": round(float(score), 3),
        "decision": decision,
        "reasons": reasons or ["按标题、摘要、原文案和结构化理解完成匹配。"],
        "matched_keywords": matched,
        "avoidance_notes": avoided,
    }


def _sentences(text: str) -> list[str]:
    normalized = text.replace("\n", " ").strip()
    if not normalized:
        return []
    chunks = []
    current = []
    for char in normalized:
        current.append(char)
        if char in "。！？!?":
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = []
    tail = "".join(current).strip()
    if tail:
        chunks.append(tail)
    return chunks or [normalized]


def _meaningful_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in _sentences(text)
        if not _is_low_signal_sentence(sentence)
    ] or _sentences(text)


def _is_low_signal_sentence(sentence: str) -> bool:
    normalized = sentence.strip(" ，。！？!?")
    if len(normalized) <= 4:
        return True
    low_signal = {"你知道吗", "大家好", "关注我", "点赞收藏", "别划走", "听好了"}
    return normalized in low_signal


def _infer_hook(title: str, caption: str, sentences: list[str]) -> str:
    parsed_title = re.sub(r"#([^\s#]+)", "", title or caption).strip()
    if parsed_title:
        return parsed_title
    for sentence in sentences:
        if "？" in sentence or "?" in sentence or len(sentence) <= 45:
            return sentence
    return sentences[0] if sentences else ""


def _infer_core_claim(sentences: list[str], hook: str) -> str:
    if not sentences:
        return hook
    for sentence in sentences:
        if _is_low_signal_sentence(sentence):
            continue
        if sentence.rstrip().endswith(("？", "?")):
            continue
        if any(token in sentence for token in ["其实", "核心", "关键", "本质", "就是", "要", "能够", "可以"]):
            return sentence
    for sentence in sentences:
        if _is_low_signal_sentence(sentence):
            continue
        if not sentence.rstrip().endswith(("？", "?")):
            return sentence
    return sentences[0]


def _summarize_material(
    title: str,
    sentences: list[str],
    keywords: list[str],
    content_type: str,
    core_claim: str,
) -> str:
    theme = _theme_label(title, keywords, " ".join(sentences))
    structure = {
        "方法清单": "用方法清单或口诀包装具体做法",
        "征兆判断": "用征兆判断制造代入感和期待感",
        "认知观点": "用认知观点解释现象并给出态度建议",
        "祝福念诵": "用祝福、念诵或仪式感完成情绪收束",
    }.get(content_type, "用观点口播展开一个可复述判断")
    claim = _truncate(_clean_sentence(core_claim), 70)
    if claim and not _is_low_signal_sentence(claim):
        return _truncate(f"围绕「{theme}」展开，{structure}，核心表达是：{claim}", 180)
    return _truncate(f"围绕「{theme}」展开，{structure}，适合拆成短视频口播素材再做风险降级改写。", 180)


def _theme_label(title: str, keywords: list[str], text: str) -> str:
    joined = " ".join([title, text])
    if "借运" in joined:
        return "借运与转运"
    if "运不外借" in joined or "借走" in joined or "运要回来" in joined:
        return "运不外借与转运"
    if "旺自己" in joined or "望自己" in joined:
        return "旺自己与能量提升"
    if "征兆" in joined or "信号" in joined:
        return "财运征兆"
    if "口袋" in joined and any(token in joined for token in ["硬币", "盐", "米"]):
        return "随身物件招财民俗"
    if any(token in joined for token in ["财运", "发财", "招财", "钱财"]):
        return "财运与招财"
    if keywords:
        return str(keywords[0])
    return _truncate(re.sub(r"#([^\s#]+)", "", title).strip() or "素材主题", 24)


def _keywords(text: str) -> list[str]:
    hashtags = re.findall(r"#([^\s#]+)", text)
    candidates = [
        "财运",
        "玄学",
        "国学智慧",
        "传统文化",
        "旺自己",
        "转运",
        "招财",
        "人生智慧",
        "认知",
        "知识型口播",
        "个人 IP",
        "创业 IP",
        "内容生产",
        "观点库",
        "爆款选题",
        "表达结构",
        "账号运营",
        "老师",
        "二创",
    ]
    hits = hashtags + [keyword for keyword in candidates if keyword in text]
    if hits:
        return _unique(hits)
    words = [
        word.strip("，。！？、,.!? ")
        for word in re.split(r"[\s，。！？、,.!?；;：:]+", text)
        if 2 <= len(word.strip()) <= 12
    ]
    return _unique(words[:6])


def _infer_structure(sentences: list[str], text: str) -> list[str]:
    if any(token in text for token in ["第一个", "第二", "第三", "三样", "八个", "11招", "四句"]):
        return ["利益或问题开头", "列出方法/口诀", "解释象征意义", "行动召唤或祝福收束"]
    if any(token in text for token in ["征兆", "信号", "表现"]):
        return ["问题钩子", "列举征兆", "放大期待感", "提醒理性使用"]
    if len(sentences) >= 3:
        return ["反常识或问题开头", "解释原因", "给出方法或判断", "收束为可复述观点"]
    if len(sentences) == 2:
        return ["观点开头", "解释或行动建议"]
    return ["单观点口播，可在二创时补充案例和方法步骤"]


def _infer_emotion(text: str) -> str:
    if any(token in text for token in ["财运", "发财", "招财", "钱财"]):
        return "求财焦虑、好运期待、掌控感"
    if any(token in text for token in ["借运", "霉运", "倒霉", "转运"]):
        return "摆脱低谷、借势变好、确定感"
    if any(token in text for token in ["旺自己", "能量", "越来越旺"]):
        return "自我提升、变好期待、行动感"
    if any(token in text for token in ["不是", "别", "不要", "问题", "压力"]):
        return "纠偏、减压、反常识"
    if any(token in text for token in ["相信", "稳定", "可信"]):
        return "信任、确定感"
    return "启发、方法感"


def _infer_content_type(text: str) -> str:
    if any(token in text for token in ["征兆", "信号", "表现"]):
        return "征兆判断"
    if any(token in text for token in ["招", "方法", "秘诀", "步骤", "第"]):
        return "方法清单"
    if any(token in text for token in ["为什么", "本质", "认知", "真相"]):
        return "认知观点"
    if any(token in text for token in ["祝", "愿", "念", "祈福"]):
        return "祝福念诵"
    return "观点口播"


def _infer_risk_level(text: str) -> str:
    notes = _risk_notes(text)
    if any("绝对化" in note for note in notes):
        return "medium"
    if any(token in text for token in ["发财", "招财", "财运", "玄学", "借运"]):
        return "medium"
    return "low"


def _risk_notes(text: str) -> list[str]:
    notes: list[str] = []
    if any(token in text for token in ["最", "一定", "绝对"]):
        notes.append("存在绝对化表达，改写时应降低承诺强度。")
    if any(token in text for token in ["发财", "招财", "财运", "借运", "转运", "玄学"]):
        notes.append("涉及玄学求财或转运承诺，二创时应改成民俗文化、心理暗示或行动建议表达。")
    if not notes:
        notes.append("未发现明显高风险表达，发布前仍需人工复核事实和平台合规。")
    return notes


def _infer_audience(text: str, keywords: list[str]) -> str:
    haystack = " ".join([text, " ".join(keywords)])
    if any(token in haystack for token in ["女生", "女性"]):
        return "关注自我提升、能量状态和女性成长表达的人群"
    if any(token in haystack for token in ["财运", "招财", "发财", "转运", "借运", "玄学"]):
        return "对财运转运、民俗玄学和自我状态改善话题感兴趣的人群"
    if any(token in haystack for token in ["旺自己", "能量"]):
        return "关注自我提升、能量状态和女性成长表达的人群"
    if any(token in haystack for token in ["创业", "老板", "生意"]):
        return "关注生意经营、个人决策和老板认知的人群"
    if any(token in haystack for token in ["知识型口播", "内容生产", "账号运营", "个人 IP"]):
        return "关注个人 IP、知识型口播和内容生产方法的人群"
    return "对观点口播、人生经验和实用建议感兴趣的人群"


def _extract_key_points(sentences: list[str], core_claim: str) -> list[str]:
    ranked = sorted(
        [_clean_sentence(sentence) for sentence in sentences if not _is_low_signal_sentence(sentence)],
        key=_sentence_score,
        reverse=True,
    )
    points = _unique([item for item in ranked if item and item != _clean_sentence(core_claim)])
    if not points and core_claim:
        points = [_clean_sentence(core_claim)]
    return [_truncate(point, 120) for point in points[:5]]


def _sentence_score(sentence: str) -> int:
    score = min(len(sentence), 80)
    for token in ["第一个", "第二", "第三", "其实", "为什么", "关键", "方法", "征兆", "口诀", "建议", "不要", "可以"]:
        if token in sentence:
            score += 20
    if sentence.endswith(("。", "！", "？")):
        score += 3
    return score


def _rewrite_angles(keywords: list[str], content_type: str, text: str) -> list[str]:
    theme = keywords[0] if keywords else "原主题"
    angles = [
        f"围绕「{theme}」改写成更理性的经验判断，保留口播钩子但弱化玄学承诺。",
    ]
    if content_type == "方法清单":
        angles.append("改成三点方法清单：现象-原因-行动建议，方便老师 IP 直接口播。")
    elif content_type == "征兆判断":
        angles.append("改成征兆自查结构：先给判断，再提示不要把结果说死。")
    elif content_type == "祝福念诵":
        angles.append("改成祝福型结尾素材，避免把念诵包装成确定收益。")
    else:
        angles.append("改成观点型口播：反常识开头，补一个生活案例，再给结论。")
    if any(token in text for token in ["财运", "发财", "招财", "借运", "转运"]):
        angles.append("把求财表达转成民俗文化、心理暗示或行动习惯，降低平台风险。")
    return _unique(angles)


def _usable_quotes(sentences: list[str]) -> list[str]:
    quotes = [
        _clean_sentence(sentence)
        for sentence in sentences
        if 8 <= len(_clean_sentence(sentence)) <= 80 and not _is_low_signal_sentence(sentence)
    ]
    return [_truncate(sentence, 80) for sentence in _unique(quotes)[:3]]


def _clean_sentence(value: str) -> str:
    value = re.sub(r"#([^\s#]+)", "", str(value or "")).strip()
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value: str, limit: int) -> str:
    value = str(value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
