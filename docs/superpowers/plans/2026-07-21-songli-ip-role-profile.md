# Songli IP Role Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create, load, confirm, and verify the first version of the `宋立心理` IP role profile in Codex MCN Ops.

**Architecture:** Keep the complete editable profile in `knowledge/ip/songlixinli/role-profile.json`, then load it through the existing `mcn collect role` workflow into the local SQLite audit ledger. Confirm the role only after the stored profile and generated persona packet match the approved positioning.

**Tech Stack:** JSON, Codex MCN Ops CLI, Python 3, SQLite

## Global Constraints

- Primary audience: parents of children aged 12-18; families with unresolved severe problems aged 18-25 are the secondary extension audience.
- Primary goal: grow a precise parent audience and increase perceived professional value; direct Douyin conversion is out of scope.
- Frontstage positioning: `看懂青春期孩子，也理解焦虑父母的家庭心理老师`.
- Family-of-origin theory stays backstage as an explanatory method, not the dominant public label.
- Sharpness targets wrong assumptions and ineffective methods, not parents as people.
- Future rewrite evidence may revise the profile; every strategic change must trigger version review and reconfirmation.

---

### Task 1: Create and Register the Role Profile

**Files:**
- Create: `knowledge/ip/songlixinli/role-profile.json`
- Verify: `data/mcn_ops.sqlite`

**Interfaces:**
- Consumes: approved positioning, target-audience hierarchy, content ratio, product-value context, and expression boundaries.
- Produces: one confirmed `ip_roles` record plus a generated persona packet for later collection and creation workflows.

- [ ] **Step 1: Create the complete JSON profile**

Write every supported IP-role field, including `target_audience`, `theme_map`, `source_evidence`, and `agent_suggestions`. Set the source status to `agent_suggested` so the CLI confirmation remains an explicit second step.

- [ ] **Step 2: Validate JSON syntax**

Run:

```bash
python3 -m json.tool knowledge/ip/songlixinli/role-profile.json >/dev/null
```

Expected: exit code `0` and no output.

- [ ] **Step 3: Load the role through the existing CLI**

Run:

```bash
PYTHONPATH=src python3 -m mcn_ops.cli collect role upsert \
  --file knowledge/ip/songlixinli/role-profile.json \
  --json
```

Expected: one enabled role named `宋立心理` with `confirmation_status=agent_suggested`.

- [ ] **Step 4: Inspect the generated persona packet**

Run:

```bash
PYTHONPATH=src python3 -m mcn_ops.cli collect role packet --name 宋立心理 --json
```

Expected: the packet contains the approved frontstage positioning, primary audience ages `12-18`, backstage family-of-origin method, content ratios, and expression boundaries.

- [ ] **Step 5: Confirm the approved role**

Run:

```bash
PYTHONPATH=src python3 -m mcn_ops.cli collect role confirm \
  --name 宋立心理 \
  --change-reason 'User approved initial IP role profile after account-copy analysis' \
  --json
```

Expected: `confirmation_status=confirmed`, `needs_reconfirm=false`, and `profile_version=1`.

- [ ] **Step 6: Verify persisted fields**

Run:

```bash
PYTHONPATH=src python3 -m mcn_ops.cli collect role show --name 宋立心理 --json
```

Expected: all role fields round-trip without missing lists or JSON objects.

- [ ] **Step 7: Commit only the role source and implementation plan**

Run:

```bash
git add docs/superpowers/plans/2026-07-21-songli-ip-role-profile.md knowledge/ip/songlixinli/role-profile.json
git commit -m "feat: add Songli psychology IP role profile"
```

Expected: a commit containing only the two new files; unrelated working-tree changes remain unstaged.
