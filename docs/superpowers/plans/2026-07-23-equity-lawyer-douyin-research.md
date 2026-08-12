# Equity Lawyer Douyin Research Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. This is a research run, not a feature-development plan.

**Goal:** Use the existing Douyin search, candidate normalization, database ledger, and transcript extraction capabilities to identify the first reliable content patterns for an equity and investment lawyer IP.

**Architecture:** Search results are fetched through the existing MXNZP adapter and recorded only as collection runs, candidates, and API call logs in `data/mcn_ops.sqlite`. Selected transcripts, analysis, and research conclusions are written to `research/lawyer-equity-douyin-exploration.md`; no row may be added to `collected_materials`.

**Tech Stack:** Python 3.11, existing `mcn_ops.collection` modules, MXNZP Douyin API adapter, SQLite, Markdown.

## Global Constraints

- Do not modify application source code or add a new collection workflow.
- Existing database candidate and API-log tables may be used.
- `collected_materials` count must be unchanged before and after the research run.
- Use the existing MXNZP request cache unless a stale response is proven.
- Store all selected copy, metrics, analysis, and conclusions in one Markdown file.
- Treat this as exploratory research; do not create or confirm an IP role yet.

---

### Task 1: Establish the research baseline

**Files:**
- Inspect: `data/mcn_ops.sqlite`
- Create during Task 5: `research/lawyer-equity-douyin-exploration.md`

- [ ] Record current row counts for `collected_materials`, `collection_runs`, `collection_candidates`, and `mxnzp_call_logs`.
- [ ] Confirm MXNZP credentials load successfully without printing secrets.
- [ ] Record the starting `collected_materials` count as the formal-ingestion guard.

### Task 2: Run the first keyword scan

**Seed keywords:**

1. 股权律师
2. 股权设计
3. 股权纠纷
4. 投融资律师
5. 合伙协议
6. 股权代持
7. 对赌协议
8. 创始人被踢出局
9. 合伙人闹掰
10. 大股东架空小股东
11. 创业公司股权怎么分
12. 小股东如何保护自己

- [ ] Create one `collection_runs` row per keyword with provider `mxnzp_candidate_research`.
- [ ] Fetch the first search page through the existing `douyin_search_videos` tool.
- [ ] Normalize and deduplicate results with existing runner helpers.
- [ ] Upsert every result into `collection_candidates` with status `discovered`.
- [ ] Log each request through `LoggedToolExecutor`.
- [ ] Finish every research run without calling `TopicCollectionRunner.run`.

### Task 3: Rank and select research samples

- [ ] Rank candidates with the existing `engagement_score`.
- [ ] Retain tier S samples at 100,000 or more likes.
- [ ] Retain tier A samples at 10,000 or more likes.
- [ ] Retain tier B samples at 3,000 or more likes when comments, saves, shares, or keyword-relative ranking is strong.
- [ ] Select up to 20 representative videos across business, legal-mechanism, conflict, and decision keywords.
- [ ] Prefer recurring authors and samples that expose a clear founder, shareholder, investor, or company-control problem.

### Task 4: Extract selected copy without formal ingestion

- [ ] Call the existing `douyin_extract_video_text` tool for selected videos with a valid source URL.
- [ ] Keep transcript results in the research process and Markdown only.
- [ ] If extraction fails, record the title, metrics, URL, and failure reason instead of retrying blindly.
- [ ] Do not call `insert_collected_material`, `mcn collect run`, or `mcn collect task keyword`.

### Task 5: Write the research Markdown

**File:**
- Create: `research/lawyer-equity-douyin-exploration.md`

- [ ] Record scope, date, sample method, and formal-ingestion guard.
- [ ] Add the complete keyword pool and per-keyword result summary.
- [ ] Add a candidate table with title, author, metrics, URL, and tier.
- [ ] Add selected transcripts and structural breakdowns.
- [ ] Write conclusions on viral logic, audience segments, core needs, content forms, repeated authors, and commercial relevance.
- [ ] Add tested hypotheses, rejected hypotheses, evidence limits, and second-round keywords.

### Task 6: Verify research integrity

- [ ] Recount `collected_materials` and confirm the value equals the Task 1 baseline.
- [ ] Confirm new rows exist in `collection_runs`, `collection_candidates`, and `mxnzp_call_logs`.
- [ ] Confirm the Markdown contains no empty required section and includes source URLs for selected samples.
- [ ] Report API/search limitations honestly when a keyword returns no usable result.
