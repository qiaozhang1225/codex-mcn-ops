"""Rebuildable semantic index. Complete source files remain authoritative."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..store import now_iso
from .workspace import OriginalWorkspace


class Embedder(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbedder:
    def __init__(self, *, url: str, model_id: str, api_key: str = "", timeout: int = 60):
        local = urlparse(url).hostname in {"localhost", "127.0.0.1", "::1"}
        if not (url.startswith("https://") or (url.startswith("http://") and local)):
            raise ValueError("embedding endpoint must use HTTPS or local HTTP")
        if not model_id or (not local and not api_key):
            raise ValueError("embedding model and remote API key are required")
        self.url = url
        self.model_id = model_id
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body = json.dumps({"model": self.model_id, "input": texts}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.url,
            data=body,
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        items = sorted(payload["data"], key=lambda item: item["index"])
        if [item["index"] for item in items] != list(range(len(texts))):
            raise ValueError("embedding provider returned invalid vector indexes")
        vectors = [[float(value) for value in item["embedding"]] for item in items]
        _check_vectors(vectors, len(texts))
        return vectors


def _check_vectors(vectors: list[list[float]], expected: int) -> int:
    if len(vectors) != expected or not vectors or not vectors[0]:
        raise ValueError("embedding provider returned the wrong number of vectors")
    dimension = len(vectors[0])
    if any(len(vector) != dimension or not all(math.isfinite(value) for value in vector) for vector in vectors):
        raise ValueError("embedding provider returned invalid vectors")
    return dimension


def chunk_text(text: str, *, max_chars: int = 1000, overlap: int = 100) -> list[str]:
    if not text.strip():
        return []
    if max_chars < 2 or overlap < 0 or overlap >= max_chars:
        raise ValueError("invalid passage size or overlap")
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


class SemanticIndex:
    def __init__(
        self, workspace: OriginalWorkspace, embedder: Embedder,
        *, local_path: Path | str | None = None, url: str | None = None,
    ):
        if (local_path is None) == (url is None):
            raise ValueError("choose exactly one Qdrant local path or URL")
        if url is not None and urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Qdrant URL must be local; private source passages are indexed")
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:
            raise RuntimeError("install the semantic extra: pip install -e '.[semantic]'") from exc
        self.models = models
        self.workspace = workspace
        self.embedder = embedder
        self.client = QdrantClient(path=str(local_path)) if local_path is not None else QdrantClient(url=url)

    def close(self) -> None:
        self.client.close()

    def _collection(self, dimension: int) -> str:
        fingerprint = hashlib.sha256(self.embedder.model_id.encode("utf-8")).hexdigest()[:12]
        return f"mcn_original_{fingerprint}_{dimension}"

    def _source_rows(self):
        with self.workspace.store.connect() as conn:
            return conn.execute(
                """SELECT s.id, s.source_hash FROM original_sources s
                   WHERE NOT EXISTS (SELECT 1 FROM original_sources newer WHERE newer.supersedes_id = s.id)
                   ORDER BY s.id"""
            ).fetchall()

    def _source_fingerprint(self) -> str:
        with self.workspace.store.connect() as conn:
            notes = conn.execute(
                """SELECT n.id, n.source_id, n.role_id, n.note, n.source_quote FROM original_source_notes n
                   JOIN original_sources s ON s.id = n.source_id
                   WHERE NOT EXISTS (SELECT 1 FROM original_sources newer WHERE newer.supersedes_id = s.id)
                   ORDER BY n.source_id, n.id"""
            ).fetchall()
        value = "\n".join(
            [f"{row['id']}:{row['source_hash']}" for row in self._source_rows()]
            + [f"{row['id']}:{row['source_id']}:{row['role_id']}:{row['note']}:{row['source_quote']}" for row in notes]
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def rebuild(self) -> dict[str, object]:
        rows = self._source_rows()
        if not rows:
            raise ValueError("add complete sources before rebuilding the semantic index")
        passages: list[tuple[dict, int, str, str | None]] = []
        for row in rows:
            source = self.workspace.get_source(row["id"])
            source_passages = chunk_text(source["text"])
            for position, passage in enumerate(source_passages):
                passages.append((source, position, passage, source["role_id"]))
            for position, note in enumerate(source["notes"], start=len(source_passages)):
                passages.append((source, position, note["note"], note["role_id"] or source["role_id"]))
        vectors: list[list[float]] = []
        for start in range(0, len(passages), 32):
            batch = passages[start:start + 32]
            embedded = self.embedder.embed([f"{source['title']}\n{passage}" for source, _, passage, _ in batch])
            _check_vectors(embedded, len(batch))
            vectors.extend(embedded)
        dimension = _check_vectors(vectors, len(passages))
        collection = self._collection(dimension)
        with self.workspace.store.connect() as conn:
            conn.execute("DELETE FROM original_semantic_index_builds WHERE collection_name = ?", (collection,))
        if self.client.collection_exists(collection):
            self.client.delete_collection(collection)
        self.client.create_collection(
            collection_name=collection,
            vectors_config=self.models.VectorParams(size=dimension, distance=self.models.Distance.COSINE),
        )
        for start in range(0, len(passages), 32):
            points = []
            for (source, position, passage, visibility_role), vector in zip(passages[start:start + 32], vectors[start:start + 32]):
                points.append(self.models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{source['id']}:{position}")),
                    vector=vector,
                    payload={
                        "source_id": source["id"], "role_id": visibility_role,
                        "kind": source["kind"], "source_hash": source["source_hash"],
                        "position": position, "passage": passage,
                    },
                ))
            self.client.upsert(collection_name=collection, points=points, wait=True)
        with self.workspace.store.connect() as conn:
            conn.execute(
                """INSERT INTO original_semantic_index_builds
                   (collection_name, model_id, source_fingerprint, built_at) VALUES (?, ?, ?, ?)""",
                (collection, self.embedder.model_id, self._source_fingerprint(), now_iso()),
            )
        return {
            "collection": collection, "model_id": self.embedder.model_id,
            "dimension": dimension, "source_count": len(rows), "passage_count": len(passages),
        }

    def find(self, query: str, *, role_id: str, limit: int = 10, require_fresh: bool = True) -> list[dict[str, object]]:
        if not self.workspace.store.get_ip_role(role_id):
            raise KeyError(f"IP role not found: {role_id}")
        if not query.strip() or limit < 1:
            raise ValueError("nonempty query and positive limit are required")
        vector = self.embedder.embed([query])[0]
        dimension = _check_vectors([vector], 1)
        collection = self._collection(dimension)
        if not self.client.collection_exists(collection):
            raise ValueError("semantic index is missing; run original index rebuild")
        if require_fresh:
            with self.workspace.store.connect() as conn:
                build = conn.execute(
                    "SELECT source_fingerprint FROM original_semantic_index_builds WHERE collection_name = ?",
                    (collection,),
                ).fetchone()
            if not build or build["source_fingerprint"] != self._source_fingerprint():
                raise ValueError("semantic index is stale; run original index rebuild")
        scoped = self.models.Filter(should=[
            self.models.FieldCondition(key="role_id", match=self.models.MatchValue(value=role_id)),
            self.models.IsNullCondition(is_null=self.models.PayloadField(key="role_id")),
        ])
        hits = self.client.query_points(
            collection_name=collection, query=vector, query_filter=scoped,
            with_payload=True, limit=max(limit * 4, 20),
        ).points
        found: list[dict[str, object]] = []
        seen: set[str] = set()
        for hit in hits:
            payload = hit.payload or {}
            source_id = str(payload["source_id"])
            if source_id in seen:
                continue
            source = self.workspace.get_source(source_id, role_id=role_id)
            if source["source_hash"] != payload["source_hash"]:
                raise ValueError(f"semantic index is stale for source: {source_id}")
            seen.add(source_id)
            found.append({
                "id": source_id, "title": source["title"], "kind": source["kind"],
                "origin": source["origin"], "source_hash": source["source_hash"],
                "score": hit.score, "passage": payload["passage"], "position": payload["position"],
            })
            if len(found) >= limit:
                break
        return found


def evaluate_retrieval(
    workspace: OriginalWorkspace, index: SemanticIndex, cases: list[dict], *, limit: int = 10,
) -> dict[str, object]:
    if not cases:
        raise ValueError("evaluation needs at least one real query case")
    results = []
    for case in cases:
        role_id = case["role_id"]
        query = case["query"]
        expected = case["expected_source_ids"]
        if not isinstance(expected, list) or not expected:
            raise ValueError("each query needs expected_source_ids")
        for source_id in expected:
            workspace.get_source(source_id, role_id=role_id)
        lexical = [item["id"] for item in workspace.find_sources(query, role_id=role_id, limit=limit)]
        semantic = [item["id"] for item in index.find(query, role_id=role_id, limit=limit)]
        results.append({
            "query": query, "role_id": role_id, "expected_source_ids": expected,
            "lexical_ids": lexical, "semantic_ids": semantic,
            "lexical_hits": sorted(set(expected) & set(lexical)),
            "semantic_hits": sorted(set(expected) & set(semantic)),
        })
    return {
        "case_count": len(results), "limit": limit,
        "lexical_cases_with_hit": sum(bool(item["lexical_hits"]) for item in results),
        "semantic_cases_with_hit": sum(bool(item["semantic_hits"]) for item in results),
        "cases": results,
    }
