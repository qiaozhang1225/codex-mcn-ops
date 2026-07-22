# Songli First-Round Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce 10 parent-facing Songli Psychology rewrite candidates through the complete creation, hook enhancement, risk cleanup, delivery, and Feishu document workflow.

**Architecture:** Use one confirmed source material per creation task. Curated copy is stored as a versioned batch manifest, imported into the existing SQLite creation ledger with one stage run per workflow stage, exported as a consolidated Markdown delivery, then appended to the existing Feishu document and read back for verification.

**Tech Stack:** Markdown, JSON, Python 3, Codex MCN Ops Store/creation workflow, SQLite, Lark/Feishu Docx

## Global Constraints

- Primary audience is parents of children aged 12–18; severe cases may extend to parents of children aged 18–25.
- Frontstage content starts from specific parent problems; family-of-origin, early trauma, and intergenerational patterns remain backstage explanations.
- Every script uses exactly one confirmed source material and remains traceable to its `material_id`.
- Every script passes `rewrite_draft` → `hook_enhancement` → `risk_cleanup` in that order.
- Risk cleanup removes medical certainty, guaranteed outcomes, fabricated authority, and direct course promises without softening necessary sharp judgments.
- The final Feishu write only appends content; it does not send the document or change sharing permissions.

---

### Task 1: Lock the IP-specific creation rules

**Files:**
- Create: `knowledge/ip/songlixinli/creation-playbook.md`
- Reference: `knowledge/ip/songlixinli/role-profile.json`
- Reference: `knowledge/creation/global-rewrite-playbook.md`
- Reference: `knowledge/creation/hook-playbook.md`
- Reference: `knowledge/creation/risk-cleanup-playbook.md`

**Interfaces:**
- Consumes: confirmed Songli role profile and global creation rules.
- Produces: role-specific rules loaded by `build_creation_context_packet()` as `ip_creation_playbook`.

- [ ] **Step 1: Write the role-specific playbook**

Write exact rules for parent perspective, content structure, sharpness target, family-mechanism placement, CTA boundary, and special handling for learning, phone, severe emotional issues, early relationships, and bullying.

- [ ] **Step 2: Verify playbook coverage**

Run:

```bash
rg -n "家长视角|家庭机制|开头|风险|手机|抑郁|早恋|欺凌|评论" knowledge/ip/songlixinli/creation-playbook.md
```

Expected: every required topic and boundary appears at least once.

### Task 2: Create 10 three-stage curated scripts

**Files:**
- Create: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Create: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Reference: `docs/superpowers/specs/2026-07-23-songli-first-round-rewrite-design.md`
- Reference: `data/mcn_ops.sqlite`

**Interfaces:**
- Consumes: the 10 exact `material_id` values and their transcripts from SQLite.
- Produces: a JSON array of 10 items with `material_id`, source metadata, topic, goal, `rewrite_draft`, `hook_enhancement`, `risk_cleanup`, and `publish_package`; plus a human-readable Markdown delivery.

- [ ] **Step 1: Draft each body from its single source**

For each item, preserve the source's retention mechanism and core value while changing the speaker to Songli's parent-facing expert posture. Target 380–480 Chinese characters when source depth supports it.

- [ ] **Step 2: Enhance only the opening**

Store both `rewrite_draft.body` and `hook_enhancement.body`. The hook-enhanced body must differ only in the opening block; the body logic and evidence remain stable.

- [ ] **Step 3: Clean risk expressions locally**

Store `risk_cleanup.body`, `replacements`, and `risk_notes`. Replacements must be exact local edits such as removing guaranteed recovery, single-case universal claims, class stigma, gender stigma, or blanket encouragement to fight back.

- [ ] **Step 4: Build publish packages**

Each item contains:

```json
{
  "cover_title_4": "四字封面",
  "video_title_18": "家长视角视频标题",
  "description": "视频描述",
  "pinned_comment": "公开评论互动问题",
  "final_copy": "与 risk_cleanup.body 完全一致"
}
```

- [ ] **Step 5: Render the consolidated Markdown**

For each of 10 numbered sections include the final title, theme, original source title, source URL, final script, and pinned comment. Do not expose internal prompts or workflow commentary in the final script.

### Task 3: Validate the creative batch before persistence

**Files:**
- Verify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Verify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`

**Interfaces:**
- Consumes: Task 2 artifacts.
- Produces: a clean validation report printed to the terminal.

- [ ] **Step 1: Run structural validation**

Run a read-only Python check that asserts:

```python
assert len(items) == 10
assert len({item["material_id"] for item in items}) == 10
assert all(item["publish_package"]["final_copy"] == item["risk_cleanup"]["body"] for item in items)
assert all(item["rewrite_draft"]["body"] != item["hook_enhancement"]["body"] for item in items)
```

Expected: `structure: PASS (10/10)`.

- [ ] **Step 2: Run role and risk validation**

Check every final body for a concrete parent problem, a child-needs/family-mechanism explanation, no hard private-message conversion, and none of these direct promises:

```python
blocked = ["一定治好", "彻底治愈", "保证有效", "听我的孩子都好了", "考不上高中就没有希望"]
```

Expected: `role_and_risk: PASS (10/10)`.

- [ ] **Step 3: Check duplicate language**

Compare normalized 20-character shingles across the 10 final bodies. Repeated source-independent body passages longer than 40 characters fail validation.

Expected: `duplicate_body: PASS`.

### Task 4: Persist the complete workflow in the SQLite ledger

**Files:**
- Modify runtime data: `data/mcn_ops.sqlite`
- Create exports: `runs/creation-deliveries/latest/<creation_task_id>-latest.md`

**Interfaces:**
- Consumes: validated JSON manifest from Task 3.
- Produces: 10 `creation_tasks`, one explicit material selection per task, confirmed stage runs, drafts, content packages, and delivery packages.

- [ ] **Step 1: Create idempotent tasks**

Use `create_creation_task()` with `role_id="role_967715c1f473"`, `platform="douyin"`, `target_count=1`, and then merge this context:

```python
{
    "batch_key": "songlixinli-first-round-20260723",
    "selected_material_id": item["material_id"],
    "curated_creation": True,
}
```

Before creating, query for the same `batch_key` and `selected_material_id`; reuse an existing task on rerun.

- [ ] **Step 2: Run and confirm source-dependent stages**

Call `run_creation_stage(..., "material_selection")`, confirm it, then run and confirm `creation_brief`. Assert the selected material equals the manifest `material_id`.

- [ ] **Step 3: Insert and confirm curated stages**

For `rewrite_draft`, `hook_enhancement`, and `risk_cleanup`, insert one `creation_stage_runs` row and one matching `creation_drafts` row using the manifest body, then mark the stage run confirmed. Each stage output records `creation_mode="curated_songli_round1"` and the upstream stage run ids.

- [ ] **Step 4: Insert publish and delivery packages**

Create the content package from `risk_cleanup.body`, insert the five-field publish package, mark `publish_format` confirmed, mark the task complete, insert and confirm `delivery`, and export the report to `runs/creation-deliveries/latest/<creation_task_id>-latest.md`.

- [ ] **Step 5: Verify ledger state**

Run a query asserting that this batch has 10 tasks, each has one selected material, all seven stage keys, a content package, and a delivery package.

Expected: `ledger: PASS tasks=10 stages=70 deliveries=10`.

### Task 5: Append and verify the Feishu document

**Files:**
- Read: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- External target: Feishu document `宋立心理 IP 账号诊断内容定位建议`

**Interfaces:**
- Consumes: final consolidated Markdown from Task 2 and verified ledger state from Task 4.
- Produces: a new appended document section titled `第一轮二创文案｜10 条备选`.

- [ ] **Step 1: Resolve the exact document**

Search the authenticated Feishu Drive for the exact document title and confirm one target document token. If multiple exact matches exist, select the one containing the existing account diagnosis report.

- [ ] **Step 2: Fetch and inspect the current ending**

Read the document before editing. If the heading `第一轮二创文案｜10 条备选` already exists, replace that section rather than appending a duplicate; otherwise append it at the end.

- [ ] **Step 3: Write the 10 final scripts**

Append the delivery content in numbered order 1–10. Do not include intermediate drafts, internal risk notes, database ids, or workflow status in the teacher-facing document.

- [ ] **Step 4: Read back and verify**

Fetch the updated document and assert the heading exists once, all 10 final titles exist, numbering is continuous, and the last final body is not truncated.

Expected: `feishu: PASS sections=10 heading_count=1`.

### Task 6: Final evidence review

**Files:**
- Verify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Verify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Verify: `data/mcn_ops.sqlite`

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: a concise user handoff with the local delivery link, Feishu link, 10 task ids, and validation results.

- [ ] **Step 1: Re-run all non-destructive validation checks**

Expected results:

```text
structure: PASS (10/10)
role_and_risk: PASS (10/10)
duplicate_body: PASS
ledger: PASS tasks=10 stages=70 deliveries=10
feishu: PASS sections=10 heading_count=1
```

- [ ] **Step 2: Report completion from evidence**

Return the two artifact links, Feishu document link, stage totals, and any residual editorial notes the user should consider during manual revision.
