# Playbook Abstraction Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将创作 Playbook 清理为原则、边界和质量信号，删除会让后续创作机械套模板的案例级规则。

**Architecture:** 以 `knowledge/creation/` 为全局方法源，以 `knowledge/ip/<slug>/creation-playbook.md` 为 IP 差异源；`workflow.py` 只保留与文件版一致的紧凑兜底。测试锁定层级边界和一致性，不锁定具体示例句。

**Tech Stack:** Markdown, Python 3, pytest.

## Global Constraints

- 不修改素材库、创作数据库和已有飞书文档。
- 不删除阶段边界、身份真实性、隐私、医疗和结果承诺规则。
- 不把现有成功案例替换成另一套固定模板。
- 保留用户已确认的钩子保真、内容任务保真和风险局部处理原则。

---

### Task 1: Compact global Playbooks

**Files:**
- Modify: `knowledge/creation/global-rewrite-playbook.md`
- Modify: `knowledge/creation/material-selection-playbook.md`
- Modify: `knowledge/creation/hook-playbook.md`

**Interfaces:**
- Consumes: creation context packet and stage contracts.
- Produces: principle-based instructions for `material_selection`, `rewrite_draft`, and `hook_enhancement`.

- [x] Remove repeated explanations, fixed CTA matrices, preferred sentences, and source-type recipes.
- [x] Preserve content-task fidelity, mechanism fidelity, speaker compatibility, stage boundaries, oral integrity, and logic alignment.
- [x] Keep length as a guardrail and reselection as an upstream decision.

### Task 2: Compact IP Playbooks

**Files:**
- Modify: `knowledge/ip/songlixinli/creation-playbook.md`
- Modify: `knowledge/ip/宋立心理/creation-playbook.md`
- Modify: `knowledge/ip/sichengshuo/creation-playbook.md`

**Interfaces:**
- Consumes: global rewrite principles.
- Produces: only role-specific audience, tension, authority, topic, and safety differences.

- [x] Replace Songli fixed chains and topic manuals with audience, objection handling, psychological-function explanation, and solution-alignment principles.
- [x] Keep both Songli files byte-equivalent.
- [x] Replace Sicheng CTA recipes and concrete examples with role-level conversion principles.

### Task 3: Align runtime fallbacks and tests

**Files:**
- Modify: `src/mcn_ops/creation/workflow.py`
- Modify: `tests/test_creation.py`
- Modify: `workflows/create_script.md`

**Interfaces:**
- Consumes: compact file Playbooks.
- Produces: matching fallback Playbooks and regression checks.

- [x] Replace `DEFAULT_GLOBAL_REWRITE_PLAYBOOK` with the compact file-equivalent content.
- [x] Simplify generated hook and IP fallback text.
- [x] Replace phrase-heavy tests with abstraction, consistency, and anti-template assertions.
- [x] Correct outdated workflow wording that treats a specific character floor as a universal target.

### Task 4: Verify

**Files:**
- Test: `tests/test_creation.py`
- Test: full test suite.

**Interfaces:**
- Consumes: all modified Playbooks and runtime fallbacks.
- Produces: evidence that the workflow still loads correct knowledge and enforces stage contracts.

- [x] Run `PYTHONPATH=src pytest tests/test_creation.py -q`.
- [x] Run `PYTHONPATH=src pytest -q`.
- [x] Compare the two Songli Playbooks and the file/runtime Global Rewrite Playbooks.
- [x] Review `git diff --check` and the scoped diff for accidental changes.
