from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcn_ops.cli import main
from mcn_ops.original import OriginalWorkspace
from mcn_ops.store import Store


def role(store: Store, name: str) -> str:
    role_id = store.upsert_ip_role(
        name=name,
        positioning="青春期心理健康知识口播",
        role_baseline="愿意解释复杂感受的咨询师",
        speaking_posture="直接、通俗",
        target_audience={"life_stage": "家长"},
    )
    store.confirm_ip_role(role_id, change_reason="test")
    return role_id


def workspace(tmp_path: Path) -> tuple[OriginalWorkspace, Store, str]:
    store = Store(tmp_path / "ledger.sqlite")
    original = OriginalWorkspace(store, tmp_path / "private")
    original.init()
    return original, store, role(store, "甲")


def test_complete_sources_are_searchable_without_analysis_and_isolated_by_ip(tmp_path: Path) -> None:
    original, store, first_role = workspace(tmp_path)
    second_role = role(store, "乙")
    work = original.add_source(
        role_id=first_role,
        kind="viral_work",
        title="青春期亲子沟通",
        origin="https://example.org/work",
        text="孩子不肯说话时，先听完一句，再问他需要什么。",
    )
    domain = original.add_source(
        role_id=first_role,
        kind="domain_knowledge",
        title="家庭沟通资料",
        text="青春期沟通需要区分拒绝交流和需要独处。",
    )
    original.add_note(work["id"], "先听的表达值得分析", source_quote="先听完一句")

    found = original.find_sources("青春期亲子沟通", role_id=first_role)
    assert {item["id"] for item in found} == {work["id"], domain["id"]}
    assert original.get_source(work["id"], role_id=first_role)["text"].endswith("需要什么。")
    assert original.get_source(work["id"], role_id=first_role)["notes"][0]["note"] == "先听的表达值得分析"
    assert original.add_source(
        role_id=first_role, kind="viral_work", title="重复作品", origin="https://example.org/work",
        text="孩子不肯说话时，先听完一句，再问他需要什么。",
    )["id"] == work["id"]
    assert original.find_sources("青春期", role_id=second_role) == []
    with pytest.raises(PermissionError):
        original.get_source(work["id"], role_id=second_role)
    with pytest.raises(ValueError, match="source quote"):
        original.add_note(work["id"], "错误引文", source_quote="原文没有")


def test_original_task_keeps_candidates_and_exact_accepted_copy(tmp_path: Path) -> None:
    original, store, role_id = workspace(tmp_path)
    source = original.add_source(
        role_id=role_id, kind="ip_knowledge", title="咨询室见闻",
        text="有些家长把沉默误当成对抗。",
    )
    task = original.new_task(role_id=role_id, topic="青春期沉默", platform="douyin", outline="从家长误解切入")
    task_id = task["id"]
    packet = original.prepare(task_id, source_ids=[source["id"]])
    assert packet["sources"][0]["text"] == "有些家长把沉默误当成对抗。"
    assert "mandatory hook" in packet["writing_contract"]
    assert packet["outline"] == "从家长误解切入"
    first = original.submit(task_id, {
        "title": "孩子沉默时", "angle": "误读沉默", "body": "孩子不说话，未必是在和你对抗。先给他一点空间。",
        "source_ids": [source["id"]], "research_notes": "",
    })
    revised_body = "别急着追问孩子为什么沉默。先把你自己的焦虑放一放，再问他愿不愿意聊。"
    second = original.submit(task_id, {
        "title": "别急着追问", "angle": "给家长一个可执行动作", "body": revised_body,
        "source_ids": [source["id"]], "research_notes": "保留知识点，重写表达",
    })
    assert len(original.task(task_id)["drafts"]) == 2
    assert first["draft_id"] != second["draft_id"]
    accepted = original.accept(task_id, second["draft_id"])
    package = store.get_content_package(accepted["content_id"])
    assert package["body"] == revised_body
    assert package["title"] == "别急着追问"
    with pytest.raises(ValueError, match="already"):
        original.accept(task_id, first["draft_id"])


def test_original_submission_rejects_cross_ip_source_and_detects_tampering(tmp_path: Path) -> None:
    original, store, first_role = workspace(tmp_path)
    second_role = role(store, "乙")
    source = original.add_source(role_id=second_role, kind="experience", title="私事", text="个人经历")
    task_id = original.new_task(role_id=first_role, topic="青春期", platform="douyin")["id"]
    with pytest.raises(PermissionError):
        original.submit(task_id, {"title": "标题", "angle": "角度", "body": "正文", "source_ids": [source["id"]]})
    with store.connect() as conn:
        private_path = conn.execute("SELECT private_path FROM original_sources WHERE id = ?", (source["id"],)).fetchone()[0]
    (original.root / private_path).write_text("篡改", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        original.get_source(source["id"], role_id=second_role)


def test_existing_collected_work_imports_without_rewrite_classification(tmp_path: Path) -> None:
    original, store, role_id = workspace(tmp_path)
    run_id = store.create_collection_run(
        task_id=None, role_id=None, topic="青春期", target_count=1,
        like_floor=1, super_like_threshold=100, tool_provider="mock",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "https://example.org/viral",
            "title": "孩子不说话时",
            "transcript_text": "完整口播：孩子不说话时，先问自己有没有在倾听。",
            "source_platform": "mock",
        },
        material_understanding={}, raw={},
    )
    source = original.import_material(material_id, role_id=role_id)
    assert original.get_source(source["id"], role_id=role_id)["text"].startswith("完整口播")
    assert source["origin"] == "https://example.org/viral"


def test_cli_original_source_and_task_journey(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "ledger.sqlite"
    root = tmp_path / "private"
    store = Store(db)
    store.init_db()
    role_id = role(store, "甲")
    source_file = tmp_path / "source.txt"
    source_file.write_text("青春期孩子需要被认真倾听。", encoding="utf-8")
    base = ["--db-path", str(db), "original", "--knowledge-root", str(root)]
    assert main(base + ["source", "add", "--role-id", role_id, "--kind", "domain_knowledge", "--title", "沟通", "--input", str(source_file)]) == 0
    source_id = json.loads(capsys.readouterr().out)["id"]
    assert main(base + ["task", "new", "--role-id", role_id, "--topic", "青春期", "--platform", "douyin"]) == 0
    task_id = json.loads(capsys.readouterr().out)["id"]
    assert main(base + ["task", "prepare", "--task-id", task_id]) == 0
    assert json.loads(capsys.readouterr().out)["sources"][0]["id"] == source_id
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"title": "听孩子说话", "angle": "家长行动", "body": "先听完，再表达。", "source_ids": [source_id]}), encoding="utf-8")
    assert main(base + ["task", "submit", "--task-id", task_id, "--input", str(response)]) == 0
    draft_id = json.loads(capsys.readouterr().out)["draft_id"]
    assert main(base + ["task", "accept", "--task-id", task_id, "--draft-id", draft_id]) == 0
    assert json.loads(capsys.readouterr().out)["content_id"]


def test_performance_keeps_comparable_series_and_human_decision(tmp_path: Path) -> None:
    original, store, role_id = workspace(tmp_path)
    task_ids = []
    for index in range(3):
        task_id = original.new_task(role_id=role_id, topic=f"话题 {index}", platform="douyin")["id"]
        draft = original.submit(task_id, {
            "title": f"稿 {index}", "angle": "实验", "body": f"正文 {index}", "source_ids": [],
        })
        original.accept(task_id, draft["draft_id"])
        task_ids.append(task_id)
    first = original.add_observation(task_ids[0], account_id="experiment", age_hours=24, organic_views=120)
    second = original.add_observation(task_ids[1], account_id="experiment", age_hours=24, organic_views=900)
    original.add_observation(task_ids[2], account_id="real-person", age_hours=24, organic_views=3000)
    original.add_observation(task_ids[2], account_id="experiment", age_hours=48, organic_views=4000)
    report = original.performance_report(role_id=role_id, account_id="experiment", platform="douyin", age_hours=24)
    assert [item["organic_views"] for item in report["observations"]] == [120, 900]
    with pytest.raises(ValueError, match="same IP"):
        original.record_decision(
            role_id=role_id, account_id="experiment", platform="douyin", age_hours=48,
            evidence_ids=[first["id"]], hypothesis="某种开头可能有效", decision="accept",
        )
    decision = original.record_decision(
        role_id=role_id, account_id="experiment", platform="douyin", age_hours=24,
        evidence_ids=[first["id"], second["id"]],
        hypothesis="直接描述家长困境可能更吸引点击", decision="revise",
        next_variation="再试一个更具体的困境场景",
    )
    assert decision["decision"] == "revise"
    assert len(original.performance_report(role_id=role_id, account_id="experiment", platform="douyin", age_hours=24)["decisions"]) == 1
