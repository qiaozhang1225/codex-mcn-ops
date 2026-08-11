from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..store import Store


DEFAULT_CREATION_PROVIDER = "codex-agent"
DEFAULT_CREATION_MODEL = "gpt-5.5"
DRAFT_LOCAL_CREATION_STATUS = "draft_local_creation"
CREATION_METHODOLOGY_VERSION = "creation-methodology-v2"
CREATION_STAGE_CONTRACT_VERSION = "creation-stage-contract-v1"
DEFAULT_TARGET_LENGTH_RANGE = (300, 500)

CREATION_STAGES = [
    "material_selection",
    "creation_brief",
    "rewrite_draft",
    "hook_enhancement",
    "risk_cleanup",
    "publish_format",
    "delivery",
]

VIEWER_COPY_OUTPUT_KEYS = {
    "body",
    "draft",
    "draft_text",
    "cleaned_body",
    "final_copy",
    "publish_package",
}

STAGE_KNOWLEDGE_KEYS = {
    "material_selection": ["material_selection_playbook", "ip_creation_playbook", "ip_recent_creation_memory"],
    "creation_brief": ["creation_brief_playbook", "global_rewrite_playbook", "ip_creation_playbook", "ip_recent_creation_memory", "ip_feedback_learnings"],
    "rewrite_draft": ["global_rewrite_playbook", "ip_creation_playbook", "ip_recent_creation_memory", "ip_feedback_learnings"],
    "hook_enhancement": ["hook_playbook", "ip_creation_playbook", "ip_recent_creation_memory"],
    "risk_cleanup": ["global_risk_lexicon", "risk_cleanup_playbook", "ip_feedback_learnings"],
    "publish_format": ["publish_format_playbook", "ip_creation_playbook", "ip_recent_creation_memory"],
    "delivery": ["publish_format_playbook"],
}

ULTRA_HIGH_RISK_REPLACEMENTS = {
    "保证发财": "更容易守住机会",
    "保证有效": "更有机会看到变化",
    "百分百有效": "更有机会看到变化",
    "立马见效": "更快感受到变化",
    "一定成功": "更容易把事做成",
    "必定成功": "更容易把事做成",
    "注定发财": "更容易抓住机会",
    "必定发财": "更容易抓住机会",
    "必能转运": "状态更容易慢慢转顺",
    "招来大财": "更容易接住机会",
    "逆天改命": "让人生的走法慢慢变顺",
    "必定改命": "让人生的走法慢慢变顺",
}

# Backward-compatible name for callers/tests that still import the old constant.
HIGH_RISK_REPLACEMENTS = ULTRA_HIGH_RISK_REPLACEMENTS

SOURCE_CARRIED_RISK_TERMS = [
    "改命",
    "改运",
    "转运",
    "自带财运",
    "就是自带财运",
]

EDGE_RISK_TERMS = ["财运", "财气", "好运", "招财", "旺财", "福报", "因果", "气场", "开悟", "命运", "贵人", "修行", "能量", "磁场", "命理"]

GLOBAL_ASR_CORRECTIONS = {
    "挂失": "卦师",
    "看挂": "看卦",
    "道德经理": "道德经里",
    "人知道不足以": "人之道，损不足以奉有余",
    "有鱼": "有余",
    "清诉": "倾诉",
    "阮世": "软柿子",
    "本居自足": "本具自足",
    "柿子都会跳转的": "柿子都会挑软的",
}

AUTHORITY_FRAME_TERMS = [
    "卦师",
    "命理师",
    "师父",
    "教易学多年",
    "教了这么多年易学",
    "做咨询",
    "老师",
]

CONCRETE_PAIN_TERMS = [
    "财运",
    "事业",
    "磁场",
    "贵人",
    "客户",
    "机会",
    "关系",
    "钱",
    "内耗",
    "焦虑",
    "卡住",
    "不顺",
]

ABSTRACT_MORALIZING_TERMS = ["分寸", "节奏", "心性", "德行", "修心", "人生", "道理", "格局", "能量", "状态"]
INTERNAL_PROCESS_TERMS = ["原文", "素材", "文案", "底稿", "改写"]
PARALLEL_ENUM_MARKERS = ["第一", "第二", "第三"]
BRIDGE_STRUCTURE_TERMS = ["三个", "三点", "三层", "三种", "三类", "三处", "三方面", "三件"]
PARALLEL_LEAD_TERMS = ["看", "问", "查", "分", "把", "先", "别", "少", "多"]

DEFAULT_GLOBAL_REWRITE_PLAYBOOK = """# Global Rewrite Playbook

This file defines the cross-IP methodology for `rewrite_draft`. IP positioning, audience, vocabulary, topic boundaries, and business posture belong in the IP playbook.

## Stage Responsibility

`rewrite_draft` produces the first complete oral adaptation.

It must:

- preserve the source's proven reason for attention;
- preserve the source's primary content task and reusable value;
- adapt speaker position, evidence, and expression to the target IP;
- form one coherent oral argument within the task's length guardrail;
- defer hook polishing to `hook_enhancement`;
- defer all platform-risk replacement to `risk_cleanup`.

It must not become a summary, a new topic inspired by the source, a safety rewrite, or publish packaging.

## Priority

When inputs conflict, use this order:

1. confirmed task goal and target audience;
2. target IP persona and hard boundaries;
3. source content task, retention mechanism, speaker position, and must-keep value;
4. material understanding and stage feedback;
5. length, CTA, and surface polish.

Do not silently erase the source's strongest viral element. If it is incompatible with the task or IP, mark the material for reselection instead of disguising the loss as adaptation.

## Content Task And Mechanism

Before writing, separate three things:

- **Topic:** what the source talks about.
- **Content task:** what the source does for the viewer, such as warning, diagnosing, teaching, validating, provoking, building trust, or stimulating desire.
- **Mechanism:** why the viewer continues, such as conflict, identity, authority, loss, curiosity, recognition, scarcity, or proof.

A successful rewrite preserves the content task and mechanism, not merely the topic or information points. The wording and structure may change only as much as IP fit and oral clarity require.

## Source Discomfort And Objection

Viewer discomfort, disagreement, or resistance can be part of a proven retention mechanism. Do not automatically soften a hook because it may offend, challenge, or unsettle the audience.

Judge instead:

- whether the discomfort attracts the intended viewer;
- whether it creates a clear reason to continue;
- whether the body can address the core objection honestly;
- whether the claim remains compatible with platform and IP boundaries.

When a hook deliberately creates an objection, the body must process that objection. It may clarify the claim, explain the underlying mechanism, or give a way forward, but it must not quietly replace the original content task.

A strong attitude can itself be the source's reusable value and retention mechanism. Separate the stance from any risky execution detail: preserve the stance in `rewrite_draft`, then use explanation, conditions, or scene boundaries to make its intended meaning clear. Do not replace an opinionated claim with a neutral procedure merely because the procedure is easier to defend.

## Speaker Compatibility

Protect wording only after identifying who can credibly say it.

- When source and target IP share a credible speaker position, keep the opening literally or near-literally in `rewrite_draft`.
- When the source depends on an identity or first-person experience the target IP cannot claim, use `perspective_translation`.
- Perspective translation must preserve the original psychological entry point, conflict, viewer position, and information-release job.
- First-person evidence may remain as a quote, case, or dialogue when the target IP can credibly introduce and interpret it.

Record why perspective changed. Unexplained replacement is presumed to have lost source value.

## Adaptation Boundary

Use minimum necessary mutation:

- correct ASR errors and awkward oral phrasing;
- remove repetition that does not contribute to retention;
- translate incompatible identity, values, or context;
- add only what is needed to support the source claim, bridge logic, establish target-IP credibility, or fulfil a promise already made.

Do not add a generic lesson, forced uplift, unrelated theory, or standardized CTA merely to make the script feel complete.

If the source is too thin, off-audience, repetitive within the current batch, or only salvageable by replacing its core mechanism, return to material selection.

`rewrite_draft` accepts only a confirmed `formal_rewrite_base`. A `topic_clue` must trigger reselection even when its metrics or topic are attractive.

Do not confuse reorganization with reconstruction:

- reorganization compresses, reorders, bridges, or translates value already earned by the source;
- reconstruction supplies a new main claim, new evidence chain, or new conclusion because the source cannot support the target length.

When the current IP playbook is still immature or the task explicitly requires low originality, reconstruction is out of scope. Preserve the recorded `salvage_boundary`; if the script cannot be completed inside it, return the material instead of filling the gap with generic IP theory or a preferred script structure.

## Internal Logic

The script needs one main claim and a continuous reasoning path. It does not need a universal sequence of hook, case, list, advice, and CTA.

Each component is optional unless the source or task requires it. What matters is that:

- the opening creates a contract the body actually fulfils;
- evidence supports the claim it is attached to;
- clarification answers a real objection created by the script;
- advice follows from the explanation rather than appearing as a generic add-on;
- the ending completes the current content task instead of switching to another one.

Record this as `internal_logic_alignment`.

## Oral Integrity

Expression integrity comes before length control.

- Keep subjects, actions, and objects clear.
- Keep perspective and pronouns stable.
- Prefer concrete actions and recognizable situations over abstract noun chains.
- Preserve useful emotional pressure without making sentences cramped.
- Read adjacent sentences aloud; wording that is logically guessable but hard to say fails.

Length is a guardrail set by the task or IP, not a target to hit by force. Rich material may use the upper part of the range. Thin material should be reselected rather than expanded with outside claims.

## CTA And Conversion

CTA is optional.

Use interaction only when it naturally continues the content value or the IP's current business goal. Choose the minimum necessary action and information request. Do not stack actions, expose unnecessary private information, or let conversion replace retention.

Publish-platform preferences belong in the IP or publish-format layer, not in the core rewrite structure.

## Stage Boundaries

- `rewrite_draft`: protect source task, mechanism, opening, value, and logic. Record risk; do not solve it.
- `hook_enhancement`: make the smallest useful opening adjustment. Do not change the content task or body logic.
- `risk_cleanup`: replace only the unsafe span. Do not use safety as permission for a second rewrite.
- `publish_format`: package the cleaned body without editing it.

## Quality Gates

Hard gates:

- source content task and retention mechanism are preserved;
- source opening is exact or near-literal unless speaker incompatibility is recorded;
- the script fits the target audience and confirmed IP;
- the body fulfils the opening's promise and handles any deliberate core objection;
- added content is earned by the source claim or task goal;
- risk replacement is deferred;
- viewer-facing copy contains no internal workflow language;
- the oral script stays inside the applicable length guardrail without sacrificing clarity.

Soft signals:

- the intended viewer recognizes the relevance early;
- authority is demonstrated through judgment or evidence, not merely claimed;
- concrete evidence carries abstract explanation when useful;
- emotional force remains comparable to the source;
- the ending feels like the natural completion of the same argument.

## Output Contract

Return:

- `draft_text`;
- `char_count`;
- `hook_preservation`;
- `opening_preservation_mode`;
- `kept_source_elements`;
- `ip_adaptation_notes`;
- `conversion_goal_alignment`;
- `deferred_risk_terms`;
- quality checks including `internal_logic_alignment`.
"""


def create_creation_task(
    store: Store,
    *,
    role_id: str,
    topic: str,
    goal: str,
    platform: str,
    target_count: int,
    provider: str = DEFAULT_CREATION_PROVIDER,
    model: str = DEFAULT_CREATION_MODEL,
    allow_reuse_material: bool = False,
) -> dict[str, Any]:
    role = _confirmed_role(store, role_id)
    if target_count < 1:
        raise ValueError("--target-count must be >= 1")
    task_id = store.create_creation_task(
        role_id=role["id"],
        topic=topic,
        goal=goal,
        platform=platform,
        target_count=target_count,
        provider=provider,
        model=model,
        allow_reuse_material=allow_reuse_material,
        context={
            "role_name": role["name"],
            "creation_methodology_version": CREATION_METHODOLOGY_VERSION,
            "rewrite_requirements": {
                "target_length_range": list(DEFAULT_TARGET_LENGTH_RANGE),
                "target_length_strategy": "upper_bound_for_long_source",
                "must_preserve_source_hook": True,
                "preserve_source_opening_on_first_draft": True,
                "source_value_policy": "identify_then_preserve_translate_or_discard",
                "cta_policy": "soft_when_task_goal_requires_conversion",
            },
        },
    )
    return build_creation_task_report(store, task_id)


def run_creation_stage(
    store: Store,
    task_id: str,
    *,
    stage_key: str,
    knowledge_root: Path,
    note: str = "",
) -> dict[str, Any]:
    if stage_key not in CREATION_STAGES:
        raise ValueError(f"unknown creation stage: {stage_key}")
    task = _task(store, task_id)
    _confirmed_role(store, str(task["role_id"]))
    _assert_previous_stage_confirmed(store, task_id, stage_key)
    if stage_key == "material_selection":
        output, markdown = _run_material_selection(store, task)
    elif stage_key == "creation_brief":
        output, markdown = _run_creation_brief(store, task, knowledge_root)
    elif stage_key == "rewrite_draft":
        output, markdown = _run_rewrite_draft(store, task, knowledge_root)
    elif stage_key == "hook_enhancement":
        output, markdown = _run_hook_enhancement(store, task)
    elif stage_key == "risk_cleanup":
        output, markdown = _run_risk_cleanup(store, task)
    elif stage_key == "publish_format":
        output, markdown = _run_publish_format(store, task)
    else:
        output, markdown = _run_delivery(store, task)
    upstream_stage_run_ids = _upstream_stage_run_ids(store, task_id, stage_key)
    output = _attach_stage_contract(store, task, stage_key, output, upstream_stage_run_ids)
    status = str(output.get("status") or "needs_confirmation")
    stage_run_id = store.insert_creation_stage_run(
        task_id=task_id,
        stage_key=stage_key,
        status=status,
        provider=str(task.get("provider") or DEFAULT_CREATION_PROVIDER),
        model=str(task.get("model") or DEFAULT_CREATION_MODEL),
        input_data={
            "task_id": task_id,
            "stage_key": stage_key,
            "note": note,
            "stage_contract_version": CREATION_STAGE_CONTRACT_VERSION,
            "upstream_stage_run_ids": upstream_stage_run_ids,
        },
        output_data=output,
        output_markdown=markdown,
        note=note,
    )
    _persist_stage_artifacts(store, task, stage_key, stage_run_id, output)
    if stage_key == "material_selection":
        store.update_creation_task(task_id, status="material_selected")
    else:
        store.update_creation_task(task_id, status=stage_key)
    return {
        "task": store.get_creation_task(task_id),
        "stage_run": store.latest_creation_stage_run(task_id, stage_key),
        "output": output,
    }


def confirm_creation_stage(store: Store, task_id: str, *, stage_key: str) -> dict[str, Any]:
    if stage_key not in CREATION_STAGES:
        raise ValueError(f"unknown creation stage: {stage_key}")
    stage = store.latest_creation_stage_run(task_id, stage_key)
    if not stage:
        raise ValueError(f"stage has not run: {stage_key}")
    if stage.get("status") == "needs_retry":
        raise ValueError(f"stage {stage_key} failed contract validation; rerun before confirming")
    store.update_creation_stage_status(stage["id"], "confirmed")
    if stage_key == "publish_format":
        task = store.get_creation_task(task_id) or {}
        store.update_creation_task(task_id, status="ready_to_publish", completed=True)
    return build_creation_task_report(store, task_id)


def build_creation_context_packet(
    store: Store,
    task_id: str,
    *,
    knowledge_root: Path,
    stage_key: str | None = None,
    include_transcript: bool = False,
) -> dict[str, Any]:
    if stage_key is not None and stage_key not in CREATION_STAGES:
        raise ValueError(f"unknown creation stage: {stage_key}")
    task = _task(store, task_id)
    role = _confirmed_role(store, str(task["role_id"]))
    all_knowledge_files = ensure_knowledge_pack(knowledge_root, role)
    knowledge_files = _knowledge_files_for_stage(all_knowledge_files, stage_key)
    selected = _selected_materials(store, task_id)
    selection_output = _latest_output(store, task_id, "material_selection")
    source_analysis = selection_output.get("source_analysis") or {}
    materials = [
        _material_packet(
            material,
            include_transcript=include_transcript,
            source_analysis=source_analysis.get(material["id"]) or {},
        )
        for material in selected
    ]
    return {
        "task": {
            "id": task["id"],
            "topic": task["topic"],
            "goal": task["goal"],
            "platform": task["platform"],
            "target_count": task["target_count"],
        },
        "task_context": task.get("context") or {},
        "stage_key": stage_key or "workflow_overview",
        "stage_contract_version": CREATION_STAGE_CONTRACT_VERSION,
        "stage_contract": _stage_contract_descriptor(stage_key),
        "upstream_stage_run_ids": _upstream_stage_run_ids(store, task_id, stage_key) if stage_key else [],
        "rewrite_requirements": _rewrite_requirements(task, role),
        "persona_packet": role.get("persona_packet") or {},
        "knowledge_files": knowledge_files,
        "knowledge": {key: Path(path).read_text(encoding="utf-8") for key, path in knowledge_files.items()},
        "selected_materials": materials,
        "source_analysis": source_analysis,
        "brief": _latest_output(store, task_id, "creation_brief").get("brief") or {},
        "stage_feedback": store.list_creation_stage_feedback_events(task_id=task_id)[:10],
        "role_stage_feedback": store.list_creation_stage_feedback_events(role_id=role["id"])[:10],
    }


def build_creation_task_report(store: Store, task_id: str) -> dict[str, Any]:
    task = _task(store, task_id)
    role = store.get_ip_role(str(task["role_id"])) or {}
    stages = store.list_creation_stage_runs(task_id)
    selections = store.list_creation_material_selections(task_id)
    drafts = store.list_creation_drafts(task_id)
    deliveries = store.list_creation_delivery_packages(task_id)
    return {
        "task": task,
        "role": {"id": role.get("id"), "name": role.get("name"), "confirmation_status": role.get("confirmation_status")},
        "stages": stages,
        "selected_materials": selections,
        "drafts": drafts,
        "delivery_packages": deliveries,
    }


def format_creation_task_report_markdown(report: dict[str, Any]) -> str:
    task = report["task"]
    lines = [
        f"# Creation Task {task['id']}",
        "",
        f"- IP: {report['role'].get('name') or task['role_id']}",
        f"- Topic: {task['topic']}",
        f"- Goal: {task['goal']}",
        f"- Platform: {task['platform']}",
        f"- Status: {task['status']}",
        "",
        "## Stages",
    ]
    for stage in report.get("stages") or []:
        lines.append(f"- {stage['stage_key']} v{stage['version']}: {stage['status']}")
    lines.append("")
    lines.append("## Selected Materials")
    for item in report.get("selected_materials") or []:
        lines.append(f"- {item['material_id']} score={item['score']:.2f} {item['reason']}")
    lines.append("")
    lines.append("## Drafts")
    for draft in report.get("drafts") or []:
        lines.append(f"- {draft['draft_type']} {draft['id']}: {draft['title']}")
    return "\n".join(lines).strip() + "\n"


def export_creation_task_markdown(store: Store, task_id: str) -> str:
    report = build_creation_task_report(store, task_id)
    lines = [format_creation_task_report_markdown(report)]
    for stage in report.get("stages") or []:
        if stage.get("output_markdown"):
            lines.extend(["", f"## {stage['stage_key']} v{stage['version']}", "", stage["output_markdown"]])
    return "\n".join(lines).strip() + "\n"


def _knowledge_files_for_stage(files: dict[str, str], stage_key: str | None) -> dict[str, str]:
    if stage_key is None:
        return files
    allowed = STAGE_KNOWLEDGE_KEYS.get(stage_key, [])
    return {key: files[key] for key in allowed if key in files}


def _stage_contract_descriptor(stage_key: str | None) -> dict[str, Any]:
    if not stage_key:
        return {"mode": "workflow_overview", "version": CREATION_STAGE_CONTRACT_VERSION}
    descriptors = {
        "material_selection": {
            "allowed_outputs": ["selected", "source_analysis", "skipped"],
            "forbidden_outputs": sorted(VIEWER_COPY_OUTPUT_KEYS),
        },
        "creation_brief": {
            "allowed_outputs": ["brief"],
            "forbidden_outputs": ["body", "draft_text", "cleaned_body", "publish_package", "replacement_phrases"],
        },
        "rewrite_draft": {
            "allowed_outputs": ["draft_text", "opening_preservation_mode", "deferred_risk_terms", "quality_checks"],
            "forbidden_outputs": ["high_risk_replacements", "risk_replacement_scope", "publish_package"],
        },
        "hook_enhancement": {
            "allowed_outputs": ["selected_hook", "body", "hook_diff_type", "mechanism_preserved"],
            "forbidden_outputs": ["high_risk_replacements", "publish_package"],
        },
        "risk_cleanup": {
            "allowed_outputs": ["cleaned_body", "high_risk_replacements", "unchanged_source_risk_terms", "risk_replacement_scope"],
            "forbidden_outputs": ["cover_title_4", "video_title_18", "publish_package"],
        },
        "publish_format": {
            "allowed_outputs": ["publish_package", "body_char_count"],
            "forbidden_outputs": ["cleaned_body", "high_risk_replacements"],
        },
        "delivery": {
            "allowed_outputs": ["delivery_markdown"],
            "forbidden_outputs": ["draft_text", "cleaned_body"],
        },
    }
    return {"stage_key": stage_key, "version": CREATION_STAGE_CONTRACT_VERSION, **descriptors.get(stage_key, {})}


def _upstream_stage_run_ids(store: Store, task_id: str, stage_key: str | None) -> list[str]:
    if not stage_key or stage_key not in CREATION_STAGES:
        return []
    index = CREATION_STAGES.index(stage_key)
    ids: list[str] = []
    for upstream in CREATION_STAGES[:index]:
        stage = store.latest_creation_stage_run(task_id, upstream)
        if stage:
            ids.append(str(stage["id"]))
    return ids


def _attach_stage_contract(
    store: Store,
    task: dict[str, Any],
    stage_key: str,
    output: dict[str, Any],
    upstream_stage_run_ids: list[str],
) -> dict[str, Any]:
    result = dict(output)
    result["stage_contract_version"] = CREATION_STAGE_CONTRACT_VERSION
    result["upstream_stage_run_ids"] = upstream_stage_run_ids
    result["artifact_type"] = f"{stage_key}_output"
    body_text = _stage_body_text(stage_key, result)
    if body_text:
        result["body_hash"] = _content_hash(body_text)
    validation = _validate_stage_contract(store, task, stage_key, result)
    result["stage_contract_validation"] = validation
    if not validation["passed"]:
        result["status"] = "needs_retry"
    return result


def _validate_stage_contract(store: Store, task: dict[str, Any], stage_key: str, output: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    if stage_key == "material_selection":
        forbidden = sorted(VIEWER_COPY_OUTPUT_KEYS & set(output))
        checks["no_viewer_copy"] = {"passed": not forbidden, "forbidden_keys": forbidden}
        checks["has_source_analysis"] = {"passed": bool(output.get("source_analysis")), "source_count": len(output.get("source_analysis") or {})}
    elif stage_key == "creation_brief":
        brief = output.get("brief") or {}
        forbidden = sorted((VIEWER_COPY_OUTPUT_KEYS - {"draft"}) & set(output))
        replacement_keys = [key for key in brief if "replacement" in str(key).lower()]
        checks["no_viewer_copy"] = {"passed": not forbidden, "forbidden_keys": forbidden}
        checks["risk_policy_deferred"] = {"passed": brief.get("risk_policy") == "defer_to_risk_cleanup", "risk_policy": brief.get("risk_policy")}
        checks["no_replacement_phrases"] = {"passed": not replacement_keys, "replacement_keys": replacement_keys}
    elif stage_key == "rewrite_draft":
        draft_text = str(output.get("draft_text") or (output.get("draft") or {}).get("draft_text") or "")
        opening = ((output.get("quality_checks") or {}).get("opening_preservation") or {})
        checks["opening_preserved"] = {"passed": bool(opening.get("passed")), "mode": opening.get("mode")}
        checks["no_cleanup_outputs"] = {
            "passed": not any(key in output for key in ["high_risk_replacements", "risk_replacement_scope"]),
            "forbidden_keys": [key for key in ["high_risk_replacements", "risk_replacement_scope"] if key in output],
        }
        leaked = _rewrite_risk_replacement_leaks(store, task["id"], draft_text)
        checks["risk_replacement_not_done"] = {"passed": not leaked, "leaked_replacements": leaked}
    elif stage_key == "hook_enhancement":
        hook_validation = output.get("validation") or {}
        checks["minimal_hook_diff"] = {
            "passed": bool(hook_validation.get("passed")) and output.get("hook_diff_type") != "replaced",
            "hook_diff_type": output.get("hook_diff_type"),
            "mechanism_preserved": output.get("mechanism_preserved"),
        }
    elif stage_key == "risk_cleanup":
        scope = output.get("risk_replacement_scope") or {}
        checks["localized_replacement_only"] = {"passed": bool(scope.get("passed", True)), "scope": scope}
        checks["has_cleaned_body"] = {"passed": bool(str(output.get("cleaned_body") or "").strip())}
    elif stage_key == "publish_format":
        package = output.get("publish_package") or {}
        risk = _latest_output(store, task["id"], "risk_cleanup")
        cleaned_body = str(risk.get("cleaned_body") or "")
        final_copy = str(package.get("final_copy") or "")
        checks["final_copy_matches_risk_cleaned_body"] = {
            "passed": final_copy == cleaned_body,
            "final_copy_hash": _content_hash(final_copy) if final_copy else "",
            "risk_cleaned_hash": _content_hash(cleaned_body) if cleaned_body else "",
        }
        checks["has_publish_fields"] = {
            "passed": all(package.get(key) for key in ["cover_title_4", "video_title_18", "description_100", "pinned_comment", "final_copy"]),
            "missing": [key for key in ["cover_title_4", "video_title_18", "description_100", "pinned_comment", "final_copy"] if not package.get(key)],
        }
    else:
        checks["delivery_only"] = {"passed": "delivery_markdown" in output}
    passed = all(check.get("passed") for check in checks.values())
    return {"passed": passed, "checks": checks}


def _rewrite_risk_replacement_leaks(store: Store, task_id: str, draft_text: str) -> list[dict[str, str]]:
    source_text = _task_source_text(store, task_id)
    leaks: list[dict[str, str]] = []
    for term, replacement in ULTRA_HIGH_RISK_REPLACEMENTS.items():
        if term in source_text and term not in draft_text and replacement in draft_text:
            leaks.append({"term": term, "replacement": replacement})
    return leaks


def _stage_body_text(stage_key: str, output: dict[str, Any]) -> str:
    if stage_key == "rewrite_draft":
        return str(output.get("draft_text") or (output.get("draft") or {}).get("draft_text") or "")
    if stage_key == "hook_enhancement":
        return str(output.get("body") or "")
    if stage_key == "risk_cleanup":
        return str(output.get("cleaned_body") or "")
    if stage_key == "publish_format":
        package = output.get("publish_package") or {}
        return str(package.get("final_copy") or "")
    if stage_key == "delivery":
        return str(output.get("delivery_markdown") or "")
    return ""


def _content_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def generate_learning_update_proposals(
    store: Store,
    *,
    role_id: str,
    knowledge_root: Path,
) -> dict[str, Any]:
    role = _confirmed_role(store, role_id)
    files = ensure_knowledge_pack(knowledge_root, role)
    events = store.list_creation_feedback_events(role_id=role_id)
    stage_events = store.list_creation_stage_feedback_events(role_id=role_id)
    observations = store.list_risk_term_observations(role_id=role_id)
    if not events and not stage_events and not observations:
        proposed = "\n## 反馈学习\n\n- 暂无足够反馈样本，继续观察。\n"
    else:
        event_lines = [
            f"- {event['created_at']} {event['platform']} judgment={event.get('judgment') or '未标注'} note={event.get('human_note') or event.get('notice') or '无'}"
            for event in events[:10]
        ]
        stage_event_lines = [
            f"- {event['created_at']} {event['stage_key']} judgment={event.get('judgment') or '未标注'} note={event.get('human_note') or '无'}"
            for event in stage_events[:10]
        ]
        risk_terms = sorted({item["term"] for item in observations[:20]})
        proposed = "\n".join(
            [
                "",
                "## 反馈学习",
                "",
                "### 作品层信号",
                *(event_lines or ["- 暂无作品层反馈。"]),
                "",
                "### 创作阶段反馈",
                *(stage_event_lines or ["- 暂无创作阶段反馈。"]),
                "",
                "### 词汇层观察",
                *(f"- {term}" for term in risk_terms),
                "",
            ]
        )
    update_id = store.insert_creation_learning_update(
        role_id=role_id,
        target_file=files["ip_feedback_learnings"],
        proposed_markdown=proposed,
        source_event_ids=[event["id"] for event in events[:10]] + [event["id"] for event in stage_events[:10]],
    )
    return {"update_id": update_id, "proposal": store.get_creation_learning_update(update_id)}


def apply_learning_update(store: Store, update_id: str) -> dict[str, Any]:
    update = store.get_creation_learning_update(update_id)
    if not update:
        raise KeyError(f"creation learning update not found: {update_id}")
    if update["status"] != "pending":
        raise ValueError(f"learning update is {update['status']}, not pending")
    target = Path(update["target_file"])
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    target.write_text(existing.rstrip() + "\n" + update["proposed_markdown"].strip() + "\n", encoding="utf-8")
    store.update_creation_learning_update_status(update_id, "applied")
    return store.get_creation_learning_update(update_id) or update


def ensure_knowledge_pack(root: Path, role: dict[str, Any]) -> dict[str, str]:
    role_slug = _role_slug(role)
    files = {
        "material_selection_playbook": root / "creation" / "material-selection-playbook.md",
        "creation_brief_playbook": root / "creation" / "creation-brief-playbook.md",
        "global_rewrite_playbook": root / "creation" / "global-rewrite-playbook.md",
        "global_risk_lexicon": root / "creation" / "global-risk-lexicon.md",
        "risk_cleanup_playbook": root / "creation" / "risk-cleanup-playbook.md",
        "hook_playbook": root / "creation" / "hook-playbook.md",
        "publish_format_playbook": root / "creation" / "publish-format-playbook.md",
        "ip_creation_playbook": root / "ip" / role_slug / "creation-playbook.md",
        "ip_feedback_learnings": root / "ip" / role_slug / "feedback-learnings.md",
        "ip_recent_creation_memory": root / "ip" / role_slug / "recent-creation-memory.md",
    }
    defaults = {
        "material_selection_playbook": "# Material Selection Playbook\n\n- 判断受众与 IP 适配、源内容任务、传播机制、说话者兼容性和可改写余量。\n- 只有下游必须另造一个内容任务才能成立时，才判为不适合二创。\n- 只输出选择依据；不改写正文，不生成发布文案，不提前做风险替换。\n",
        "creation_brief_playbook": "# Creation Brief Playbook\n\n- 只把素材转成写作任务说明：留人机制、必须保留元素、正文逻辑计划、CTA 适配判断和风险后置策略。\n- 风险字段只记录 `risk_policy: defer_to_risk_cleanup` 和观察词，不给替换句。\n- brief 不能写出完整正文，也不能把风险意识改写成开头方向。\n",
        "global_rewrite_playbook": DEFAULT_GLOBAL_REWRITE_PLAYBOOK,
        "global_risk_lexicon": "# Global Risk Lexicon\n\n- 超高风险：保证发财、保证有效、百分百有效、立马见效、一定成功、必定成功、必能转运、注定发财、逆天改命、明确医疗/金融/法律/宗教结果承诺。\n- 源文案携带风险：改命、改运、转运、自带财运等，默认记录并后置，不在 rewrite_draft 或 hook_enhancement 阶段替换。\n- 边缘观察：财运、财气、好运、招财、旺财、福报、因果、气场、开悟、命运、贵人、修行、能量、磁场。\n- risk_cleanup 只局部替换超高风险词；源文案携带词和边缘词默认观察，不机械删除。\n",
        "risk_cleanup_playbook": "# Risk Cleanup Playbook\n\n- 只处理超高风险表达，且只替换命中的短语。\n- 不重写整句，不改变钩子机制，不把风险软化成解释性降温。\n- 原文案携带的财运、命运、贵人、磁场、能量、福报等语境词默认记录观察。\n- 如果风险词位于开头，只替换风险短语，保留原开头的主体、数量钩子、节奏和情绪力度。\n- 风险表达同时承载核心态度时，先用主体、对象、条件或场景限定其含义；只有限定后仍不可发布，才删除立场本身。\n",
        "hook_playbook": "# Hook Playbook\n\n- 保护原钩子的传播任务和强度，不以改动幅度衡量二创质量。\n- 原说话者与目标 IP 兼容时优先保留；不兼容时做 `perspective_translation`，重建可信入口而不是照搬身份。\n- 反感、异议或反常识可能就是留人机制，不要在开头主动消解。\n- 通过 strength parity 检查冲突、具体性、受众入口、态度强度和继续观看理由。\n- 当留人机制是鲜明立场时，不能用警示、信息差或中性后果替换。\n- 本阶段不重写正文，也不承担风险清理。\n",
        "publish_format_playbook": "# Publish Format Playbook\n\n- 只根据 risk cleanup 后正文生成发布包装。\n- 输出四字封面标题、十八字视频标题、视频描述、置顶评论、最终可复制文案和正文字数。\n- 最终可复制文案必须等于 risk cleanup 后正文；不得在发布包装阶段重写正文逻辑。\n",
        "ip_creation_playbook": f"# {role.get('name') or role_slug} Creation Playbook\n\n- 只记录相对于全局规则真正不同的角色定位、受众张力、专业解释方式和禁区。\n- 不固化开头句式、正文组件、案例结构或 CTA 模板。\n",
        "ip_feedback_learnings": f"# {role.get('name') or role_slug} Feedback Learnings\n\n- 发布后的作品层和词汇层反馈写在这里。\n",
        "ip_recent_creation_memory": f"# {role.get('name') or role_slug} Recent Creation Memory\n\n- 记录近期已写主题、论据和结构，避免重复。\n",
    }
    for key, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(defaults[key], encoding="utf-8")
    return {key: str(path) for key, path in files.items()}


def _run_material_selection(store: Store, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    selected = select_creation_materials(store, task)
    source_analysis: dict[str, Any] = {}
    for item in selected["selected"]:
        material = store.get_collected_material(item["material_id"])
        if material:
            source_analysis[material["id"]] = _analyze_source_material(material, task)
    markdown = "\n".join(
        [
            "# Material Selection",
            "",
            *[
                f"- {item['material_id']} score={item['score']:.2f}: {item['reason']}"
                for item in selected["selected"]
            ],
            "",
            "## Source Analysis",
            *[
                f"- {material_id}: hook={analysis.get('source_hook_text') or ''}; authority={analysis.get('authority_frame') or ''}"
                for material_id, analysis in source_analysis.items()
            ],
        ]
    )
    return {**selected, "source_analysis": source_analysis, "status": "needs_confirmation"}, markdown


def select_creation_materials(store: Store, task: dict[str, Any]) -> dict[str, Any]:
    role_id = str(task["role_id"])
    topic = str(task.get("topic") or "")
    target_count = int(task.get("target_count") or 1)
    allow_reuse = bool(task.get("allow_reuse_material"))
    role = store.get_ip_role(role_id) or {}
    explicit_material_ids = _explicit_selected_material_ids(task)
    if explicit_material_ids:
        return _select_explicit_creation_materials(store, task, role_id=role_id, material_ids=explicit_material_ids)
    matches = {item["material_id"]: item for item in store.list_material_role_matches(role_id=role_id)}
    used_ids = {
        item["material_id"]
        for item in store.list_material_creations(role_id=role_id)
    }
    candidates: list[tuple[float, dict[str, Any], str]] = []
    skipped: list[dict[str, Any]] = []
    for material in store.list_collected_materials(status="collected"):
        if material.get("eligibility_status") != "accepted":
            skipped.append({"material_id": material["id"], "reason": "not_eligible"})
            continue
        if material["id"] in used_ids and not allow_reuse:
            skipped.append({"material_id": material["id"], "reason": "already_used_by_role"})
            continue
        text = _material_search_text(material)
        topic_hit = 1 if topic and topic in text else 0
        role_terms = list(role.get("search_keywords") or []) + list(role.get("fit_themes") or [])
        role_hit_count = len([term for term in role_terms if term and str(term) in text])
        match = matches.get(material["id"])
        match_score = float(match.get("fit_score") or 0) if match and match.get("decision") == "accepted" else 0.0
        score = match_score + topic_hit * 0.35 + min(role_hit_count, 4) * 0.12 + float(material.get("knowledge_core_score") or 0) * 0.2
        if score <= 0 and topic not in text:
            skipped.append({"material_id": material["id"], "reason": "low_topic_role_fit"})
            continue
        reason = _selection_reason(material, topic_hit=topic_hit, role_hit_count=role_hit_count, match_score=match_score)
        candidates.append((score, material, reason))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for score, material, reason in candidates[:target_count]:
        store.upsert_creation_material_selection(
            task_id=task["id"],
            material_id=material["id"],
            role_id=role_id,
            selection_status="selected",
            score=score,
            reason=reason,
            metadata={
                "clean_title": material.get("clean_title") or material.get("title"),
                "content_type": material.get("content_type"),
                "summary_text": material.get("summary_text"),
            },
        )
        selected.append({"material_id": material["id"], "score": round(score, 3), "reason": reason})
    return {"selected": selected, "skipped_count": len(skipped), "skipped": skipped[:30]}


def _run_creation_brief(store: Store, task: dict[str, Any], knowledge_root: Path) -> tuple[dict[str, Any], str]:
    packet = build_creation_context_packet(store, task["id"], knowledge_root=knowledge_root, stage_key="creation_brief")
    materials = packet["selected_materials"]
    if not materials:
        raise ValueError("no selected materials; run and confirm material_selection first")
    requirements = packet["rewrite_requirements"]
    key_points: list[str] = []
    source_keep: list[str] = []
    source_discard: list[str] = []
    deferred_risk_terms: list[dict[str, Any]] = []
    for material in materials:
        key_points.extend(str(item) for item in material.get("key_points") or [])
        analysis = material.get("source_analysis") or {}
        source_keep.extend(str(item) for item in analysis.get("must_keep_elements") or [])
        source_discard.extend(str(item) for item in analysis.get("discard_elements") or [])
        deferred_risk_terms.extend(dict(item) for item in analysis.get("deferred_risk_terms") or [])
    brief = {
        "target_ip": packet["persona_packet"].get("target_ip"),
        "topic": task["topic"],
        "goal": task["goal"],
        "platform": task["platform"],
        "main_claim": materials[0].get("core_claim") or materials[0].get("summary_text") or task["topic"],
        "retention_mechanism": (materials[0].get("source_analysis") or {}).get("source_hook_mechanism") or "",
        "must_keep": _dedupe([materials[0].get("source_analysis", {}).get("source_hook_text"), materials[0].get("hook_text"), *source_keep, *key_points[:4]]),
        "must_keep_elements": _dedupe([materials[0].get("source_analysis", {}).get("source_hook_text"), materials[0].get("hook_text"), *source_keep, *key_points[:4]]),
        "avoid": _dedupe((packet["persona_packet"].get("avoid_themes") or []) + (packet["persona_packet"].get("forbidden_expressions") or []) + source_discard),
        "rewrite_strategy": "high_fidelity_retention_mechanism_rewrite",
        "body_logic_plan": _body_logic_plan(materials[0], task),
        "cta_fit_decision": _cta_fit_decision(task, packet["persona_packet"]),
        "risk_policy": "defer_to_risk_cleanup",
        "deferred_risk_terms": _dedupe_risk_terms(deferred_risk_terms),
        "stage_boundary": "creation_brief only records risk; rewrite_draft must not replace source risk terms",
        "source_material_ids": [material["id"] for material in materials],
        "rewrite_requirements": requirements,
    }
    markdown = "\n".join(
        [
            "# Creation Brief",
            "",
            f"- IP: {brief['target_ip']}",
            f"- Topic: {brief['topic']}",
            f"- Main claim: {brief['main_claim']}",
            f"- Must keep: {'; '.join(brief['must_keep'])}",
            f"- Avoid: {'; '.join(brief['avoid'])}",
            f"- Deferred risk terms: {'; '.join(item['term'] for item in brief['deferred_risk_terms'])}",
            f"- Target length: {requirements['target_length_range'][0]}-{requirements['target_length_range'][1]} Chinese chars",
        ]
    )
    return {"brief": brief, "knowledge_file_count": len(packet["knowledge_files"]), "status": "needs_confirmation"}, markdown


def _run_rewrite_draft(store: Store, task: dict[str, Any], knowledge_root: Path) -> tuple[dict[str, Any], str]:
    packet = build_creation_context_packet(store, task["id"], knowledge_root=knowledge_root, stage_key="rewrite_draft")
    brief = packet["brief"]
    material = packet["selected_materials"][0]
    persona = packet["persona_packet"]
    requirements = packet["rewrite_requirements"]
    source_analysis = material.get("source_analysis") or {}
    body = _compose_rewrite_body(task, persona, material, brief, source_analysis, requirements)
    validation = _validate_rewrite_draft(body, source_analysis, requirements)
    status = "needs_confirmation" if _rewrite_stage_boundary_passed(validation) else "needs_retry"
    hook_text = source_analysis.get("source_hook_text") or material.get("hook_text") or ""
    authority_frame = _authority_frame_for_draft(task, persona, source_analysis)
    kept_source_elements = _kept_source_elements(body, source_analysis)
    deferred_risk_terms = validation.get("deferred_risk_terms") or []
    opening_preservation = validation["checks"].get("opening_preservation") or {}
    draft = {
        "title": str(material.get("clean_title") or task["topic"])[:40],
        "body": body,
        "draft_text": body,
        "char_count": _script_char_count(body),
        "source_material_id": material["id"],
        "source_opening_text": source_analysis.get("source_opening_text") or "",
        "opening_preservation_mode": opening_preservation.get("mode") or "",
        "preserved_hook_text": hook_text,
        "hook_preservation": validation["checks"].get("hook_preservation") or {},
        "authority_frame": authority_frame,
        "kept_source_elements": kept_source_elements,
        "ip_adaptation_notes": _ip_adaptation_notes(task, persona, source_analysis),
        "conversion_goal_alignment": _conversion_goal_alignment(task, persona, body),
        "risk_notes": validation["risk_notes"],
        "deferred_risk_terms": deferred_risk_terms,
        "validation": validation,
        "rewrite_notes": ["先识别爆款元素", "原文开头进入保护区", "风险词只记录并后置", "避免把内容改成泛泛大道理"],
    }
    markdown = "# Rewrite Draft\n\n" + body
    return {
        "draft": draft,
        "draft_text": body,
        "char_count": draft["char_count"],
        "hook_preservation": draft["hook_preservation"],
        "kept_source_elements": kept_source_elements,
        "ip_adaptation_notes": draft["ip_adaptation_notes"],
        "conversion_goal_alignment": draft["conversion_goal_alignment"],
        "risk_notes": validation["risk_notes"],
        "deferred_risk_terms": deferred_risk_terms,
        "opening_preservation_mode": draft["opening_preservation_mode"],
        "quality_checks": validation["checks"],
        "status": status,
        "creation_mode": "structured_creation_methodology_v2",
    }, markdown


def _run_hook_enhancement(store: Store, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    draft = _latest_draft(store, task["id"], "rewrite_draft")
    body = draft.get("body") or ""
    metadata = draft.get("metadata") or {}
    first_line = body.splitlines()[0] if body else f"{task['topic']}这件事，很多人都想错了。"
    source_opening = str(metadata.get("source_opening_text") or first_line)
    hooks = _dedupe(_minimal_hook_variants(first_line))
    enhanced = body if body.startswith(hooks[0]) else hooks[0] + "\n\n" + body
    hook_validation = _validate_hook_enhancement(
        source_opening=source_opening,
        selected_hook=hooks[0],
        original_body=body,
        enhanced_body=enhanced,
    )
    output = {
        "hooks": hooks,
        "selected_hook": hooks[0],
        "body": enhanced,
        "source_opening_text": source_opening,
        "hook_diff_type": hook_validation["diff_type"],
        "mechanism_preserved": hook_validation["mechanism_preserved"],
        "dedup_change_summary": hook_validation["change_summary"],
        "validation": hook_validation,
        "status": DRAFT_LOCAL_CREATION_STATUS if hook_validation["passed"] else "needs_retry",
        "creation_mode": "minimal_hook_enhancement_boundary_v1",
    }
    return output, "# Hook Enhancement\n\n" + "\n".join(f"- {hook}" for hook in hooks)


def _run_risk_cleanup(store: Store, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    draft = _latest_draft(store, task["id"], "hook_enhancement") or _latest_draft(store, task["id"], "rewrite_draft")
    original = draft.get("body") or ""
    source_text = _task_source_text(store, task["id"])
    cleaned = original
    replacements = []
    for term, replacement in ULTRA_HIGH_RISK_REPLACEMENTS.items():
        if term in cleaned:
            cleaned = cleaned.replace(term, replacement)
            replacements.append(
                {
                    "term": term,
                    "replacement": replacement,
                    "reason": "超高风险结果承诺或命运操控表达，仅在 risk_cleanup 局部替换",
                    "origin": "source" if term in source_text else "generated",
                }
            )
            store.insert_risk_term_observation(
                role_id=task["role_id"],
                task_id=task["id"],
                term=term,
                risk_level="超高风险",
                status="已替换",
                sample_text=original[:180],
            )
    source_carried_terms = []
    for term in SOURCE_CARRIED_RISK_TERMS:
        if term in cleaned and term in source_text:
            source_carried_terms.append(
                {
                    "term": term,
                    "status": "保留观察",
                    "observation": "源文案携带风险词，不在 rewrite/hook 阶段替换，risk_cleanup 也只记录不扩写",
                }
            )
            store.insert_risk_term_observation(
                role_id=task["role_id"],
                task_id=task["id"],
                term=term,
                risk_level="源文案携带高风险",
                status="保留观察",
                sample_text=cleaned[:180],
            )
    edge_terms = []
    for term in EDGE_RISK_TERMS:
        if term in cleaned and term not in {item["term"] for item in source_carried_terms}:
            edge_terms.append({"term": term, "status": "待验证", "observation": "边缘词，保留但进入观察"})
            store.insert_risk_term_observation(
                role_id=task["role_id"],
                task_id=task["id"],
                term=term,
                risk_level="边缘",
                status="待验证",
                sample_text=cleaned[:180],
            )
    replacement_scope = _risk_replacement_scope(original, cleaned, replacements)
    risk_level = "已清理超高风险" if replacements else ("可发但需观察" if edge_terms or source_carried_terms else "安全")
    output = {
        "cleaned_body": cleaned,
        "high_risk_replacements": replacements,
        "replacements": replacements,
        "unchanged_source_risk_terms": source_carried_terms,
        "edge_risk_watchlist": edge_terms,
        "risk_replacement_scope": replacement_scope,
        "overall_risk": risk_level,
        "status": "needs_confirmation",
    }
    markdown = "\n".join(
        [
            "# Risk Cleanup",
            "",
            "## Cleaned Copy",
            cleaned,
            "",
            "## High-risk replacements",
            *(f"- {item['term']} -> {item['replacement']}" for item in replacements),
            "",
            "## Unchanged source-carried risk terms",
            *(f"- {item['term']}: {item['status']}" for item in source_carried_terms),
            "",
            "## Edge-risk watchlist",
            *(f"- {item['term']}: {item['status']}" for item in edge_terms),
        ]
    )
    return output, markdown


def _run_publish_format(store: Store, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    risk = _latest_output(store, task["id"], "risk_cleanup")
    body = str(risk.get("cleaned_body") or _latest_draft(store, task["id"], "rewrite_draft").get("body") or "")
    package = _build_publish_package(task, body)
    body_char_count = _script_char_count(body)
    package["body_char_count"] = body_char_count
    content_id = store.create_content_package(
        title=package["video_title_18"],
        body=body,
        media_paths=[],
        hashtags=[str(task["topic"])],
        metadata={"source": "creation_task", "creation_task_id": task["id"], "role_id": task["role_id"]},
    )
    store.update_creation_task(task["id"], content_package_id=content_id)
    for selection in store.list_creation_material_selections(task["id"], selection_status="selected"):
        store.insert_material_creation(
            material_id=selection["material_id"],
            role_id=task["role_id"],
            content_package_id=content_id,
            task_id=None,
            platform=task["platform"],
            rewrite_angle=task["topic"],
            status="draft",
            metadata={"source": "creation_task", "creation_task_id": task["id"], "selection_reason": selection["reason"]},
        )
    delivery_id = store.insert_creation_delivery_package(
        task_id=task["id"],
        platform=task["platform"],
        package=package,
        content_package_id=content_id,
        status="draft",
    )
    output = {
        "content_package_id": content_id,
        "delivery_package_id": delivery_id,
        "publish_package": package,
        "body_char_count": body_char_count,
        "status": "needs_confirmation",
    }
    markdown = _format_publish_package(package)
    return output, markdown


def _run_delivery(store: Store, task: dict[str, Any]) -> tuple[dict[str, Any], str]:
    markdown = export_creation_task_markdown(store, task["id"])
    return {"delivery_markdown": markdown, "status": "needs_confirmation"}, markdown


def _persist_stage_artifacts(
    store: Store,
    task: dict[str, Any],
    stage_key: str,
    stage_run_id: str,
    output: dict[str, Any],
) -> None:
    if stage_key == "rewrite_draft":
        draft = output.get("draft") or {}
        store.insert_creation_draft(
            task_id=task["id"],
            stage_run_id=stage_run_id,
            draft_type="rewrite_draft",
            title=str(draft.get("title") or task["topic"]),
            body=str(draft.get("draft_text") or draft.get("body") or ""),
            metadata=draft,
        )
    elif stage_key == "hook_enhancement":
        store.insert_creation_draft(
            task_id=task["id"],
            stage_run_id=stage_run_id,
            draft_type="hook_enhancement",
            title=str(output.get("selected_hook") or task["topic"]),
            body=str(output.get("body") or ""),
            metadata={
                "hooks": output.get("hooks") or [],
                "source_opening_text": output.get("source_opening_text") or "",
                "hook_diff_type": output.get("hook_diff_type") or "",
                "mechanism_preserved": output.get("mechanism_preserved"),
                "dedup_change_summary": output.get("dedup_change_summary") or "",
                "validation": output.get("validation") or {},
            },
        )
    elif stage_key == "risk_cleanup":
        store.insert_creation_draft(
            task_id=task["id"],
            stage_run_id=stage_run_id,
            draft_type="risk_cleanup",
            title=str(task["topic"]),
            body=str(output.get("cleaned_body") or ""),
            metadata={
                "high_risk_replacements": output.get("high_risk_replacements") or [],
                "unchanged_source_risk_terms": output.get("unchanged_source_risk_terms") or [],
                "edge_risk_watchlist": output.get("edge_risk_watchlist") or [],
                "risk_replacement_scope": output.get("risk_replacement_scope") or {},
                "overall_risk": output.get("overall_risk"),
            },
        )


def _assert_previous_stage_confirmed(store: Store, task_id: str, stage_key: str) -> None:
    index = CREATION_STAGES.index(stage_key)
    if index == 0:
        return
    previous = store.latest_creation_stage_run(task_id, CREATION_STAGES[index - 1])
    if not previous or previous.get("status") != "confirmed":
        raise ValueError(f"confirm stage {CREATION_STAGES[index - 1]} before running {stage_key}")


def _confirmed_role(store: Store, role_id: str) -> dict[str, Any]:
    role = store.get_ip_role(role_id)
    if not role:
        raise KeyError(f"role not found: {role_id}")
    if role.get("confirmation_status") != "confirmed" or bool(role.get("needs_reconfirm")):
        raise ValueError(f"role {role_id} is {role.get('confirmation_status')}; confirm the IP role before creation")
    return role


def _task(store: Store, task_id: str) -> dict[str, Any]:
    task = store.get_creation_task(task_id)
    if not task:
        raise KeyError(f"creation task not found: {task_id}")
    return task


def _selected_materials(store: Store, task_id: str) -> list[dict[str, Any]]:
    materials = []
    for selection in store.list_creation_material_selections(task_id, selection_status="selected"):
        material = store.get_collected_material(selection["material_id"])
        if material:
            materials.append(material)
    return materials


def _material_packet(
    material: dict[str, Any],
    *,
    include_transcript: bool,
    source_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = {
        "id": material["id"],
        "clean_title": material.get("clean_title") or material.get("title"),
        "summary_text": material.get("summary_text"),
        "hook_text": material.get("hook_text"),
        "core_claim": material.get("core_claim"),
        "content_type": material.get("content_type"),
        "oral_script_pattern": material.get("oral_script_pattern"),
        "key_points": material.get("key_points") or [],
        "rewrite_angles": material.get("rewrite_angles") or [],
        "risk_notes": material.get("risk_notes") or [],
        "material_understanding": material.get("material_understanding") or {},
        "source_analysis": source_analysis or {},
    }
    if include_transcript:
        packet["transcript_text"] = material.get("transcript_text")
    return packet


def _rewrite_requirements(task: dict[str, Any], role: dict[str, Any]) -> dict[str, Any]:
    context = dict(task.get("context") or {})
    requirements = dict(context.get("rewrite_requirements") or {})
    expression_constraints = role.get("expression_constraints") or {}
    target_range = (
        requirements.get("target_length_range")
        or expression_constraints.get("target_length_range")
        or list(DEFAULT_TARGET_LENGTH_RANGE)
    )
    if not isinstance(target_range, list) or len(target_range) != 2:
        target_range = list(DEFAULT_TARGET_LENGTH_RANGE)
    return {
        "methodology_version": context.get("creation_methodology_version") or CREATION_METHODOLOGY_VERSION,
        "target_length_range": [int(target_range[0]), int(target_range[1])],
        "must_preserve_source_hook": bool(requirements.get("must_preserve_source_hook", True)),
        "preserve_source_opening_on_first_draft": bool(requirements.get("preserve_source_opening_on_first_draft", True)),
        "target_length_strategy": requirements.get("target_length_strategy") or "upper_bound_for_long_source",
        "source_value_policy": requirements.get("source_value_policy") or "identify_then_preserve_translate_or_discard",
        "cta_policy": requirements.get("cta_policy") or "soft_when_task_goal_requires_conversion",
        "asr_corrections": {
            **GLOBAL_ASR_CORRECTIONS,
            **dict(requirements.get("asr_corrections") or {}),
            **dict(expression_constraints.get("asr_corrections") or {}),
        },
    }


def _analyze_source_material(material: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    transcript = str(material.get("transcript_text") or "")
    source_opening, opening_corrections = _source_opening_text(transcript, GLOBAL_ASR_CORRECTIONS)
    hook = _first_sentence(transcript) or str(material.get("hook_text") or "").strip()
    corrected_hook, hook_corrections = _apply_asr_corrections(hook, GLOBAL_ASR_CORRECTIONS)
    corrected_text, text_corrections = _apply_asr_corrections(
        " ".join(
            str(part or "")
            for part in [
                material.get("clean_title"),
                material.get("title"),
                material.get("summary_text"),
                material.get("core_claim"),
                transcript[:500],
            ]
        ),
        GLOBAL_ASR_CORRECTIONS,
    )
    authority_terms = [term for term in AUTHORITY_FRAME_TERMS if term in corrected_text]
    concrete_terms = [term for term in CONCRETE_PAIN_TERMS if term in corrected_text or term in str(task.get("topic") or "")]
    must_keep = _dedupe([source_opening, corrected_hook, *authority_terms[:2], *(material.get("key_points") or [])[:3]])
    deferred_risk_terms = _classify_risk_terms(corrected_text, source_text=corrected_text)
    hook_mechanism = _source_hook_mechanism(corrected_hook)
    viral_reasoning = _dedupe(
        [
            "强开头钩子" if corrected_hook else "",
            "身份势能" if authority_terms else "",
            "具体痛点" if concrete_terms else "",
            "高互动素材" if _engagement_signal(material) else "",
        ]
    )
    return {
        "source_text": transcript,
        "source_hook_text": corrected_hook,
        "source_opening_text": source_opening,
        "source_hook_mechanism": hook_mechanism,
        "source_char_count": _script_char_count(transcript),
        "viral_reasoning": viral_reasoning,
        "topic_fit": {
            "topic": task.get("topic") or "",
            "matched_terms": concrete_terms,
            "fit_signal": "topic_or_role_term_matched" if concrete_terms else "weak_explicit_match",
        },
        "duplicate_signal": "selection_stage_only_not_rewritten",
        "risk_inventory": deferred_risk_terms,
        "authority_frame": authority_terms[0] if authority_terms else "",
        "authority_terms": authority_terms,
        "concrete_pain_terms": concrete_terms,
        "must_keep_elements": must_keep,
        "discard_elements": [],
        "deferred_risk_terms": deferred_risk_terms,
        "asr_corrections": _dedupe_dicts([*opening_corrections, *hook_corrections, *text_corrections]),
    }


def _source_hook_mechanism(hook: str) -> str:
    text = str(hook or "")
    if any(term in text for term in ["只有", "刷到", "限流"]):
        return "scarcity_or_fate_stop"
    if any(term in text for term in ["两点", "三点", "特征", "征兆"]):
        return "diagnostic_self_check"
    if any(term in text for term in ["告诉你", "卦师", "命理师", "老师"]):
        return "practitioner_authority"
    if any(term in text for term in ["不是", "其实", "真正"]):
        return "misread_reversal"
    return "direct_topic_entry" if text else ""


def _body_logic_plan(material: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    analysis = material.get("source_analysis") or {}
    key_points = [str(item) for item in material.get("key_points") or []]
    return {
        "opening_contract": analysis.get("source_opening_text") or material.get("hook_text") or "",
        "main_claim": material.get("core_claim") or material.get("summary_text") or task.get("topic") or "",
        "point_count_target": min(max(len(key_points), 2), 3) if key_points else 3,
        "point_source": key_points[:3],
        "logic_policy": "body must fulfill the opening promise before adding explanation or CTA",
    }


def _cta_fit_decision(task: dict[str, Any], persona: dict[str, Any]) -> dict[str, Any]:
    cta = _soft_conversion_cta(task, persona)
    topic_text = " ".join(str(part or "") for part in [task.get("topic"), task.get("goal"), persona.get("positioning")])
    body_type = "metaphysics_diagnosis" if any(term in topic_text for term in ["财运", "事业", "命运", "磁场", "命理", "咨询"]) else "knowledge_oral_script"
    return {
        "body_type": body_type,
        "primary_cta": "comment" if cta else "none",
        "cta_text": cta,
        "reason": "consultation-style diagnosis can use public comment lead capture" if cta else "no forced CTA unless the body earns it",
    }


def _explicit_selected_material_ids(task: dict[str, Any]) -> list[str]:
    context = task.get("context") or {}
    values: list[Any] = []
    if context.get("selected_material_id"):
        values.append(context["selected_material_id"])
    values.extend(context.get("selected_material_ids") or [])
    return _dedupe([str(value) for value in values])


def _select_explicit_creation_materials(
    store: Store,
    task: dict[str, Any],
    *,
    role_id: str,
    material_ids: list[str],
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for material_id in material_ids[: int(task.get("target_count") or 1)]:
        material = store.get_collected_material(material_id)
        if not material:
            skipped.append({"material_id": material_id, "reason": "not_found"})
            continue
        if material.get("status") != "collected":
            skipped.append({"material_id": material_id, "reason": f"status_{material.get('status')}"})
            continue
        if material.get("eligibility_status") != "accepted":
            skipped.append({"material_id": material_id, "reason": "not_eligible"})
            continue
        score = 1.0
        reason = "explicit_selected_material"
        store.upsert_creation_material_selection(
            task_id=task["id"],
            material_id=material["id"],
            role_id=role_id,
            selection_status="selected",
            score=score,
            reason=reason,
            metadata={
                "clean_title": material.get("clean_title") or material.get("title"),
                "content_type": material.get("content_type"),
                "summary_text": material.get("summary_text"),
                "selection_source": "task_context",
            },
        )
        selected.append({"material_id": material["id"], "score": score, "reason": reason})
    return {"selected": selected, "skipped_count": len(skipped), "skipped": skipped}


def _compose_rewrite_body(
    task: dict[str, Any],
    persona: dict[str, Any],
    material: dict[str, Any],
    brief: dict[str, Any],
    source_analysis: dict[str, Any],
    requirements: dict[str, Any],
) -> str:
    if requirements.get("preserve_source_opening_on_first_draft") and source_analysis.get("source_opening_text"):
        hook = str(source_analysis["source_opening_text"]).strip()
    else:
        hook = str(source_analysis.get("source_hook_text") or material.get("hook_text") or material.get("clean_title") or f"{task['topic']}这件事，很多人都想错了。").strip()
    hook = _ensure_sentence(hook)
    target_ip = persona.get("target_ip") or "这个账号"
    topic = str(task.get("topic") or "")
    authority = _authority_frame_for_draft(task, persona, source_analysis)
    pain = _concrete_pain_phrase(task, persona, source_analysis)
    main_claim = str(brief.get("main_claim") or material.get("core_claim") or material.get("summary_text") or f"{topic}要先看清自己的状态").strip()
    posture = persona.get("speaking_posture") or "像老师当面提醒"
    cta = _soft_conversion_cta(task, persona)
    if cta:
        claim_sentence = _oral_claim_sentence(task, persona, main_claim)
        body = (
            f"{hook}\n\n"
            f"{pain}，先别急着求方法。接下来这三个关键点你回头可以逐条对照，所以这条先点赞收藏。"
            f"你先看三个方面："
            f"第一，看你住的地方乱不乱，玄关堆杂物、灯不亮、旧东西舍不得扔，人的心气会被拖低；"
            f"第二，看你身边有没有总是消耗、抱怨、赌气、诉苦的人，圈子一乱，贵人和客户就很难靠近；"
            f"第三，看你的精气神和认知，熬夜、焦虑、总问凭什么、看别人好就酸，机会来了也接不住。"
            f"{claim_sentence}"
            f"说白了，环境、人和念头一乱，机会就算到了也容易滑过去。"
            f"你先把环境、关系和念头理顺，财运和事业才有地方落下来。"
            f"{cta}"
        )
    else:
        body = (
            f"{hook}\n\n"
            f"{target_ip}要把{topic or '这件事'}讲到具体处境里。"
            f"{pain}，真正要看的不是一时情绪，而是你怎么判断、怎么选择、怎么把眼前的事接住。"
            f"{main_claim}。"
            f"这类内容最怕讲成空话，所以要留下一个能马上对照的标准：当你开始少被消耗、少乱答应、能把机会稳稳接住，变化才算真的发生。"
        )
    return _fit_script_length(body, requirements, task, persona, material)


def _oral_claim_sentence(task: dict[str, Any], persona: dict[str, Any], main_claim: str) -> str:
    if _persona_accepts_metaphysics(persona, task):
        return "磁场不是玄乎，它就藏在你住的环境、来往的人、每天反复起的念头里。"
    claim = str(main_claim or "").strip()
    return _ensure_sentence(claim) if claim else ""


def _validate_rewrite_draft(
    body: str,
    source_analysis: dict[str, Any],
    requirements: dict[str, Any],
) -> dict[str, Any]:
    char_count = _script_char_count(body)
    min_len, max_len = requirements["target_length_range"]
    hook = str(source_analysis.get("source_hook_text") or "")
    opening = str(source_analysis.get("source_opening_text") or "")
    opening_preservation = _opening_preservation_status(body, opening, requirements)
    hook_preserved = opening_preservation["passed"] if opening else (not hook or _normalized_for_compare(body).startswith(_normalized_for_compare(hook)[:18]))
    concrete_pain = any(term in body for term in CONCRETE_PAIN_TERMS)
    kept_elements = _kept_source_elements(body, source_analysis)
    abstract_hits = [term for term in ABSTRACT_MORALIZING_TERMS if term in body]
    too_abstract = len(abstract_hits) >= 6 and not concrete_pain
    deferred_risk_terms = _classify_risk_terms(body, source_text=opening)
    risk_notes: list[str] = []
    bridge_body = _bridge_body_alignment(body)
    parallel_structure = _parallel_structure_alignment(body)
    checks = {
        "length": {"passed": min_len <= char_count <= max_len, "char_count": char_count, "target_range": [min_len, max_len]},
        "opening_preservation": opening_preservation,
        "hook_preservation": {"passed": (hook_preserved or not requirements.get("must_preserve_source_hook")), "source_hook_text": hook},
        "concrete_pain": {"passed": concrete_pain, "matched_terms": [term for term in CONCRETE_PAIN_TERMS if term in body]},
        "source_elements": {"passed": bool(kept_elements), "kept": kept_elements},
        "abstract_moralizing": {"passed": not too_abstract, "matched_terms": abstract_hits},
        "no_internal_process_terms": {"passed": not any(term in body for term in INTERNAL_PROCESS_TERMS), "matched_terms": [term for term in INTERNAL_PROCESS_TERMS if term in body]},
        "internal_logic_alignment": {
            "passed": bridge_body["passed"] and parallel_structure["passed"],
            "bridge_body_alignment": bridge_body,
            "parallel_structure_alignment": parallel_structure,
        },
        "bridge_body_alignment": bridge_body,
        "parallel_structure_alignment": parallel_structure,
    }
    passed = all(item["passed"] for item in checks.values() if isinstance(item, dict) and "passed" in item)
    return {"passed": passed, "checks": checks, "risk_notes": risk_notes, "deferred_risk_terms": deferred_risk_terms}


def _rewrite_stage_boundary_passed(validation: dict[str, Any]) -> bool:
    checks = validation.get("checks") or {}
    required = ["opening_preservation", "hook_preservation", "no_internal_process_terms"]
    return all(bool((checks.get(key) or {}).get("passed")) for key in required)


def _opening_preservation_status(body: str, source_opening: str, requirements: dict[str, Any]) -> dict[str, Any]:
    source = str(source_opening or "").strip()
    if not source:
        return {
            "passed": True,
            "mode": "no_source_opening",
            "source_opening_text": "",
            "body_opening_preview": str(body or "")[:80],
        }
    normalized_source = _normalized_for_compare(source)
    normalized_body = _normalized_for_compare(body)
    probe_len = min(len(normalized_source), 36)
    if probe_len < 12:
        probe_len = len(normalized_source)
    protected_prefix = normalized_source[:probe_len]
    exact = str(body or "").strip().startswith(source)
    near_literal = bool(protected_prefix) and normalized_body.startswith(protected_prefix)
    requires_preservation = bool(requirements.get("preserve_source_opening_on_first_draft", True))
    mode = "exact_source_opening" if exact else ("near_literal_source_opening" if near_literal else "changed_or_missing_source_opening")
    return {
        "passed": near_literal or not requires_preservation,
        "mode": mode,
        "source_opening_text": source,
        "protected_prefix": protected_prefix,
        "body_opening_preview": str(body or "")[:80],
    }


def _minimal_hook_variants(hook: str) -> list[str]:
    original = _ensure_sentence(str(hook or "").strip())
    if not original:
        return []
    variants = [original]
    minimal = original
    for old, new in [
        ("以下的", "下面这些"),
        ("以下这", "下面这"),
        ("这条视频", "这条内容"),
        ("一般情况下", "通常"),
        ("就要具备", "只要具备"),
    ]:
        minimal = minimal.replace(old, new)
    if minimal != original:
        variants.append(minimal)
    return variants


def _validate_hook_enhancement(
    *,
    source_opening: str,
    selected_hook: str,
    original_body: str,
    enhanced_body: str,
) -> dict[str, Any]:
    source_norm = _normalized_for_compare(source_opening)
    selected_norm = _normalized_for_compare(selected_hook)
    if not source_norm:
        diff_type = "no_source_opening"
    elif selected_norm == source_norm:
        diff_type = "unchanged"
    else:
        probe = source_norm[: min(len(source_norm), 24)]
        length_delta = abs(len(selected_norm) - len(source_norm))
        diff_type = "minimal_dedup" if probe and selected_norm.startswith(probe[:12]) and length_delta <= 12 else "replaced"
    source_tokens = _hook_mechanism_tokens(source_opening)
    retained_tokens = [term for term in source_tokens if term in selected_hook]
    mechanism_preserved = diff_type in {"unchanged", "minimal_dedup", "no_source_opening"} and (
        not source_tokens or len(retained_tokens) >= max(1, int(len(source_tokens) * 0.6))
    )
    risk_denial_reframe = any(term in selected_hook for term in ["不是玄乎", "不是绝对", "不是看漂不漂亮", "不是迷信"])
    if risk_denial_reframe and not any(term in str(source_opening or "") for term in ["不是玄乎", "不是绝对", "不是看漂不漂亮", "不是迷信"]):
        mechanism_preserved = False
        diff_type = "replaced"
    return {
        "passed": diff_type != "replaced" and mechanism_preserved and enhanced_body.startswith(selected_hook),
        "diff_type": diff_type,
        "mechanism_preserved": mechanism_preserved,
        "source_mechanism_tokens": source_tokens,
        "retained_mechanism_tokens": retained_tokens,
        "change_summary": "开头未改动" if diff_type == "unchanged" else ("只做去重/顺口化微调" if diff_type == "minimal_dedup" else "开头机制被替换"),
    }


def _hook_mechanism_tokens(text: str) -> list[str]:
    candidates = [
        "只有",
        "刷到",
        "限流",
        "两点",
        "三点",
        "两个",
        "三个",
        "女人",
        "女性",
        "财运",
        "财气",
        "卦师",
        "命理师",
        "告诉你",
        "特征",
        "征兆",
        "一定要",
    ]
    return [term for term in candidates if term in str(text or "")]


def _classify_risk_terms(text: str, *, source_text: str = "") -> list[dict[str, Any]]:
    content = str(text or "")
    source = str(source_text or "")
    items: list[dict[str, Any]] = []
    ultra_terms_in_content = [term for term in sorted(ULTRA_HIGH_RISK_REPLACEMENTS, key=len, reverse=True) if term in content]
    for term in ultra_terms_in_content:
        items.append(
            {
                "term": term,
                "risk_level": "超高风险",
                "origin": "source" if term in source else "generated",
                "action": "defer_to_risk_cleanup",
            }
        )
    observed_terms = _dedupe([*SOURCE_CARRIED_RISK_TERMS, *EDGE_RISK_TERMS])
    for term in sorted(observed_terms, key=len, reverse=True):
        if term not in content:
            continue
        if any(term != ultra and term in ultra for ultra in ultra_terms_in_content):
            continue
        source_carried = term in source
        items.append(
            {
                "term": term,
                "risk_level": "源文案携带高风险" if source_carried and term in SOURCE_CARRIED_RISK_TERMS else "边缘",
                "origin": "source" if source_carried else "generated",
                "action": "observe_without_rewrite",
            }
        )
    return _dedupe_risk_terms(items)


def _dedupe_risk_terms(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        term = str(item.get("term") or "")
        level = str(item.get("risk_level") or "")
        if not term:
            continue
        key = (term, level)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _risk_replacement_scope(original: str, cleaned: str, replacements: list[dict[str, Any]]) -> dict[str, Any]:
    expected = str(original or "")
    for item in replacements:
        expected = expected.replace(str(item.get("term") or ""), str(item.get("replacement") or ""))
    passed = expected == str(cleaned or "")
    return {
        "passed": passed,
        "change_type": "none" if not replacements else ("localized_term_replacement" if passed else "unexpected_rewrite"),
        "changed_terms": [item.get("term") for item in replacements],
        "changed_term_count": len(replacements),
    }


def _task_source_text(store: Store, task_id: str) -> str:
    parts: list[str] = []
    for material in _selected_materials(store, task_id):
        parts.extend(
            str(part or "")
            for part in [
                material.get("clean_title"),
                material.get("title"),
                material.get("summary_text"),
                material.get("hook_text"),
                material.get("core_claim"),
                material.get("transcript_text"),
            ]
        )
    return " ".join(parts)


def _bridge_body_alignment(body: str) -> dict[str, Any]:
    has_numbered_body = all(marker in body for marker in PARALLEL_ENUM_MARKERS)
    if not has_numbered_body:
        return {"passed": True, "reason": "no_three_point_body"}
    bridge = body.split("第一", 1)[0]
    matched_terms = [term for term in BRIDGE_STRUCTURE_TERMS if term in bridge]
    return {
        "passed": bool(matched_terms),
        "matched_terms": matched_terms,
        "bridge_preview": bridge[-80:].strip(),
    }


def _parallel_structure_alignment(body: str) -> dict[str, Any]:
    segments = _enumerated_body_segments(body)
    if len(segments) < 3:
        return {"passed": True, "reason": "no_three_point_body"}
    lead_terms = [_parallel_lead_term(segment) for segment in segments[:3]]
    passed = all(lead_terms) and len(set(lead_terms)) == 1
    return {"passed": passed, "lead_terms": lead_terms, "segments": segments[:3]}


def _enumerated_body_segments(body: str) -> list[str]:
    if not all(marker in body for marker in PARALLEL_ENUM_MARKERS):
        return []
    try:
        first = body.split("第一", 1)[1].split("第二", 1)[0]
        second = body.split("第二", 1)[1].split("第三", 1)[0]
        third = body.split("第三", 1)[1]
    except IndexError:
        return []
    third = re.split(r"[。！？]", third, maxsplit=1)[0]
    return [_clean_parallel_segment(segment) for segment in [first, second, third]]


def _clean_parallel_segment(segment: str) -> str:
    return re.sub(r"^[，、:：；;\s]+", "", segment or "").strip()


def _parallel_lead_term(segment: str) -> str:
    cleaned = _clean_parallel_segment(segment)
    for term in PARALLEL_LEAD_TERMS:
        if cleaned.startswith(term):
            return term
    return cleaned[:1]


def _authority_frame_for_draft(task: dict[str, Any], persona: dict[str, Any], source_analysis: dict[str, Any]) -> str:
    source_authority = str(source_analysis.get("authority_frame") or "")
    if source_authority and _persona_accepts_metaphysics(persona, task):
        return f"一个{source_authority}"
    baseline = str(persona.get("role_baseline") or "")
    if baseline:
        return baseline
    return "一个长期观察这个问题的人"


def _persona_accepts_metaphysics(persona: dict[str, Any], task: dict[str, Any]) -> bool:
    text = " ".join(
        str(part or "")
        for part in [
            persona.get("positioning"),
            persona.get("role_baseline"),
            persona.get("speaking_posture"),
            task.get("goal"),
            task.get("topic"),
            " ".join(str(item) for item in persona.get("fit_themes") or []),
            " ".join(str(item) for item in persona.get("search_keywords") or []),
        ]
    )
    return any(term in text for term in ["玄学", "命理", "卦", "磁场", "财运", "道家", "咨询"])


def _concrete_pain_phrase(task: dict[str, Any], persona: dict[str, Any], source_analysis: dict[str, Any]) -> str:
    terms = _dedupe(
        [
            *(source_analysis.get("concrete_pain_terms") or []),
            str(task.get("topic") or ""),
            *(persona.get("fit_themes") or [])[:2],
        ]
    )
    if any(term in terms for term in ["财运", "事业", "磁场", "贵人", "客户"]):
        return "财运、事业和身边磁场卡住的时候"
    if terms:
        return f"{terms[0]}这件事卡住的时候"
    return "一个人反复被同一个问题困住的时候"


def _soft_conversion_cta(task: dict[str, Any], persona: dict[str, Any]) -> str:
    text = " ".join(str(part or "") for part in [task.get("goal"), persona.get("positioning"), persona.get("role_baseline")])
    if not any(term in text for term in ["咨询", "获客", "客户", "私信", "预约"]):
        return ""
    return "如果你也有财运或事业问题，可以在评论区留下你的出厂日期。"


def _ip_adaptation_notes(task: dict[str, Any], persona: dict[str, Any], source_analysis: dict[str, Any]) -> list[str]:
    notes = ["使用目标 IP 的 persona packet 改写，不默认继承原作者定位"]
    if source_analysis.get("authority_frame"):
        notes.append("原文案存在身份势能，按目标 IP 适配后保留或转译")
    if _soft_conversion_cta(task, persona):
        notes.append("任务目标包含咨询/获客，结尾使用评论区承接，不默认引导私信")
    return notes


def _conversion_goal_alignment(task: dict[str, Any], persona: dict[str, Any], body: str) -> dict[str, Any]:
    cta = _soft_conversion_cta(task, persona)
    return {
        "requires_conversion": bool(cta),
        "soft_cta_present": bool(cta and cta in body),
        "cta_text": cta,
        "cta_channel": "comment" if cta else "",
        "private_message_cta_present": "私信" in body,
        "save_prompt_present": "收藏" in body,
    }


def _kept_source_elements(body: str, source_analysis: dict[str, Any]) -> list[str]:
    normalized_body = _normalized_for_compare(body)
    kept: list[str] = []
    for element in source_analysis.get("must_keep_elements") or []:
        text = str(element or "").strip()
        if not text:
            continue
        normalized = _normalized_for_compare(text)
        if normalized and (normalized in normalized_body or normalized[:12] in normalized_body):
            kept.append(text)
    return _dedupe(kept)


def _fit_script_length(body: str, requirements: dict[str, Any], task: dict[str, Any], persona: dict[str, Any], material: dict[str, Any] | None = None) -> str:
    min_len, max_len = requirements["target_length_range"]
    desired_min = _desired_min_length(requirements, material, min_len, max_len)
    supplements = [
        "你先看清自己最近的选择有没有跑偏。",
        "越是想要结果，越要先把身边的人、事和机会分清楚。",
        "真正有用的提醒，一定能让你马上拿自己的生活来对照。",
    ]
    result = body.strip()
    for sentence in supplements:
        if _script_char_count(result) >= desired_min:
            break
        result += sentence
    if _script_char_count(result) > max_len:
        result = _trim_to_char_count(result, max_len)
    return result.strip()


def _desired_min_length(requirements: dict[str, Any], material: dict[str, Any] | None, min_len: int, max_len: int) -> int:
    strategy = str(requirements.get("target_length_strategy") or "")
    source_text = str((material or {}).get("transcript_text") or "")
    source_count = _script_char_count(source_text)
    source_analysis = (material or {}).get("source_analysis") or {}
    if not source_count:
        try:
            source_count = int(source_analysis.get("source_char_count") or 0)
        except (TypeError, ValueError):
            source_count = 0
    if strategy == "upper_bound_for_long_source" and source_count >= 900:
        return max(min_len, max_len - 20)
    return min_len


def _trim_to_char_count(body: str, max_len: int) -> str:
    sentences = re.split(r"(?<=[。！？])", body)
    kept = ""
    for sentence in sentences:
        candidate = (kept + sentence).strip()
        if candidate and _script_char_count(candidate) <= max_len:
            kept = candidate
    if kept:
        return kept
    compact = re.sub(r"\s+", "", body)
    return compact[: max(0, max_len - 1)] + "。"


def _script_char_count(body: str) -> int:
    return len(re.sub(r"\s+", "", body or ""))


def _first_sentence(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    match = re.split(r"[。！？!?]\s*", cleaned, maxsplit=1)
    return match[0].strip(" ，,。") if match else cleaned[:80]


def _source_opening_text(text: str, corrections: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return "", []
    sentences = re.findall(r"[^。！？!?]+[。！？!?]?", cleaned)
    opening = "".join(sentences[:2]).strip() if sentences else cleaned[:120]
    return _apply_asr_corrections(opening, corrections)


def _ensure_sentence(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    return stripped if stripped[-1] in "。！？!?" else stripped + "。"


def _apply_asr_corrections(text: str, corrections: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    corrected = str(text or "")
    applied: list[dict[str, str]] = []
    for wrong, right in corrections.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            applied.append({"from": wrong, "to": right})
    return corrected, applied


def _dedupe_dicts(values: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        key = (item.get("from") or "", item.get("to") or "")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalized_for_compare(text: str) -> str:
    return re.sub(r"[\s，。！？!?,.；;：:、“”\"'（）()《》]+", "", str(text or ""))


def _engagement_signal(material: dict[str, Any]) -> bool:
    metrics = material.get("public_metrics") or {}
    try:
        return int(metrics.get("likes") or 0) >= 10000
    except (TypeError, ValueError):
        return False


def _latest_output(store: Store, task_id: str, stage_key: str) -> dict[str, Any]:
    stage = store.latest_creation_stage_run(task_id, stage_key)
    return dict(stage.get("output") or {}) if stage else {}


def _latest_draft(store: Store, task_id: str, draft_type: str) -> dict[str, Any]:
    drafts = store.list_creation_drafts(task_id, draft_type=draft_type)
    return drafts[-1] if drafts else {}


def _material_search_text(material: dict[str, Any]) -> str:
    parts = [
        material.get("clean_title"),
        material.get("title"),
        material.get("summary_text"),
        material.get("hook_text"),
        material.get("core_claim"),
        material.get("content_type"),
        " ".join(str(item) for item in material.get("key_points") or []),
        " ".join(str(item) for item in material.get("rewrite_angles") or []),
    ]
    return " ".join(str(part or "") for part in parts)


def _selection_reason(material: dict[str, Any], *, topic_hit: int, role_hit_count: int, match_score: float) -> str:
    reasons = []
    if match_score:
        reasons.append(f"role_match={match_score:.2f}")
    if topic_hit:
        reasons.append("topic_hit")
    if role_hit_count:
        reasons.append(f"role_terms={role_hit_count}")
    if material.get("summary_text"):
        reasons.append("has_summary")
    return ", ".join(reasons) or "selected_by_material_quality"


def _role_slug(role: dict[str, Any]) -> str:
    for source in (role.get("style_anchors") or {}, role.get("source_evidence") or {}, role.get("agent_suggestions") or {}):
        slug_value = source.get("knowledge_slug") if isinstance(source, dict) else None
        if slug_value:
            slug = re.sub(r"\s+", "-", str(slug_value).strip().lower())
            slug = re.sub(r"[^\w\-]+", "", slug)
            if slug:
                return slug
    raw = str(role.get("name") or role.get("id") or "unknown-role").strip().lower()
    slug = re.sub(r"\s+", "-", raw)
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", slug)
    return slug or str(role.get("id") or "unknown-role")


def _short_title(topic: str) -> str:
    cleaned = re.sub(r"\s+", "", topic)
    return (cleaned + "要稳")[:4] if len(cleaned) < 4 else cleaned[:4]


def _build_publish_package(task: dict[str, Any], body: str) -> dict[str, Any]:
    final_copy = str(body or "").strip()
    return {
        "cover_title_4": _semantic_cover_title_4(task, final_copy),
        "video_title_18": _semantic_video_title_18(task, final_copy),
        "description_100": _semantic_description_100(task, final_copy),
        "pinned_comment": _semantic_pinned_comment(task, final_copy),
        "final_copy": final_copy,
    }


def _semantic_cover_title_4(task: dict[str, Any], body: str) -> str:
    text = _package_text(task, body)
    if "人之道" in text or "有余" in text:
        return "有余磁场"
    if "磁场" in text and any(term in text for term in ["三个方面", "三处", "环境", "精气神"]):
        return "磁场自查"
    if "财运" in text and any(term in text for term in ["卡", "不顺", "事业"]):
        return "财运自查"
    if "事业" in text:
        return "事业自查"
    return _four_char_title(str(task.get("topic") or "发布标题"))


def _semantic_video_title_18(task: dict[str, Any], body: str) -> str:
    text = _package_text(task, body)
    if "人之道" in text or "有余" in text:
        return _title_limit("财运卡住先看有余感", 18)
    if "磁场" in text and any(term in text for term in ["居住", "社交", "精气神", "认知", "三个方面"]):
        return _title_limit("财运事业先看三处磁场", 18)
    if "磁场" in text:
        return _title_limit("磁场乱先看这三处", 18)
    if "财运" in text and "事业" in text:
        return _title_limit("财运事业卡住先自查", 18)
    return _title_limit(f"{_short_title(str(task.get('topic') or '这件事'))}先自查", 18)


def _semantic_description_100(task: dict[str, Any], body: str) -> str:
    text = _package_text(task, body)
    if "人之道" in text or "有余" in text:
        desc = "借《道德经》里的有余提醒你：财运和事业卡住时，别急着诉苦，先把对外状态立起来。"
    elif "磁场" in text and any(term in text for term in ["居住", "社交", "精气神", "认知", "三个方面"]):
        desc = "财运事业不顺，先自查三处磁场：居住环境、身边关系、精气神和认知状态。"
    elif "磁场" in text:
        desc = "很多人不是没有机会，而是自己的磁场先乱了；这条帮你做一次现实自查。"
    else:
        desc = f"{task.get('topic') or '这件事'}别只问方法，先看自己当下的状态和选择。"
    return _description_limit(desc, 100)


def _semantic_pinned_comment(task: dict[str, Any], body: str) -> str:
    text = _package_text(task, body)
    if "人之道" in text or "有余" in text:
        return "你最近更像卡在匮乏感，还是有余感？"
    if "磁场" in text and any(term in text for term in ["居住", "社交", "精气神", "认知", "三个方面"]):
        return "你觉得自己更卡在环境、人际，还是精气神？"
    if "财运" in text or "事业" in text:
        return "你最近更卡在财运、事业，还是身边关系？"
    return "你觉得这条最适合对照哪一种状态？"


def _package_text(task: dict[str, Any], body: str) -> str:
    return f"{task.get('topic') or ''} {body or ''}"


def _four_char_title(value: str) -> str:
    cleaned = re.sub(r"[\s，,。！？!?:：；;、]+", "", value or "")
    if not cleaned:
        return "状态自查"
    if _script_char_count(cleaned) >= 4:
        return cleaned[:4]
    return (cleaned + "自查")[:4]


def _title_limit(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", "", value or "")
    return cleaned[:limit]


def _description_limit(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    if _script_char_count(cleaned) <= limit:
        return cleaned
    return _trim_to_char_count(cleaned, limit)


def _format_publish_package(package: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Publish Format",
            "",
            f"4字封面标题：{package['cover_title_4']}",
            "",
            f"18字视频标题：{package['video_title_18']}",
            "",
            f"视频描述：{package['description_100']}",
            "",
            f"置顶评论：{package['pinned_comment']}",
            "",
            f"正文字数：{package.get('body_char_count') or _script_char_count(package['final_copy'])}",
            "",
            "最终可复制文案：",
            package["final_copy"],
        ]
    )


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
