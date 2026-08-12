# Songli Script 10 Strong-Attitude Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复第 10 条原素材“受到欺负要反击”的强传播态度，并用最小主体修改补充自我保护与后续处理边界。

**Architecture:** 保留现有素材和创作任务，在独立审计文件中重做 rewrite、hook、risk、publish 四阶段，再同步更新首轮本地交付、SQLite 当前交付和飞书第 10 条。Playbook 只沉淀抽象规则，不把本案例写成固定模板。

**Tech Stack:** Markdown、JSON、SQLite、lark-cli docs、Codex MCN Ops creation workflow

## Global Constraints

- 唯一底稿为 `mat_3224eca9691b`。
- 最终正文 380—480 字。
- 开头保留“一定要打回去”和“气势不能输”的强态度。
- 风险清理通过解释和条件边界完成，不得删除传播机制。
- 不得触碰飞书第 9 条用户手动修改后的内容。

---

### Task 1: 三阶段重写与发布包

**Files:**
- Create: `runs/creation-deliveries/songlixinli-script10-strong-attitude-20260725.json`
- Modify: `data/mcn_ops.sqlite`
- Modify: `runs/creation-deliveries/latest/createtask_263156956957-latest.md`

**Interfaces:**
- Consumes: `mat_3224eca9691b` 原始转写与现有任务 `createtask_263156956957`。
- Produces: 忠于原素材强态度的 rewrite、hook、risk、publish 阶段终稿。

- [x] 写入保留原立场和原逻辑的 rewrite draft。
- [x] 在 hook 阶段确认强态度开头，不另造传播机制。
- [x] 在 risk 阶段只补充自卫含义、危险场景脱离和成年人介入边界。
- [x] 生成封面、标题、描述、置顶评论与最终正文。
- [x] 更新现有创作任务的阶段版本和当前发布包。

### Task 2: Playbook 沉淀

**Files:**
- Modify: `knowledge/creation/global-rewrite-playbook.md`
- Modify: `knowledge/creation/risk-cleanup-playbook.md`
- Modify: `knowledge/ip/songlixinli/creation-playbook.md`
- Modify: `knowledge/ip/宋立心理/creation-playbook.md`
- Modify: `src/mcn_ops/creation/workflow.py`

**Interfaces:**
- Consumes: 第 10 条失败原因与修正边界。
- Produces: “风险表达同时是传播机制时优先限定而非整体替换”的抽象规则。

- [x] 在全局二创规则中补充强立场保留原则。
- [x] 在风险清理规则中补充最小跨度替换和上下文限定原则。
- [x] 在宋立专属规则中补充承接家长保护欲的表达边界。
- [x] 同步运行时默认 Playbook，保持文件与常量一致。

### Task 3: 本地与飞书替换

**Files:**
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.feishu.xml`
- Modify: Feishu doc `Ie4AdE3KrosC1kxt6X6cS7XVnVg`

**Interfaces:**
- Consumes: Task 1 的最终发布包。
- Produces: 新第 10 条当前交付。

- [x] 只替换本地第 10 条的阶段稿和发布包。
- [x] 读取飞书第 10 条最新 block ID 并精准替换。
- [x] 回读第 9、10 条，确认第 9 条未改。

### Task 4: 验收

**Files:**
- Verify: Tasks 1–3 outputs

**Interfaces:**
- Consumes: 本地交付、SQLite、飞书和 Playbook。
- Produces: 长度、追溯、一致性和测试证据。

- [x] 比较本地、SQLite 与飞书最终正文。
- [x] 验证强态度开头仍在，安全边界位于主体。
- [x] 运行 JSON/XML 解析、SQLite integrity check、`git diff --check` 和完整测试。
