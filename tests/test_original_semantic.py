from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mcn_ops.cli import main
from mcn_ops.original import OriginalWorkspace
from mcn_ops.original.semantic import OpenAICompatibleEmbedder, SemanticIndex, chunk_text, evaluate_retrieval
from mcn_ops.store import Store


class ConceptEmbedder:
    model_id = "test-concepts-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "双相" in text or "躁郁" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "亲子" in text or "家庭" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def test_semantic_retrieval_finds_synonym_and_enforces_ip_scope(tmp_path: Path) -> None:
    store = Store(tmp_path / "ledger.sqlite")
    original = OriginalWorkspace(store, tmp_path / "private")
    original.init()
    first = store.upsert_ip_role(name="甲")
    second = store.upsert_ip_role(name="乙")
    shared = original.add_source(kind="domain_knowledge", title="双相情感障碍", text="双相情感障碍的情绪波动需要区分。")
    original.add_note(shared["id"], "亲子沟通的私有解读", role_id=first)
    private = original.add_source(role_id=first, kind="viral_work", title="家庭沟通", text="亲子沟通不要只问成绩。")
    original.add_source(role_id=second, kind="experience", title="私人经历", text="躁郁症经历只属于乙。")
    assert original.find_sources("躁郁症", role_id=first) == []

    index = SemanticIndex(original, ConceptEmbedder(), local_path=tmp_path / "qdrant")
    try:
        report = index.rebuild()
        assert report["source_count"] == 3
        found = index.find("躁郁症", role_id=first)
        assert found[0]["id"] == shared["id"]
        comparison = evaluate_retrieval(original, index, [{
            "role_id": first, "query": "躁郁症", "expected_source_ids": [shared["id"]],
        }])
        assert comparison["lexical_cases_with_hit"] == 0
        assert comparison["semantic_cases_with_hit"] == 1
        assert private["id"] in {item["id"] for item in index.find("家庭关系", role_id=first)}
        assert all(item["title"] != "私人经历" for item in found)
        assert all(item["passage"] != "亲子沟通的私有解读" for item in index.find("亲子关系", role_id=second))
        original.add_source(role_id=first, kind="domain_knowledge", title="新资料", text="亲子关系补充。")
        with pytest.raises(ValueError, match="stale|missing"):
            # The old index cannot claim that it includes the newly added source.
            index.find("新资料", role_id=first, require_fresh=True)
        index.rebuild()
        assert any(item["title"] == "新资料" for item in index.find("亲子", role_id=first))
    finally:
        index.close()


def test_long_source_keeps_overlapping_passages() -> None:
    text = "甲" * 1200
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) == 3
    assert chunks[0][-50:] == chunks[1][:50]


def test_embedding_adapter_validates_response_and_keeps_key_out_of_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return io.BytesIO(json.dumps({"data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]}).encode())

    monkeypatch.setattr("mcn_ops.original.semantic.urlopen", fake_urlopen)
    embedder = OpenAICompatibleEmbedder(url="https://example.org/embeddings", model_id="test", api_key="secret")
    assert embedder.embed(["甲", "乙"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert requests[0].get_header("Authorization") == "Bearer secret"
    assert b"secret" not in requests[0].data
    with pytest.raises(ValueError, match="API key"):
        OpenAICompatibleEmbedder(url="https://example.org/embeddings", model_id="test")


def test_cli_semantic_index_and_writing_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db = tmp_path / "ledger.sqlite"
    root = tmp_path / "private"
    store = Store(db)
    original = OriginalWorkspace(store, root)
    original.init()
    role_id = store.upsert_ip_role(name="甲")
    store.confirm_ip_role(role_id)
    source = original.add_source(role_id=role_id, kind="domain_knowledge", title="双相", text="双相情感障碍资料。")
    task_id = original.new_task(role_id=role_id, topic="躁郁症", platform="douyin")["id"]
    monkeypatch.setattr("mcn_ops.cli.OpenAICompatibleEmbedder", lambda **kwargs: ConceptEmbedder())
    base = [
        "--db-path", str(db), "original", "--knowledge-root", str(root),
        "--embedding-url", "http://localhost:1/embeddings", "--embedding-model", "test-concepts-v1",
    ]
    assert main(base + ["index", "rebuild"]) == 0
    capsys.readouterr()
    assert main(base + ["source", "find", "--role-id", role_id, "--query", "躁郁症", "--semantic"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == source["id"]
    assert main(base + ["task", "prepare", "--task-id", task_id, "--semantic"]) == 0
    assert json.loads(capsys.readouterr().out)["sources"][0]["id"] == source["id"]
