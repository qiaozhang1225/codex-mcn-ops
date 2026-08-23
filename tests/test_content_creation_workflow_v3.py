from __future__ import annotations

from pathlib import Path
import re

import pytest

from mcn_ops.creation import confirm_creation_stage, create_creation_task, prepare_creation_stage, submit_creation_stage
from mcn_ops.store import Store


def _task(tmp_path: Path) -> tuple[Store, str, str, Path]:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="经验型老师",
        positioning="帮助家长改善沟通",
        search_keywords=["沟通"],
        fit_themes=["亲子沟通"],
        role_baseline="讲清具体方法",
    )
    store.confirm_ip_role(role_id, change_reason="test")
    run_id = store.create_collection_run(task_id=None, role_id=role_id, topic="沟通", target_count=1, like_floor=1, super_like_threshold=100, tool_provider="mock")
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "role_id": role_id,
            "source_link": "mock://v3",
            "title": "孩子为什么不愿意沟通",
            "platform_caption": "孩子为什么不愿意沟通",
            "transcript_text": "孩子不愿意沟通，不是没有话，而是担心一开口就被否定。先听完，再问他想被倾听还是一起想办法。",
            "source_platform": "mock",
            "public_metrics": {"likes": 20000},
            "material_eligibility": {"eligibility_status": "accepted", "knowledge_core_score": 0.9, "oral_script_fit_score": 0.9},
        },
        material_understanding={
            "topic_summary": "孩子因担心被否定而停止沟通。",
            "hook": "孩子不愿意沟通，不是没有话。",
            "core_claim": "沟通前先建立表达安全感。",
            "content_type": "方法解释",
            "key_points": ["先听完", "再确认需要"],
            "understanding_provider": "codex-agent",
            "understanding_model": "gpt-5.5",
        },
        raw={},
    )
    task_id = create_creation_task(store, role_id=role_id, topic="沟通", goal="生成一条口播", platform="douyin", target_count=1)["task"]["id"]
    root = tmp_path / "knowledge"
    _submit_selection_and_brief(store, task_id, material_id, root)
    return store, task_id, material_id, root


def _submit_selection_and_brief(store: Store, task_id: str, material_id: str, root: Path) -> None:
    submit_creation_stage(
        store,
        task_id,
        stage_key="material_selection",
        knowledge_root=root,
        result={
            "materials": [{
                "material_id": material_id,
                "material_class": "formal_rewrite_base",
                "source_content_task": "解释孩子不沟通并给出动作",
                "source_hook_mechanism": "misread_reversal",
                "speaker_position": "经验型老师",
                "thickness_judgment": "足够",
                "professional_alignment": "aligned",
                "conflicting_claim": "",
                "professional_disposition": "keep",
                "salvage_boundary": "保留反转、原因和动作",
                "selection_rationale": "传播机制与正文证据完整",
                "selection_weaknesses": [],
            }]
        },
    )
    confirm_creation_stage(store, task_id, stage_key="material_selection")
    submit_creation_stage(
        store,
        task_id,
        stage_key="creation_brief",
        knowledge_root=root,
        result={
            "adaptation_mode": "adaptation",
            "main_claim": "孩子不说话可能是在保护自己不被立即否定",
            "retention_mechanism": "misread_reversal",
            "must_keep_elements": ["不是没话", "被否定", "倾听或一起想办法"],
            "body_logic_plan": ["误读反转", "解释原因", "给出动作"],
            "professional_support_mode": "none",
            "support_card_ids": [],
            "support_function": "",
            "target_gap": "",
            "risk_policy": "defer_to_risk_review",
        },
    )
    confirm_creation_stage(store, task_id, stage_key="creation_brief")


def _script_result(body: str, opening: str, **overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "writing_mode": "initial_draft",
        "creation_mode": "adaptation",
        "base_script_run_id": "",
        "base_body_hash": "",
        "revision_request_stage_run_id": "",
        "body": body,
        "opening": opening,
        "body_contract": "解释孩子沉默的原因，并给出先听完再确认需要的动作。",
        "source_content_task_preserved": True,
        "source_hook_mechanism_preserved": True,
        "source_evidence_path_preserved": True,
        "speaker_translation_valid": True,
        "new_claims": [],
        "source_mapping": [],
        "protected_elements": ["误读反转", "双选项动作"],
        "changed_spans": [],
    }
    result.update(overrides)
    return result


def _quality_result(packet: dict[str, object], *, verdict: str = "pass", revision_request: dict[str, object] | None = None) -> dict[str, object]:
    script = packet["current_script"]
    assert isinstance(script, dict)
    opening = str(script["opening"])
    body = str(script["body"])
    sentences = [part.strip() for part in re.findall(r".+?(?:[。！？?!]+|$)", opening) if part.strip()]
    sentence_1 = sentences[0] if sentences else ""
    sentence_2 = sentences[1] if len(sentences) > 1 else ""
    return {
        "reviewed_script_run_id": script["stage_run_id"],
        "reviewed_body_hash": script["body_hash"],
        "verdict": verdict,
        "quality_dimensions": {"content_task": "pass", "oral_integrity": "pass"},
        "opening_scope_review": {
            "opening_sentence_1": sentence_1,
            "opening_sentence_2": sentence_2,
            "bridge_starts_at_sentence": 3,
            "sentence_1_hook_task": "推翻孩子没话的误读",
            "sentence_2_hook_task": "升级继续逼问带来的沟通损失",
            "sentence_1_strength": "strong" if sentence_1 else "absent",
            "sentence_2_strength": "strong" if sentence_2 else "absent",
            "high_stimulus_keywords": ["孩子", "沟通", "被否定", "把话藏得更深"] if sentence_2 else ["孩子", "沟通"],
        },
        "five_affliction_review": {
            "贪": {"status": "strong", "evidence_span": "把话藏得更深" if sentence_2 else opening[:8], "reason": "避免沟通进一步关闭", "body_payoff": True, "body_payoff_span": "先听完", "revision_direction": ""},
            "瞋": {"status": "absent", "evidence_span": "", "reason": "无需强加对立", "body_payoff": False, "body_payoff_span": "", "revision_direction": ""},
            "痴": {"status": "strong", "evidence_span": "不是因为他没话", "reason": "推翻没话的误读", "body_payoff": True, "body_payoff_span": "担心一开口就被否定", "revision_direction": ""},
            "慢": {"status": "absent", "evidence_span": "", "reason": "无需身份比较", "body_payoff": False, "body_payoff_span": "", "revision_direction": ""},
            "疑": {"status": "strong", "evidence_span": "而是担心一开口就被否定", "reason": "揭示隐藏原因", "body_payoff": True, "body_payoff_span": "担心一开口就被否定", "revision_direction": ""},
            "coherent_body_contract": True,
            "rationale_for_not_forcing_missing": "强加愤怒或身份优越会破坏亲子沟通主题。",
        },
        "source_mechanism_review": {"preserved": True},
        "body_contract_review": {"fulfilled": "先听完" in body},
        "protected_elements": ["误读反转", "双选项动作"],
        "failed_dimensions": [] if verdict == "pass" else ["opening_attention"],
        "revision_request": revision_request,
    }


def test_v3_linear_roles_publish_the_same_double_reviewed_script(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。家长再逼着问，只会让他把话藏得更深。"
    body = opening + "家长急着给答案，孩子感受到的却是自己的想法不重要。下一次他开口时，先听完，再问：你想让我听你说，还是和你一起想办法？"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(body, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")

    quality_packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)
    quality = submit_creation_stage(store, task_id, stage_key="quality_review", result=_quality_result(quality_packet), knowledge_root=root)
    assert quality["output"]["five_affliction_review"]["derived_active_driver_count"] == 3
    confirm_creation_stage(store, task_id, stage_key="quality_review")

    risk_packet = prepare_creation_stage(store, task_id, stage_key="risk_review", knowledge_root=root)
    script = risk_packet["current_script"]
    risk_result = {
        "reviewed_script_run_id": script["stage_run_id"], "reviewed_body_hash": script["body_hash"], "verdict": "pass",
        "issues": [], "overall_risk": "safe", "revision_request": None,
    }
    submit_creation_stage(store, task_id, stage_key="risk_review", result=risk_result, knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="risk_review")

    publish = submit_creation_stage(
        store,
        task_id,
        stage_key="publish_format",
        knowledge_root=root,
        result={"publish_package": {"cover_title_4": "重新沟通", "video_title_18": "孩子为什么不愿意沟通", "video_description": "先听完再确认需要。", "pinned_comment": "你会先听还是先讲？", "final_copy": body}},
    )
    assert publish["output"]["status"] == "needs_confirmation"
    assert store.get_content_package(publish["output"]["content_package_id"])["body"] == body


def test_quality_review_is_read_only_and_drives_bounded_writer_revision(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子不愿意沟通。"
    body = opening + "他可能担心一开口就被否定。家长先听完，再问他想被倾听还是一起想办法。"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(body, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)

    invalid = _quality_result(packet)
    invalid["body"] = "reviewer must not rewrite"
    with pytest.raises(ValueError, match="review output must not contain viewer copy fields"):
        submit_creation_stage(store, task_id, stage_key="quality_review", result=invalid, knowledge_root=root)

    request = {
        "revision_scope": "opening_only",
        "problems": ["开头没有呈现误读反转"],
        "revision_directions": ["在第一句加入不是没话而是怕被否定"],
        "protected_elements": ["正文动作"],
        "protected_spans": ["家长先听完"],
        "max_edit_boundary": "第一句",
    }
    revise = _quality_result(packet, verdict="revise", revision_request=request)
    for driver in ["痴", "疑"]:
        revise["five_affliction_review"][driver] = {"status": "absent", "evidence_span": "", "reason": "当前开头缺失", "body_payoff": False, "body_payoff_span": "", "revision_direction": "补足误读反转"}
    submit_creation_stage(store, task_id, stage_key="quality_review", result=revise, knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="quality_review")

    writer_packet = prepare_creation_stage(store, task_id, stage_key="script_writing", knowledge_root=root)
    revision = writer_packet["script_revision_context"]
    new_opening = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。"
    new_body = body.replace(opening, new_opening, 1)
    result = _script_result(
        new_body,
        new_opening,
        writing_mode="opening_only",
        base_script_run_id=revision["base_script_run_id"],
        base_body_hash=revision["base_body_hash"],
        revision_request_stage_run_id=revision["revision_request_stage_run_id"],
        changed_spans=[{"before": opening, "after": new_opening, "reason": "补足误读反转"}],
    )
    submitted = submit_creation_stage(store, task_id, stage_key="script_writing", result=result, knowledge_root=root)
    assert submitted["output"]["status"] == "needs_confirmation"
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    with pytest.raises(ValueError, match="quality_review must pass"):
        prepare_creation_stage(store, task_id, stage_key="risk_review", knowledge_root=root)


def test_quality_review_packet_checks_real_progression_and_spoken_directness(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子越来越沉默，家长先别急着替他回答。"
    body = opening + "先听完，再问他想被倾听还是一起想办法。"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(body, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")

    packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)
    playbook = packet["knowledge"]["quality_review_playbook"]

    assert "两个可分级变量" in playbook
    assert "可见的因果桥梁" in playbook
    assert "直接表达" in playbook
    assert "自然的时间变化或累积递进可以保留" in playbook
    assert "强行递进" in playbook


def test_risk_revision_invalidates_old_quality_pass(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。家长再逼着问，只会让他把话藏得更深。"
    risky = opening + "家长先听完，这样做一定能让孩子恢复正常，再问他想被倾听还是一起想办法。"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(risky, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    quality_packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)
    submit_creation_stage(store, task_id, stage_key="quality_review", result=_quality_result(quality_packet), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="quality_review")

    risk_packet = prepare_creation_stage(store, task_id, stage_key="risk_review", knowledge_root=root)
    script = risk_packet["current_script"]
    request = {
        "revision_scope": "risk_localized_revision",
        "problems": ["确定性恢复承诺"],
        "revision_directions": ["只降低结果确定性"],
        "protected_elements": ["具体倾听动作"],
        "protected_spans": ["家长先听完"],
        "max_edit_boundary": "标记风险片段及必要语法衔接",
    }
    submit_creation_stage(
        store,
        task_id,
        stage_key="risk_review",
        knowledge_root=root,
        result={
            "reviewed_script_run_id": script["stage_run_id"], "reviewed_body_hash": script["body_hash"], "verdict": "revise",
            "issues": [{"span": "一定能让孩子恢复正常", "risk_type": "guaranteed_outcome", "severity": "hard_fail", "reason": "确定性结果承诺", "repair_boundary": "只修改确定性", "protected_elements": ["倾听动作"], "revision_direction": "改为条件性表达"}],
            "overall_risk": "high", "revision_request": request,
        },
    )
    confirm_creation_stage(store, task_id, stage_key="risk_review")
    writer_packet = prepare_creation_stage(store, task_id, stage_key="script_writing", knowledge_root=root)
    revision = writer_packet["script_revision_context"]
    safe = risky.replace("一定能让孩子恢复正常", "才更有机会让沟通慢慢恢复")
    result = _script_result(
        safe,
        opening,
        writing_mode="risk_localized_revision",
        base_script_run_id=revision["base_script_run_id"],
        base_body_hash=revision["base_body_hash"],
        revision_request_stage_run_id=revision["revision_request_stage_run_id"],
        changed_spans=[{"before": "一定能让孩子恢复正常", "after": "才更有机会让沟通慢慢恢复", "reason": "移除结果保证"}],
    )
    submit_creation_stage(store, task_id, stage_key="script_writing", result=result, knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    with pytest.raises(ValueError, match="stale"):
        prepare_creation_stage(store, task_id, stage_key="risk_review", knowledge_root=root)


def test_original_work_starts_at_creation_brief_without_material_selection(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(name="原创作者", positioning="解释真实生活问题", search_keywords=["生活"], fit_themes=["生活判断"], role_baseline="具体可信")
    store.confirm_ip_role(role_id, change_reason="test")
    task_id = create_creation_task(
        store,
        role_id=role_id,
        topic="为什么越忙越焦虑",
        goal="生成原创口播",
        platform="douyin",
        target_count=1,
        creation_mode="original",
    )["task"]["id"]
    root = tmp_path / "knowledge"
    packet = prepare_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=root)
    assert packet["task_context"]["creation_mode"] == "original"
    result = dict(packet["response_template"])
    result.update(
        {
            "adaptation_mode": "original",
            "main_claim": "忙碌可能是在回避真正重要的决定",
            "retention_mechanism": "misread_reversal",
            "must_keep_elements": ["忙碌不等于推进"],
            "body_logic_plan": ["提出误区", "解释机制", "给出动作"],
            "professional_support_mode": "none",
            "support_card_ids": [],
            "support_function": "",
            "target_gap": "",
            "risk_policy": "defer_to_risk_review",
        }
    )
    submitted = submit_creation_stage(store, task_id, stage_key="creation_brief", result=result, knowledge_root=root)
    assert submitted["output"]["status"] == "needs_confirmation"


def test_artificial_five_affliction_driver_blocks_quality_pass(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。家长再逼着问，只会让他把话藏得更深。"
    body = opening + "家长急着给答案，孩子感受到的却是自己的想法不重要。下一次他开口时，先听完，再问他想被倾听还是一起想办法。"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(body, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)
    result = _quality_result(packet)
    result["five_affliction_review"]["瞋"] = {
        "status": "artificial",
        "evidence_span": "孩子不愿意沟通",
        "reason": "把普通问题硬写成对立",
        "body_payoff": False,
        "body_payoff_span": "",
        "revision_direction": "删除无根据的对立刺激",
    }
    submitted = submit_creation_stage(store, task_id, stage_key="quality_review", result=result, knowledge_root=root)
    assert submitted["output"]["status"] == "needs_retry"
    assert "quality pass cannot contain artificial five-affliction drivers" in submitted["output"]["validation"]["gate_failures"]


def test_quality_pass_rejects_third_sentence_evidence_weak_sentence_two_and_sparse_keywords(tmp_path: Path) -> None:
    store, task_id, _, root = _task(tmp_path)
    opening = "孩子不愿意沟通，不是因为他没话，而是担心一开口就被否定。家长再逼着问，只会让他把话藏得更深。真正原因，看三个信号。"
    body = opening + "家长先听完，再问他想被倾听还是一起想办法。"
    submit_creation_stage(store, task_id, stage_key="script_writing", result=_script_result(body, opening), knowledge_root=root)
    confirm_creation_stage(store, task_id, stage_key="script_writing")
    packet = prepare_creation_stage(store, task_id, stage_key="quality_review", knowledge_root=root)
    result = _quality_result(packet)
    result["opening_scope_review"]["sentence_2_strength"] = "weak"
    result["opening_scope_review"]["high_stimulus_keywords"] = ["孩子", "沟通", "被否定"]
    result["five_affliction_review"]["疑"] = {
        "status": "strong",
        "evidence_span": "看三个信号",
        "reason": "把第三句的信息缺口错算成开头命中",
        "body_payoff": True,
        "body_payoff_span": "先听完",
        "revision_direction": "把强信息缺口前置到前两句",
    }

    submitted = submit_creation_stage(store, task_id, stage_key="quality_review", result=result, knowledge_root=root)
    failures = submitted["output"]["validation"]["gate_failures"]

    assert submitted["output"]["status"] == "needs_retry"
    assert "five_affliction_review.疑.evidence_span must quote opening sentence one or two" in failures
    assert "quality pass requires both opening sentences to be strong" in failures
    assert "quality pass requires at least four distinct high-stimulus keywords in the first two sentences" in failures
