# Material Collection SOP

## Purpose

Collect reusable short-video material for IP creation while keeping the system CLI-first and auditable.

## Commands

```bash
mcn collect role upsert --name "知识型老师" --search-keyword 知识型口播
mcn collect role confirm --role-id role_xxxxxxxxxxxx --change-reason 首次确认
mcn collect run --topic 知识型口播 --target-count 1 --tool-provider mock --like-floor 1
mcn collect report --run-id crun_xxxxxxxxxxxx
mcn collect match --run-id crun_xxxxxxxxxxxx
mcn material promote --material-id mat_xxxxxxxxxxxx --platform douyin
```

## IP Role Profile Maintenance

Formal collection and rewriting should start from a confirmed IP role profile. Low-level diagnostic commands can use drafts, but `mcn collect task keyword --role-id ...` requires `confirmation_status=confirmed`.

Create or update a complete role profile from JSON:

```json
{
  "name": "见心说",
  "positioning": "中年修心口播",
  "role_baseline": "温和克制的修心型老师",
  "life_stage": "50岁以上",
  "core_temperament": "稳定、克制、不表演",
  "speaking_posture": "像过来人慢慢提醒",
  "target_audience": {
    "life_stage": "中年",
    "pain_points": ["内耗", "执念"]
  },
  "search_keywords": ["修心", "内耗"],
  "fit_themes": ["修心", "放下执念"],
  "avoid_themes": ["暴富承诺"],
  "style_anchors": {
    "opening_style": "一句生活化判断开头",
    "ending_style": "克制收束，不强行动员"
  },
  "expression_constraints": {
    "allowed_intensity": "medium"
  },
  "forbidden_expressions": ["保证发财"],
  "typical_topics": ["人到中年要学会放下"]
}
```

Recommended command sequence:

```bash
mcn collect role upsert --file role.json --json
mcn collect role show --role-id role_xxxxxxxxxxxx
mcn collect role confirm --role-id role_xxxxxxxxxxxx --change-reason 首次确认
mcn collect role packet --role-id role_xxxxxxxxxxxx --json
mcn collect role export --file data/ip-roles-export.json --json
```

Status rules:

- `draft`: editable, not valid for formal high-level collection tasks.
- `agent_suggested`: imported or Codex-suggested profile waiting for confirmation.
- `confirmed`: valid for formal collection and later creation flows.
- `needs_reconfirm`: a key strategy field changed after confirmation; confirm again before formal use.

`source_role_id` on a material means the role that started collection. It is not the material's only suitable IP. Use `material_role_matches` to inspect all IP-role fit judgments.

## Handoff To Creation

Once a role profile is confirmed and material collection has produced accepted materials with material understanding, use the high-level creation workflow instead of directly copying transcripts into drafts.

```bash
mcn create task new \
  --role-id role_xxxxxxxxxxxx \
  --topic 财运 \
  --goal "生成一条知识型五段式口播" \
  --platform douyin \
  --target-count 3

mcn create task run --task-id createtask_xxxxxxxxxxxx --stage material_selection
mcn create task confirm --task-id createtask_xxxxxxxxxxxx --stage material_selection
mcn create task run --task-id createtask_xxxxxxxxxxxx --stage creation_brief
```

Creation tasks read `knowledge/creation/*.md` and `knowledge/ip/<role_slug>/*.md` as the long-term rewrite background. SQLite remains the fact and audit store; Markdown stores reusable creative experience, risk wording, and feedback learnings.

Use `mcn create knowledge packet --task-id ... --json` to inspect the exact context before a formal rewrite stage. By default, the packet uses promoted material understanding fields and does not include complete transcripts.

## High-Level Collection Tasks

Use `mcn collect task ...` for reusable collection work. Low-level commands remain available for diagnostics and one-off operations.

Keyword start:

```bash
mcn collect task keyword \
  --topic 财运 \
  --target-count 30 \
  --tool-provider mxnzp
```

The keyword task is complete only when the task has enough saved or reused materials, not when a single search finishes. It can search the seed topic, related keywords, role keywords, and `next_collection_keywords` discovered from saved materials. Existing materials are reused by `work_id > source_url > title+author` and are not overwritten.

Author start:

```bash
mcn collect task author \
  --name "娜说智慧" \
  --like-floor 10000
```

The default viral threshold is `10000` likes. Author tasks first expand the author with `user_post sortType=1`, then materialize every video that meets the viral threshold and duration window. Use `--materialize-top N` only when intentionally limiting the count. Use `--skip-expand` when the author videos are already in `douyin_author_videos`.

Database-discovered author start:

```bash
mcn collect task discover-authors \
  --min-appearances 2 \
  --like-floor 10000 \
  --top-authors 10
```

This reads `collected_materials`, `collection_candidates`, and `douyin_author_videos`, ranks source authors by appearances, max/average engagement, profile availability, and follower data, then reuses the author task flow for each top author. Use `--dry-run` to review the ranked author list without API calls.

Task review:

```bash
mcn collect task show --task-id ctask_xxxxxxxxxxxx
mcn collect task report --task-id ctask_xxxxxxxxxxxx
mcn collect task resume --task-id ctask_xxxxxxxxxxxx
```

Reports include saved materials, skipped candidates, discovered source authors, understanding provider/model/status, next recommended keywords/authors, and API call/cache counts. A collected material is not considered metadata-ready until material understanding has written the promoted columns and `material_understanding_json`.

## Real MXNZP Collection

Set credentials in `.env.local`:

```bash
MXNZP_APP_ID=...
MXNZP_APP_SECRET=...
DOUYIN_COOKIE=...
```

`DOUYIN_COOKIE` can be supplied manually or fetched in environments that already persist a Douyin login session:

```bash
mcn collect douyin-cookie --json
```

The command visits `https://www.douyin.com` and joins the returned cookies into `key=value; key2=value2` form. A very short cookie, such as only `__ac_nonce`, is treated as not logged in.

When a long logged-in cookie is required, use the browser login flow:

```bash
mcn collect douyin-login-cookie --write-env --json
```

This opens Chrome or Chromium with the project profile at `data/browser-profiles/douyin-cookie`. Log in to Douyin in that window. The CLI polls the browser session through Chrome DevTools, extracts Douyin cookies, and writes a valid cookie to `.env.local` when `--write-env` is set. Use `--show-cookie` only for local diagnostics because the full cookie is a secret.

`user_post` should only use a valid login cookie:

```bash
mcn collect mxnzp-call user_post \
  --params '{"userId":"<sec_uid>","sortType":1,"cursor":""}' \
  --json
```

For a one-shot call that guides login when no `DOUYIN_COOKIE` is configured:

```bash
mcn collect mxnzp-call user_post \
  --params '{"userId":"<sec_uid>","sortType":1,"cursor":""}' \
  --login-cookie \
  --json
```

If `--auto-cookie` reports that the cookie is too short, switch to `douyin-login-cookie` or `--login-cookie`. Do not use `--allow-short-auto-cookie` except for diagnostics.

Then run:

```bash
mcn collect run --topic 知识型口播 --target-count 1 --tool-provider mxnzp
```

Review the transcript, metrics, source link, understanding JSON, and skipped reasons before increasing the target count.

## Author Expansion

When a material performs well or looks reusable, collect the source author's profile before collecting more of their work.

For one material:

1. Read `collected_materials.source_url`.
2. Call MXNZP `detail` or `detail_v3/detail_v4` with the source URL.
3. Extract author identifiers from the detail response:
   - preferred: `raw.data.author.sec_uid`
   - fallback: `raw.data.author.short_id` / `raw.data.author.uid`
   - keep `raw.data.author.share_info.share_url` when present
4. Call `user_info` with the `sec_uid`.
5. Upsert the profile into `douyin_authors`.
6. Update the source material fields:
   - `author_sec_uid`
   - `author_profile_url`
   - `author_douyin_id`
   - `work_id`
7. Upsert the source work into `douyin_author_videos`.

To collect the author's posted works, call `user_post` with:

```bash
mcn collect mxnzp-call user_post \
  --params '{"userId":"<sec_uid>","sortType":1,"cursor":""}' \
  --json
```

`user_post` requires a valid logged-in `DOUYIN_COOKIE`. Without it, run `mcn collect douyin-login-cookie --write-env --json` first, or add `--login-cookie` to the `mxnzp-call` command. Keep the author profile and source work if login is not available yet, then mark the author as ready for expansion once a valid cookie is configured. Use `sortType=1` first when the goal is to find the author's high-performing material. Continue pagination with the returned cursor until either the target count is reached or no more high-potential videos appear.

The reusable author workflow is:

```bash
mcn collect author expand \
  --name "娜说智慧" \
  --sort-type 1 \
  --max-pages 0 \
  --like-floor 5000 \
  --top 50 \
  --json
```

This stores posted works in `douyin_author_videos` and ranks high-potential works by weighted engagement.

To turn ranked author works into formal collected materials, including `video_to_text_v2` transcript extraction and material understanding:

```bash
mcn collect author materialize \
  --name "娜说智慧" \
  --top 5 \
  --like-floor 5000 \
  --json
```

Existing collected materials with the same `work_id` are protected by default. `materialize` records them as `existing_preserved` and does not overwrite `material_understanding_json`, promoted understanding columns, `understanding_provider`, or `understanding_model`. Use `--duplicate-existing` only when a deliberate duplicate sample is needed. Use `--refresh-existing-understanding` only when intentionally replacing the previous understanding with the current configured provider/model.

For author-level爆款 expansion, rank `douyin_author_videos` with the same engagement score used in keyword search:

- likes
- saves / collects
- comments
- shares
- duration fit
- title/caption relevance to the target IP

## Search Prefilter

Every material collection run has a search-result prefilter before `video_to_text_v2`.
The purpose is to reduce downstream API usage, not to make the final material judgment.

The prefilter uses search-result metadata only:

- title / platform caption / author text for keyword and role relevance
- public metrics for heat and reuse potential
- duration for basic format fit
- current page quality and target material count for pagination decisions

Default duration window:

- reject videos shorter than 20 seconds
- reject videos longer than 300 seconds

These values are intentionally conservative and can be changed per run:

```bash
mcn collect run \
  --topic 财运 \
  --target-count 10 \
  --tool-provider mxnzp \
  --min-duration-seconds 20 \
  --max-duration-seconds 300
```

Pagination is Codex-owned in the workflow. The runner continues to the next page only when:

- MXNZP reports another page, and
- the latest page still contains promising candidates, and
- the accumulated candidate buffer has not already reached roughly 2x the target count.

This means a hot keyword can continue past the early pages when the current page still has strong videos.
It also means the search can stop early when enough good candidates already exist for the target collection count.

Public metrics are ranked by a weighted engagement score. Likes matter, but saves and shares carry extra weight because they better indicate reusable material value.

## Formal Material Eligibility Gate

Search prefiltering only decides whether a result is worth spending transcript API cost. It is not the final judgment.

After transcript extraction, the workflow runs `material-eligibility-v1` before inserting a reusable formal material or running material understanding. This gate protects the formal library from noisy short-video formats that may have traffic but cannot become knowledge-sharing oral-script drafts.

Formal reusable material must satisfy all of the following:

- has a non-empty transcript or caption long enough to support later understanding;
- has a clear knowledge core, viewpoint, explanation chain, judgment logic, or reusable list structure;
- fits oral-script collection rather than pure interaction, blessing, emotional prompting, plot, parenting, pet, or entertainment scenes;
- does not rely on concrete ritual actions such as pouring water, breathing toward the sun, chanting formulas, placing objects, or asking viewers to perform a luck ritual.

Common reject examples:

- `倒一杯自来水，吐三口气...`
- `玄学转运小妙招`
- `大晴天找个开阔地，迎着太阳深吸一口气`
- `爸爸带娃` / `养宠修行` / drama interaction clips
- missing transcript or transcript too short to judge

The gate writes:

- `eligibility_status`
- `reject_reason`
- `content_form`
- `knowledge_core_score`
- `oral_script_fit_score`
- `ip_fit_score`
- full `material_eligibility_json`

`collection_candidates` may keep rejected or broad results for audit. `collected_materials.status='collected'` is the reusable formal pool. Rows marked `eligibility_rejected`, `missing_transcript`, `topic_mismatch`, or `role_boundary_mismatch` should not be used for normal二创 unless explicitly reviewed and restored.

A single Buddhist-color term is not automatically rejected. If the script has a strong knowledge explanation chain, it can stay in the pool with `content_form='佛教色彩'`, and later IP matching or rewriting should decide whether to translate it into道家/国学 expression or reject it for a specific IP boundary.

## Material Understanding

Material understanding is a required part of collection, not a later optional cleanup step.

The default provider/model/status is:

- `understanding_provider = codex-agent`
- `understanding_model = gpt-5.5`
- `understanding_status = success`

This step creates the reusable metadata for later二创 retrieval and IP matching:

- `summary_text`
- `hook_text`
- `core_claim`
- `content_type`
- `oral_script_pattern`
- `audience`
- `emotion_trigger`
- `risk_level`
- `content_structure_json`
- `key_points_json`
- `rewrite_angles_json`
- `usable_quotes_json`
- `risk_notes_json`
- `recommended_platforms_json`
- `next_collection_keywords_json`
- full `material_understanding_json`

`local-rules/material-understanding-rules-v2` is only an explicit fallback for exceptional cases. It must remain `draft_local_understanding` and should be treated as not fully metadata-ready.

## Boundaries

- SQLite owns audit and state.
- MXNZP owns data acquisition only.
- No DeepSeek client, no React/FastAPI center, no confirmation-card system.
