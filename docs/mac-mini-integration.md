# Mac mini integration checkpoint

This branch contains the new original-writing and knowledge-base code. It does not contain private IP sources, the Mac mini's existing SQLite data, logged-in Douyin/WeChat Channels sessions, media, or credentials. Pull the branch into an isolated checkout and preserve the Mac mini's operational data before running migrations or collection. Do not copy the MacBook test database into the Mac mini production ledger.

## Local verification after pulling

1. Fetch `codex/knowledge-led-original-content` and inspect its diff against `main`. Install the project with `pip install -e '.[semantic]'` in an isolated environment. Run `python -m pytest -q` and `mcn --help`.
2. Back up the Mac mini's real SQLite ledger and any existing private knowledge files together. If `Store.init_db` reports a legacy collection schema, run the repository's explicit collection migration on a validated copy before attempting `mcn original`; do not use this new command to bypass migration.
3. Confirm an existing IP role and inspect its ID. Use the already working Douyin/Channels search and transcription routes to obtain complete works. For a saved `collected_materials` item with complete transcript, run `mcn original source import-material --role-id ROLE --material-id MATERIAL`. If the work and transcript exist but no formal material was created, run `mcn original source import-work --role-id ROLE --source-work-id WORK`. Neither route requires historical `formal_rewrite_base` classification. Add IP/domain knowledge with `source add`; keep files in ignored private storage. Inspect full text with `source read` and integrity with `original doctor`.
4. Propose and activate a private Markdown page for the IP. Use `topic suggest`, `task new`, `task prepare`, `task submit`, and `task accept` to complete one original-writing path without the v3 template gates. Compare the accepted content package body byte-for-byte with the chosen draft. No command in this path posts a video.

## Semantic retrieval trial

Configure `MCN_EMBEDDING_URL` as the full OpenAI-compatible `/embeddings` endpoint, `MCN_EMBEDDING_MODEL` as the exact deployed model name, and `MCN_EMBEDDING_API_KEY` for a remote provider. An HTTP endpoint is accepted only on localhost; a remote endpoint requires HTTPS. Source passages are sent to that embedding endpoint, so select an approved provider for private IP material. Qdrant uses ignored local on-disk storage by default; set `MCN_QDRANT_URL=http://localhost:6333` for the local Docker service. Remote Qdrant URLs are intentionally rejected.

Run `mcn original index rebuild`, then `mcn original source find --role-id ROLE --query '实际写作问题' --semantic`. Read matched complete sources. Create a private JSON file such as:

```json
[
  {"role_id": "role_xxx", "query": "受众会说的真实问题", "expected_source_ids": ["osrc_xxx"]}
]
```

Run `mcn original index evaluate --input data/retrieval-cases.json`. This reports lexical and semantic hits side by side, including misses; it does not assert that one model is better from a synthetic benchmark. Add real questions and expected sources as work progresses. Rebuild after any source or note change. Keep query cases and output under ignored private storage.

## Collection interface to verify on Mac mini

The integration points are `Store.get_collected_material(material_id)` and `Store.source_package_for_work(source_work_id)`: they expose title, stable origin or work ID, and complete `transcript_text`. The new imports store private immutable source versions. The current branch does not change login, platform search, pagination, media acquisition, or ASR; the previously verified Mac mini routes remain responsible for those. Verify one Douyin and one WeChat Channels work through the appropriate import and `source read`, including a clear error for a record without complete transcript. Document any Mac mini-specific adapter discrepancy in the branch; do not silently truncate a transcript or promote a search hit to a complete work.

Video generation, live ADB final submission, and automatic creator-center metric reading remain separate later slices. The current manual `performance add/report/decide` path can be tested with known non-production observations, but it does not verify traffic growth or a live publication.
