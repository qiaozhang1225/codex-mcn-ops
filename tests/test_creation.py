from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcn_ops.creation import (
    build_creation_context_packet,
    confirm_creation_stage,
    create_creation_task,
    generate_learning_update_proposals,
    apply_learning_update,
    run_creation_stage,
)
from mcn_ops.store import Store
from mcn_ops.creation.workflow import (
    DEFAULT_GLOBAL_REWRITE_PLAYBOOK,
    _build_publish_package,
    _validate_hook_enhancement,
)
from mcn_ops.creation.workflow import CREATION_STAGE_CONTRACT_VERSION, _validate_stage_contract


def _confirmed_role(store: Store) -> str:
    role_id = store.upsert_ip_role(
        name="思丞说",
        positioning="国学智慧口播",
        search_keywords=["财运", "修行"],
        fit_themes=["财运", "道家修行"],
        forbidden_expressions=["保证发财"],
        role_baseline="克制的国学知识分享者",
        speaking_posture="像过来人慢慢讲清楚",
        target_audience={"life_stage": "中年", "pain_points": ["内耗", "求稳"]},
    )
    store.confirm_ip_role(role_id, change_reason="test")
    return role_id


def _confirmed_metaphysics_role(store: Store) -> str:
    role_id = store.upsert_ip_role(
        name="思成说",
        positioning="玄学咨询获客型 IP，围绕财运、事业、玄学、磁场做口播",
        search_keywords=["财运", "事业", "玄学", "磁场", "命理"],
        fit_themes=["财运", "事业", "磁场", "命理咨询"],
        avoid_themes=["佛教色彩过强的修行表达", "保证发财"],
        forbidden_expressions=["保证发财", "必定改命"],
        role_baseline="接地气的玄学咨询老师",
        speaking_posture="像老师当面提醒，直接但不吓人",
        target_audience={"pain_points": ["财运卡住", "事业不顺", "想咨询命理磁场"]},
        expression_constraints={
            "target_length_range": [300, 500],
            "asr_corrections": {"挂失": "卦师"},
        },
    )
    store.confirm_ip_role(role_id, change_reason="test")
    return role_id


def _material(store: Store, *, title: str, topic: str, accepted: bool = True, hook: str = "") -> str:
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic=topic,
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mock",
    )
    return store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": f"mock://{title}",
            "title": title,
            "platform_caption": f"{title} #{topic}",
            "transcript_text": f"{hook or title}，这是一段知识型口播内容。",
            "source_platform": "mock",
            "public_metrics": {"likes": 10000},
            "material_eligibility": {
                "eligibility_status": "accepted" if accepted else "rejected",
                "content_form": "knowledge_oral_script" if accepted else "ritual_action",
                "knowledge_core_score": 0.9 if accepted else 0.0,
                "oral_script_fit_score": 0.8 if accepted else 0.0,
                "reasons": ["知识型口播"] if accepted else ["非知识型仪式动作"],
            },
        },
        material_understanding={
            "topic_summary": f"{topic}的知识型解释",
            "hook": hook or f"{title}真正该看的不是玄学动作。",
            "core_claim": f"{topic}要回到人的判断和节奏。",
            "content_type": "认知观点",
            "oral_script_pattern": "判断开头-解释原因-行动提醒",
            "key_points": ["看节奏", "看判断", "看能不能守住分寸"],
            "rewrite_angles": ["转成国学智慧口播"],
            "risk_notes": ["避免保证结果"],
            "understanding_provider": "codex-agent",
            "understanding_model": "gpt-5.5",
        },
        raw={},
    )


def _run_until_publish_format(store: Store, task_id: str, knowledge_root: Path) -> dict:
    for stage in [
        "material_selection",
        "creation_brief",
        "rewrite_draft",
        "hook_enhancement",
        "risk_cleanup",
    ]:
        result = run_creation_stage(store, task_id, stage_key=stage, knowledge_root=knowledge_root)
        assert result["stage_run"]["provider"] == "codex-agent"
        assert result["stage_run"]["model"] == "gpt-5.5"
        confirm_creation_stage(store, task_id, stage_key=stage)
    return run_creation_stage(store, task_id, stage_key="publish_format", knowledge_root=knowledge_root)


def test_creation_requires_confirmed_role(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(name="草稿角色", search_keywords=["财运"])

    with pytest.raises(ValueError, match="confirm the IP role"):
        create_creation_task(
            store,
            role_id=role_id,
            topic="财运",
            goal="生成口播",
            platform="douyin",
            target_count=1,
        )


def test_creation_material_selection_filters_accepted_and_reuse(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    accepted_id = _material(store, title="一个人发财前的征兆", topic="财运")
    rejected_id = _material(store, title="倒一杯自来水吐三口气", topic="财运", accepted=False)
    content_id = store.create_content_package(title="used", body="used", media_paths=[])
    store.insert_material_creation(
        material_id=accepted_id,
        role_id=role_id,
        content_package_id=content_id,
        task_id=None,
        platform="douyin",
    )

    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=2,
    )
    result = run_creation_stage(store, task["task"]["id"], stage_key="material_selection", knowledge_root=tmp_path / "knowledge")

    assert result["output"]["selected"] == []
    skipped = {item["material_id"]: item["reason"] for item in result["output"]["skipped"]}
    assert skipped[accepted_id] == "already_used_by_role"
    assert skipped[rejected_id] == "not_eligible"


def test_creation_stage_order_publish_and_feedback_learning(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    material_id = _material(
        store,
        title="一个人发财前的征兆",
        topic="财运",
        hook="一个人保证发财前，往往先稳住自己的节奏。",
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.92,
        decision="accepted",
        reasons=["适合思丞说"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成一条知识型五段式口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]

    with pytest.raises(ValueError, match="confirm stage material_selection"):
        run_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=tmp_path / "knowledge")

    publish_result = _run_until_publish_format(store, task_id, tmp_path / "knowledge")
    assert publish_result["output"]["content_package_id"].startswith("content_")
    assert publish_result["output"]["delivery_package_id"].startswith("cdeliv_")
    assert publish_result["output"]["publish_package"]["final_copy"]
    assert "保证发财" not in publish_result["output"]["publish_package"]["final_copy"]
    confirm_creation_stage(store, task_id, stage_key="publish_format")

    task_row = store.get_creation_task(task_id)
    assert task_row is not None
    assert task_row["status"] == "ready_to_publish"
    creations = store.list_material_creations(material_id=material_id, role_id=role_id)
    assert creations[0]["content_package_id"] == publish_result["output"]["content_package_id"]
    observations = store.list_risk_term_observations(role_id=role_id)
    assert {item["term"] for item in observations} >= {"保证发财", "财运"}

    feedback_id = store.insert_creation_feedback_event(
        content_package_id=publish_result["output"]["content_package_id"],
        task_id=task_id,
        role_id=role_id,
        platform="douyin",
        metrics={"likes": 1200},
        human_note="财运表达可以再稳一点",
        judgment="good",
    )
    proposal = generate_learning_update_proposals(store, role_id=role_id, knowledge_root=tmp_path / "knowledge")
    update = proposal["proposal"]
    target = Path(update["target_file"])
    before = target.read_text(encoding="utf-8")
    assert feedback_id in update["source_event_ids"]
    assert "财运表达可以再稳一点" not in before

    applied = apply_learning_update(store, update["id"])
    after = target.read_text(encoding="utf-8")
    assert applied["status"] == "applied"
    assert "财运表达可以再稳一点" in after


def test_creation_context_packet_uses_knowledge_without_transcript_by_default(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    _material(store, title="修行不是逃离生活", topic="修行")
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="修行",
        goal="生成一条道家修行方向口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="material_selection")

    packet = build_creation_context_packet(store, task_id, knowledge_root=tmp_path / "knowledge")

    assert "global_rewrite_playbook" in packet["knowledge_files"]
    assert "ip_creation_playbook" in packet["knowledge_files"]
    global_playbook = packet["knowledge"]["global_rewrite_playbook"]
    assert "Content Task And Mechanism" in global_playbook
    assert "Speaker Compatibility" in global_playbook
    assert "Source Discomfort And Objection" in global_playbook
    assert "Internal Logic" in global_playbook
    assert "internal_logic_alignment" in global_playbook
    assert "CTA is optional" in global_playbook
    assert "Expression integrity comes before length control" in global_playbook
    assert "perspective_translation" in global_playbook
    assert "Preferred patterns" not in global_playbook
    assert "Decision matrix" not in global_playbook
    assert len(global_playbook.splitlines()) < 180
    hook_playbook = packet["knowledge"]["hook_playbook"]
    assert "perspective_translation" in hook_playbook
    assert "strength parity" in hook_playbook.lower()
    assert packet["selected_materials"]
    assert packet["rewrite_requirements"]["target_length_range"] == [300, 500]
    assert packet["selected_materials"][0]["source_analysis"]["source_hook_text"]
    assert "transcript_text" not in packet["selected_materials"][0]


def test_file_and_runtime_global_rewrite_playbooks_stay_aligned() -> None:
    project_root = Path(__file__).resolve().parents[1]
    file_playbook = (project_root / "knowledge" / "creation" / "global-rewrite-playbook.md").read_text(
        encoding="utf-8"
    )

    assert file_playbook.strip() == DEFAULT_GLOBAL_REWRITE_PLAYBOOK.strip()


def test_songli_playbook_is_principle_based() -> None:
    project_root = Path(__file__).resolve().parents[1]
    playbook = project_root / "knowledge" / "ip" / "songlixinli" / "creation-playbook.md"
    text = playbook.read_text(encoding="utf-8")

    assert "说话者兼容" in text
    assert "反感可能正是留人机制" in text
    assert "处理钩子制造的核心异议" in text
    assert "行为背后的功能" in text
    assert "方案必须回应前面的解释" in text
    assert "推荐句式" not in text
    assert "核心公式" not in text
    assert "主题专项规则" not in text
    assert len(text.splitlines()) < 120


def test_rewrite_context_packet_excludes_risk_cleanup_playbooks(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_metaphysics_role(store)
    _material(store, title="自带财运的女性特征", topic="财运", hook="以下的特征你就要具备两点，你就是自带财运的女性。")
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="material_selection")

    packet = build_creation_context_packet(store, task_id, knowledge_root=tmp_path / "knowledge", stage_key="rewrite_draft")

    assert packet["stage_key"] == "rewrite_draft"
    assert packet["stage_contract_version"] == CREATION_STAGE_CONTRACT_VERSION
    assert "global_rewrite_playbook" in packet["knowledge_files"]
    assert "hook_playbook" not in packet["knowledge_files"]
    assert "global_risk_lexicon" not in packet["knowledge_files"]
    assert "risk_cleanup_playbook" not in packet["knowledge_files"]
    assert all("Do not soften risk into explanatory cooling" not in text for text in packet["knowledge"].values())


def test_creation_context_packet_uses_configured_ip_knowledge_slug(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="思丞说",
        positioning="玄学咨询获客型 IP",
        search_keywords=["财运"],
        fit_themes=["财运"],
        source_evidence={"knowledge_slug": "sichengshuo"},
    )
    store.confirm_ip_role(role_id, change_reason="test")
    _material(store, title="一个人发财前的征兆", topic="财运")
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="material_selection")

    packet = build_creation_context_packet(store, task_id, knowledge_root=tmp_path / "knowledge")

    assert "/sichengshuo/" in packet["knowledge_files"]["ip_creation_playbook"]


def test_rewrite_draft_preserves_viral_hook_asr_correction_and_length(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_metaphysics_role(store)
    material_id = _material(
        store,
        title="很多人忽略了的，但很重要的一个因素",
        topic="财运",
        hook="只有运气好的人才能刷到这条视频，因为这种视频一般情况下都会被限流。",
    )
    material = store.get_collected_material(material_id)
    assert material is not None
    source_package = dict(material["source_package"])
    long_transcript_unit = (
        "只有运气好的人才能刷到这条视频。今天我会站在一个挂失的角度跟大家聊一聊磁场。"
        "财运和事业卡住，不一定是不努力。很多时候是环境、关系、念头和判断一起影响了一个人。"
        "一个人住的地方长期混乱，身边的人长期抱怨，自己的念头长期焦急，机会来了也接不住。"
    )
    source_package["transcript_text"] = long_transcript_unit * 12
    with store.connect() as conn:
        conn.execute(
            "UPDATE collected_materials SET transcript_text = ?, source_package_json = ? WHERE id = ?",
            (source_package["transcript_text"], json.dumps(source_package, ensure_ascii=False), material_id),
        )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.95,
        decision="accepted",
        reasons=["适合玄学咨询获客"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成一条用于玄学咨询获客的短口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    selection = run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    analysis = selection["output"]["source_analysis"][material_id]
    assert analysis["source_hook_text"].startswith("只有运气好的人才能刷到这条视频")
    assert analysis["source_opening_text"].startswith("只有运气好的人才能刷到这条视频")
    assert "一个卦师的角度" in analysis["source_opening_text"]
    assert analysis["authority_frame"] == "卦师"
    assert {"from": "挂失", "to": "卦师"} in analysis["asr_corrections"]
    confirm_creation_stage(store, task_id, stage_key="material_selection")
    run_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="creation_brief")

    rewrite = run_creation_stage(store, task_id, stage_key="rewrite_draft", knowledge_root=tmp_path / "knowledge")
    output = rewrite["output"]
    draft = output["draft_text"]
    assert output["status"] == "needs_confirmation"
    assert 380 <= output["char_count"] <= 500
    assert draft.startswith("只有运气好的人才能刷到这条视频")
    assert "今天我会站在一个卦师的角度" in draft
    assert "卦师" in draft
    assert "挂失" not in draft
    assert "原文" not in draft
    assert "财运" in draft
    assert "事业" in draft
    assert "先看三个方面" in draft
    assert "第一，看" in draft
    assert "第二，看" in draft
    assert "第三，看" in draft
    assert "评论区" in draft
    assert "私信" not in draft
    assert output["quality_checks"]["internal_logic_alignment"]["passed"] is True
    assert output["quality_checks"]["bridge_body_alignment"]["passed"] is True
    assert output["quality_checks"]["parallel_structure_alignment"]["passed"] is True
    assert output["conversion_goal_alignment"]["soft_cta_present"] is True
    assert output["conversion_goal_alignment"]["cta_channel"] == "comment"
    assert output["conversion_goal_alignment"]["private_message_cta_present"] is False


def test_rewrite_draft_defers_source_risk_and_protects_opening(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_metaphysics_role(store)
    opening = "以下的特征你就要具备两点，你就是自带财运的女性。"
    material_id = _material(
        store,
        title="自带财运的女性特征",
        topic="财运",
        hook=opening,
    )
    material = store.get_collected_material(material_id)
    assert material is not None
    source_package = dict(material["source_package"])
    source_package["transcript_text"] = (
        f"{opening}第一，眼神稳，不慌张。第二，说话不乱，不轻易抱怨。"
        "第三，做事有分寸，机会来了能接得住。这样的财运，不是凭空来的。"
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE collected_materials SET transcript_text = ?, source_package_json = ? WHERE id = ?",
            (source_package["transcript_text"], json.dumps(source_package, ensure_ascii=False), material_id),
        )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.95,
        decision="accepted",
        reasons=["适合财运诊断"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成一条用于玄学咨询获客的短口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]

    selection = run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    analysis = selection["output"]["source_analysis"][material_id]
    assert analysis["discard_elements"] == []
    assert {item["term"] for item in analysis["deferred_risk_terms"]} >= {"自带财运", "财运"}
    confirm_creation_stage(store, task_id, stage_key="material_selection")
    brief = run_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=tmp_path / "knowledge")
    assert "自带财运" not in brief["output"]["brief"]["avoid"]
    confirm_creation_stage(store, task_id, stage_key="creation_brief")

    rewrite = run_creation_stage(store, task_id, stage_key="rewrite_draft", knowledge_root=tmp_path / "knowledge")
    draft = rewrite["output"]["draft_text"]
    assert draft.startswith(opening)
    assert rewrite["output"]["risk_notes"] == []
    assert rewrite["output"]["opening_preservation_mode"] == "exact_source_opening"
    assert {item["term"] for item in rewrite["output"]["deferred_risk_terms"]} >= {"自带财运", "财运"}
    confirm_creation_stage(store, task_id, stage_key="rewrite_draft")

    hook = run_creation_stage(store, task_id, stage_key="hook_enhancement", knowledge_root=tmp_path / "knowledge")
    assert hook["output"]["selected_hook"].startswith(opening)
    assert hook["output"]["hook_diff_type"] == "unchanged"
    assert hook["output"]["mechanism_preserved"] is True
    confirm_creation_stage(store, task_id, stage_key="hook_enhancement")

    risk = run_creation_stage(store, task_id, stage_key="risk_cleanup", knowledge_root=tmp_path / "knowledge")
    assert risk["output"]["cleaned_body"] == hook["output"]["body"]
    assert risk["output"]["high_risk_replacements"] == []
    assert {item["term"] for item in risk["output"]["unchanged_source_risk_terms"]} >= {"自带财运"}
    assert risk["output"]["risk_replacement_scope"]["change_type"] == "none"


def test_ultra_high_risk_is_replaced_only_in_risk_cleanup(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_metaphysics_role(store)
    material_id = _material(
        store,
        title="发财前的征兆",
        topic="财运",
        hook="一个人保证发财前，往往先稳住自己的节奏。",
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.95,
        decision="accepted",
        reasons=["适合财运诊断"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成一条用于玄学咨询获客的短口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="material_selection")
    run_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="creation_brief")

    rewrite = run_creation_stage(store, task_id, stage_key="rewrite_draft", knowledge_root=tmp_path / "knowledge")
    assert "保证发财" in rewrite["output"]["draft_text"]
    assert rewrite["output"]["risk_notes"] == []
    assert any(item["term"] == "保证发财" and item["action"] == "defer_to_risk_cleanup" for item in rewrite["output"]["deferred_risk_terms"])
    confirm_creation_stage(store, task_id, stage_key="rewrite_draft")
    hook = run_creation_stage(store, task_id, stage_key="hook_enhancement", knowledge_root=tmp_path / "knowledge")
    assert "保证发财" in hook["output"]["body"]
    confirm_creation_stage(store, task_id, stage_key="hook_enhancement")

    risk = run_creation_stage(store, task_id, stage_key="risk_cleanup", knowledge_root=tmp_path / "knowledge")
    assert "保证发财" not in risk["output"]["cleaned_body"]
    assert risk["output"]["high_risk_replacements"][0]["term"] == "保证发财"
    assert risk["output"]["risk_replacement_scope"]["change_type"] == "localized_term_replacement"
    assert risk["output"]["stage_contract_version"] == CREATION_STAGE_CONTRACT_VERSION
    assert risk["output"]["stage_contract_validation"]["passed"] is True
    assert risk["output"]["body_hash"]


def test_stage_contract_metadata_flows_between_stages(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_metaphysics_role(store)
    material_id = _material(
        store,
        title="发财前的征兆",
        topic="财运",
        hook="一个人保证发财前，往往先稳住自己的节奏。",
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.95,
        decision="accepted",
        reasons=["适合财运诊断"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成一条用于玄学咨询获客的短口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    for stage in ["material_selection", "creation_brief", "rewrite_draft", "hook_enhancement", "risk_cleanup"]:
        result = run_creation_stage(store, task_id, stage_key=stage, knowledge_root=tmp_path / "knowledge")
        assert result["output"]["stage_contract_version"] == CREATION_STAGE_CONTRACT_VERSION
        assert result["output"]["stage_contract_validation"]["passed"] is True
        confirm_creation_stage(store, task_id, stage_key=stage)

    publish = run_creation_stage(store, task_id, stage_key="publish_format", knowledge_root=tmp_path / "knowledge")

    assert publish["output"]["stage_contract_validation"]["passed"] is True
    assert publish["output"]["publish_package"]["body_char_count"] == publish["output"]["body_char_count"]
    assert publish["output"]["body_hash"]
    assert len(publish["output"]["upstream_stage_run_ids"]) == 5


def test_confirm_rejects_needs_retry_stage(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    store.insert_creation_stage_run(
        task_id=task_id,
        stage_key="rewrite_draft",
        status="needs_retry",
        provider="codex-agent",
        model="gpt-5.5",
        output_data={"stage_contract_validation": {"passed": False}},
    )

    with pytest.raises(ValueError, match="failed contract validation"):
        confirm_creation_stage(store, task_id, stage_key="rewrite_draft")


def test_publish_contract_rejects_body_rewrite(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_row = store.get_creation_task(task["task"]["id"])
    assert task_row is not None
    store.insert_creation_stage_run(
        task_id=task_row["id"],
        stage_key="risk_cleanup",
        status="confirmed",
        provider="codex-agent",
        model="gpt-5.5",
        output_data={"cleaned_body": "风险清理后的正文"},
    )

    validation = _validate_stage_contract(
        store,
        task_row,
        "publish_format",
        {"publish_package": {"cover_title_4": "财运自查", "video_title_18": "财运先自查", "description_100": "desc", "pinned_comment": "comment", "final_copy": "被发布阶段改过的正文"}},
    )

    assert validation["passed"] is False
    assert validation["checks"]["final_copy_matches_risk_cleaned_body"]["passed"] is False


def test_hook_enhancement_rejects_risk_denial_replacement() -> None:
    source = "以下的特征你就要具备两点，你就是自带财运的女性。"
    selected = "看一个女人有没有财气，不是看漂不漂亮，也不是说占两条就一定富。"

    validation = _validate_hook_enhancement(
        source_opening=source,
        selected_hook=selected,
        original_body=source + "第一，看眼神稳不稳。",
        enhanced_body=selected + "\n\n第一，看眼神稳不稳。",
    )

    assert validation["passed"] is False
    assert validation["diff_type"] == "replaced"
    assert validation["mechanism_preserved"] is False


def test_rewrite_draft_rejects_internal_process_terms(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    material_id = _material(store, title="一个人发财前的征兆", topic="财运")
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_id,
        task_id=None,
        fit_score=0.9,
        decision="accepted",
        reasons=["适合"],
    )
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    run_creation_stage(store, task_id, stage_key="material_selection", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="material_selection")
    run_creation_stage(store, task_id, stage_key="creation_brief", knowledge_root=tmp_path / "knowledge")
    confirm_creation_stage(store, task_id, stage_key="creation_brief")

    result = run_creation_stage(store, task_id, stage_key="rewrite_draft", knowledge_root=tmp_path / "knowledge")
    output = result["output"]

    assert output["quality_checks"]["no_internal_process_terms"]["passed"] is True


def test_stage_feedback_enters_learning_proposal(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = _confirmed_role(store)
    _material(store, title="一个人发财前的征兆", topic="财运")
    task = create_creation_task(
        store,
        role_id=role_id,
        topic="财运",
        goal="生成口播",
        platform="douyin",
        target_count=1,
    )
    task_id = task["task"]["id"]
    feedback_id = store.insert_creation_stage_feedback_event(
        task_id=task_id,
        role_id=role_id,
        stage_key="rewrite_draft",
        platform="douyin",
        judgment="rejected",
        human_note="开头变弱、字数太长、太像讲大道理",
    )

    proposal = generate_learning_update_proposals(store, role_id=role_id, knowledge_root=tmp_path / "knowledge")
    update = proposal["proposal"]
    assert feedback_id in update["source_event_ids"]
    assert "开头变弱、字数太长、太像讲大道理" in update["proposed_markdown"]


def test_publish_package_uses_semantic_titles_and_distinct_description() -> None:
    task = {"topic": "财运与有余磁场"}
    body = (
        "作为一个命理师，我告诉你，一个人想发财、事业想往上走，其实真不难。"
        "你先记住《道德经》里一句话：人之道，损不足以奉有余。"
        "人性会本能靠近看起来富足、稳定、有结果的人。"
        "你把有余的状态立起来，财运和事业才有机会靠近。"
    )

    package = _build_publish_package(task, body)

    assert package["cover_title_4"] == "有余磁场"
    assert package["video_title_18"] == "财运卡住先看有余感"
    assert package["description_100"] != package["final_copy"][: len(package["description_100"])]
    assert "有余" in package["description_100"]
