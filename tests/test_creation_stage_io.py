from __future__ import annotations

from pathlib import Path

import pytest

from mcn_ops.creation import confirm_creation_stage, create_creation_task, prepare_creation_stage, submit_creation_stage
from mcn_ops.creation.knowledge import validate_role_knowledge
from mcn_ops.store import Store


def _fixture(tmp_path: Path) -> tuple[Store, str, str, str]:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="经验型老师",
        positioning="帮助家长改善沟通的经验型内容IP",
        search_keywords=["沟通", "孩子"],
        fit_themes=["亲子沟通"],
        role_baseline="讲清具体方法的老师",
    )
    store.confirm_ip_role(role_id, change_reason="test")
    run_id = store.create_collection_run(
        task_id=None,
        role_id=role_id,
        topic="沟通",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mock",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "role_id": role_id,
            "source_link": "mock://communication",
            "title": "孩子为什么不愿意沟通",
            "platform_caption": "孩子为什么不愿意沟通",
            "transcript_text": "孩子不愿意沟通，不是没有话，而是担心一开口就被否定。先听完，再问他想被倾听还是一起想办法。",
            "source_platform": "mock",
            "public_metrics": {"likes": 20000},
            "material_eligibility": {
                "eligibility_status": "accepted",
                "knowledge_core_score": 0.9,
                "oral_script_fit_score": 0.9,
            },
        },
        material_understanding={
            "topic_summary": "孩子因担心被否定而停止沟通。",
            "hook": "孩子不愿意沟通，不是没有话。",
            "core_claim": "沟通前要先建立表达安全感。",
            "content_type": "方法解释",
            "key_points": ["先听完", "再确认需要"],
            "understanding_provider": "codex-agent",
            "understanding_model": "gpt-5.5",
        },
        raw={},
    )
    task_id = create_creation_task(
        store,
        role_id=role_id,
        topic="沟通",
        goal="生成一条口播",
        platform="douyin",
        target_count=1,
    )["task"]["id"]
    return store, role_id, material_id, task_id


def test_prepare_is_read_only_and_contains_transcript_contract(tmp_path: Path) -> None:
    store, _, material_id, task_id = _fixture(tmp_path)
    packet = prepare_creation_stage(
        store,
        task_id,
        stage_key="material_selection",
        knowledge_root=tmp_path / "knowledge",
    )
    assert store.list_creation_material_selections(task_id) == []
    assert packet["candidate_materials"][0]["id"] == material_id
    assert packet["candidate_materials"][0]["transcript_text"].startswith("孩子不愿意沟通")
    assert packet["output_contract"]["stage"] == "material_selection"
    assert packet["response_template"]["materials"][0]["professional_alignment"] == "aligned"


def test_hard_conflict_cannot_advance_as_formal_rewrite_base(tmp_path: Path) -> None:
    store, _, material_id, task_id = _fixture(tmp_path)
    result = submit_creation_stage(
        store,
        task_id,
        stage_key="material_selection",
        knowledge_root=tmp_path / "knowledge",
        result={
            "materials": [
                {
                    "material_id": material_id,
                    "material_class": "formal_rewrite_base",
                    "source_content_task": "给出沟通方法",
                    "source_hook_mechanism": "misread_reversal",
                    "speaker_position": "经验型老师",
                    "thickness_judgment": "足够",
                    "professional_alignment": "hard_conflict",
                    "conflicting_claim": "核心方法冲突",
                    "professional_disposition": "reject",
                    "salvage_boundary": "不能保留核心处方",
                    "selection_rationale": "冲突后无法保持原任务",
                    "selection_weaknesses": [],
                }
            ]
        },
    )
    assert result["output"]["status"] == "needs_retry"
    assert store.list_creation_material_selections(task_id, selection_status="selected") == []
    with pytest.raises(ValueError, match="failed contract validation"):
        confirm_creation_stage(store, task_id, stage_key="material_selection")


def test_agent_submission_runs_end_to_end_without_rules_fallback(tmp_path: Path) -> None:
    store, _, material_id, task_id = _fixture(tmp_path)
    knowledge_root = tmp_path / "knowledge"
    selection = submit_creation_stage(
        store,
        task_id,
        stage_key="material_selection",
        knowledge_root=knowledge_root,
        result={
            "materials": [
                {
                    "material_id": material_id,
                    "material_class": "formal_rewrite_base",
                    "source_content_task": "解释孩子不沟通并给出一个动作",
                    "source_hook_mechanism": "misread_reversal",
                    "speaker_position": "经验型老师",
                    "thickness_judgment": "可通过压缩完成",
                    "professional_alignment": "aligned",
                    "conflicting_claim": "",
                    "professional_disposition": "keep",
                    "salvage_boundary": "保留误读反转、原因和双选项动作",
                    "selection_rationale": "内容任务和证据完整",
                    "selection_weaknesses": [],
                }
            ]
        },
    )
    assert selection["stage_run"]["provider"] == "codex-agent"
    confirm_creation_stage(store, task_id, stage_key="material_selection")

    brief_result = {
        "adaptation_mode": "adaptation",
        "main_claim": "孩子不说话可能是在保护自己不被立即否定",
        "retention_mechanism": "misread_reversal",
        "must_keep_elements": ["不是没话", "被否定", "倾听或一起想办法"],
        "body_logic_plan": ["误读反转", "解释原因", "给出动作"],
        "professional_support_mode": "none",
        "support_card_ids": [],
        "support_function": "",
        "target_gap": "",
        "risk_policy": "defer_to_risk_cleanup",
    }
    submit_creation_stage(store, task_id, stage_key="creation_brief", result=brief_result, knowledge_root=knowledge_root)
    confirm_creation_stage(store, task_id, stage_key="creation_brief")

    body = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。家长急着给答案，以为是在帮助；孩子感受到的却是自己的想法不重要。下一次他开口时，先听完，再问一句：你现在想让我听你说，还是和你一起想办法？当表达不再立刻换来批评，沟通才有机会重新开始。"
    rewrite_result = {
        "draft_text": body,
        "source_content_task_preserved": True,
        "source_hook_mechanism_preserved": True,
        "source_evidence_path_preserved": True,
        "speaker_translation_valid": True,
        "new_claims": [],
        "source_mapping": [
            {"source_element": "不是没有话", "draft_location": "开头", "action": "preserved"},
            {"source_element": "倾听或一起想办法", "draft_location": "结尾", "action": "preserved"},
        ],
    }
    submit_creation_stage(store, task_id, stage_key="rewrite_draft", result=rewrite_result, knowledge_root=knowledge_root)
    confirm_creation_stage(store, task_id, stage_key="rewrite_draft")

    submit_creation_stage(
        store,
        task_id,
        stage_key="hook_enhancement",
        knowledge_root=knowledge_root,
        result={"selected_hook": "孩子不愿意沟通，不是因为他没话。", "body": body, "hook_diff_type": "unchanged", "mechanism_preserved": True},
    )
    confirm_creation_stage(store, task_id, stage_key="hook_enhancement")

    submit_creation_stage(
        store,
        task_id,
        stage_key="risk_cleanup",
        knowledge_root=knowledge_root,
        result={"cleaned_body": body, "claim_risks": [], "risk_replacement_scope": {"changed_spans": []}, "overall_risk": "safe", "source_content_task_preserved": True},
    )
    confirm_creation_stage(store, task_id, stage_key="risk_cleanup")

    publish = submit_creation_stage(
        store,
        task_id,
        stage_key="publish_format",
        knowledge_root=knowledge_root,
        result={"publish_package": {"cover_title_4": "重新沟通", "video_title_18": "孩子为什么不愿意沟通", "video_description": "先听完，再确认孩子需要什么。", "pinned_comment": "你最容易在哪一步打断孩子？", "final_copy": body}},
    )
    assert publish["output"]["content_package_id"]
    assert store.get_content_package(publish["output"]["content_package_id"])["body"] == body


def test_repository_knowledge_packs_validate_for_two_distinct_ips() -> None:
    root = Path(__file__).resolve().parents[1] / "knowledge"
    songli = validate_role_knowledge(root, {"id": "role_songli", "name": "宋立心理", "style_anchors": {"knowledge_slug": "songlixinli"}})
    sicheng = validate_role_knowledge(root, {"id": "role_sicheng", "name": "思丞说", "style_anchors": {"knowledge_slug": "sichengshuo"}})
    assert songli["valid"] is True
    assert songli["domain_pack"] == "psychology-education"
    assert songli["professional_card_count"] >= 5
    assert sicheng["valid"] is True
    assert sicheng["domain_pack"] == "traditional-culture-metaphysics"
    assert sicheng["professional_card_count"] >= 4
