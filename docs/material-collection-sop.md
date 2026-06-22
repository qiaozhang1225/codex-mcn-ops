# Material Collection SOP

## Purpose

Collect reusable short-video material for IP creation while keeping the system CLI-first and auditable.

## Commands

```bash
mcn collect role upsert --name "知识型老师" --search-keyword 知识型口播
mcn collect run --topic 知识型口播 --target-count 1 --tool-provider mock --like-floor 1
mcn collect report --run-id crun_xxxxxxxxxxxx
mcn collect match --run-id crun_xxxxxxxxxxxx
mcn material promote --material-id mat_xxxxxxxxxxxx --platform douyin
```

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

## Boundaries

- Codex/GPT-5.5 owns understanding and matching.
- SQLite owns audit and state.
- MXNZP owns data acquisition only.
- No DeepSeek client, no React/FastAPI center, no confirmation-card system.
