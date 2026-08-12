# Equity Lawyer Douyin Round 2 Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce evidence-backed, content-spread-first recommendations for launching an equity and investment lawyer IP on Douyin.

**Architecture:** Reuse the current MXNZP adapters and `data/mcn_ops.sqlite`. Keyword searches create research Runs and Candidates, author expansion writes only author/video research tables, and transcript/comment responses remain research evidence rather than formal collected materials. Synthesize all conclusions into `research/lawyer-equity-douyin-round2.md`.

**Tech Stack:** Python 3.11, existing `mcn_ops.collection` modules, MXNZP Douyin API, SQLite, Markdown.

## Global Constraints

- Do not modify application source code.
- Do not create or confirm an IP role.
- Do not call `mcn collect run`, `mcn collect task keyword`, or `mcn collect author materialize`.
- Do not increase `collected_materials`.
- Prefer content-spread evidence over commercial-conversion evidence.
- Do not reproduce long third-party transcripts in the research Markdown.
- Preserve existing uncommitted user changes.

---

### Task 1: Record Round 2 Baseline

**Files:**
- Inspect: `data/mcn_ops.sqlite`
- Read: `research/lawyer-equity-douyin-exploration.md`

- [ ] Record counts for `collected_materials`, `collection_runs`, `collection_candidates`, `douyin_authors`, `douyin_author_videos`, and `mxnzp_call_logs`.
- [ ] Confirm MXNZP credentials and Douyin cookie load without printing secrets.
- [ ] Build the Round 1 URL set to prevent duplicate evidence inflation.

### Task 2: Expand High-Spread Topics

**Data target:** 200–250 new keyword Candidate rows.

- [ ] Search 25–30 short user-language keywords grouped into partnership conflict, equity allocation, control loss, nominee/shareholder disputes, and financing.
- [ ] Fetch up to three pages per keyword while pagination remains useful.
- [ ] Create one research `collection_runs` row per keyword with provider `mxnzp_candidate_research_round2`.
- [ ] Normalize with `candidates_from_mxnzp_result`, deduplicate within each run, and write only `collection_candidates`.
- [ ] Stop early when two consecutive pages contribute no new useful videos.
- [ ] Record API failures and search drift in each Run summary.

### Task 3: Rank Topics and Resolve Benchmark Authors

**Data target:** 10–12 benchmark authors.

- [ ] Deduplicate Round 2 candidates by source URL or work ID.
- [ ] Rank with existing `engagement_score` plus saves, shares, and relative-breakout evidence.
- [ ] Calculate per-topic candidate count, S/A/B count, median engagement, and top-decile engagement.
- [ ] Identify repeated authors and classify them as lawyer, equity/business advisor, or general business-story account.
- [ ] Resolve author identity through existing `user_search` and `user_info` adapters, then upsert `douyin_authors`.
- [ ] Exclude ambiguous identities from automatic author expansion and document them.

### Task 4: Expand Benchmark Author Works

**Data target:** 100–150 stored author videos.

- [ ] For each resolved author, call existing `user_post` with `sortType=1`.
- [ ] Fetch up to five pages, stopping after two pages without a relevant or high-performing work.
- [ ] Store works only in `douyin_author_videos`.
- [ ] Rank author works by existing engagement score.
- [ ] Retain 8–12 relevant works per author for model analysis.
- [ ] Do not call materialization.

### Task 5: Select Transcript and Comment Samples

**Data target:** 50–60 transcripts and comments from 15–20 videos.

- [ ] Select absolute S/A/B hits, relative breakouts, high-save/high-share samples, and low-performing control samples.
- [ ] Ensure every core topic, creator type, format, and duration band appears.
- [ ] Extract text through existing `video_to_text_v2` and log calls under research Runs.
- [ ] Analyze hooks, formats, emotional drivers, structures, professional density, and reproducibility.
- [ ] Fetch the first useful comment page for 15–20 high-value videos.
- [ ] Classify comments into personal experience, solution request, challenge, template/calculation request, emotional reaction, and user debate.

### Task 6: Synthesize the Round 2 Markdown

**File:**
- Create: `research/lawyer-equity-douyin-round2.md`

- [ ] Document sample method, database traceability, and evidence limits.
- [ ] Add keyword and topic performance tables.
- [ ] Add benchmark-author performance and format comparisons.
- [ ] Add 50–60 transcript analyses using short excerpts and paraphrases.
- [ ] Add comment-language findings.
- [ ] Rank spread topics, hooks, structures, and formats.
- [ ] Define five to eight repeatable content models validated across independent authors.
- [ ] Produce 30–50 launch-test topics.
- [ ] Recommend three to five launch content pillars.
- [ ] Separate proven conclusions, directional hypotheses, and rejected assumptions.

### Task 7: Verify Research Integrity

- [ ] Confirm `collected_materials` equals the Task 1 baseline.
- [ ] Confirm every reported count matches SQLite.
- [ ] Confirm every primary content model has evidence from at least three authors and five high-performing works; downgrade models that do not.
- [ ] Confirm the Markdown contains source links, no required empty sections, and no long copied transcripts.
- [ ] Record shortfalls honestly if API or author-identity limits prevent a numerical target.
