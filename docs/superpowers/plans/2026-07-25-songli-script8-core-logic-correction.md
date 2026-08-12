# Songli Script 8 Core Logic Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正宋立心理第 8 条二创文案，使开头、案例解释和结论全部回到“抑郁的孩子在要求父母把自己重新养一遍”的原始内容任务。

**Architecture:** 以一份新的审计修订文件作为最新版本，再将同一发布包同步到首轮 JSON、Markdown、飞书 XML 和 SQLite 创作任务。飞书通过 block 级精准替换更新第 8 条，最后回读本地、数据库和飞书三端进行一致性校验。

**Tech Stack:** JSON、Markdown、XML、SQLite、lark-cli docs

## Global Constraints

- 保留原素材的核心命题，不以风险清理改写内容任务。
- 最终口播正文不计空白字符为 380–480 字。
- 只修改第 8 条及其对应任务版本，不改其他文案。
- 飞书编辑使用用户身份和 block 级精准替换。

---

### Task 1: 固化并同步最新文案

**Files:**
- Create: `runs/creation-deliveries/songlixinli-script8-revision-v2-20260725.json`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.feishu.xml`

**Interfaces:**
- Consumes: `mat_62ba1fb58510` 的原始命题和案例画面。
- Produces: 统一的 `rewrite_draft`、`hook_enhancement`、`risk_cleanup` 和 `publish_package`。

- [ ] **Step 1: 写入新的审计修订文件**

使用 `apply_patch` 新建 v2 修订文件，正文以“把他当成一个小孩，再重新养一遍”为开头结论。

- [ ] **Step 2: 同步首轮交付的三种格式**

使用 `apply_patch` 将第 8 条 JSON、Markdown 和 XML 替换成同一发布包。

- [ ] **Step 3: 校验字数和旧错误表达**

Run:

```bash
rg -n '不是把他当婴儿重新养一遍|别再把那些像懒' runs/creation-deliveries/songlixinli-script8-revision-v2-20260725.json runs/creation-deliveries/songlixinli-first-round-20260723.{json,md,feishu.xml}
```

Expected: 无输出。

### Task 2: 更新 SQLite 创作任务

**Files:**
- Modify: `data/mcn_ops.sqlite`
- Create: `data/backups/mcn_ops-before-songli-script8-v2-20260725.sqlite`
- Modify: `runs/creation-deliveries/latest/createtask_24e1c96cd7c3-latest.md`

**Interfaces:**
- Consumes: Task 1 的统一发布包。
- Produces: 新的 rewrite、hook、risk、publish 和 delivery 阶段版本，以及最新任务导出。

- [ ] **Step 1: 备份数据库**

Run:

```bash
cp data/mcn_ops.sqlite data/backups/mcn_ops-before-songli-script8-v2-20260725.sqlite
```

Expected: 备份文件存在且大小大于 0。

- [ ] **Step 2: 写入新版本并更新当前任务指针**

复用仓库现有 SQLite 数据结构，新增 `songli_script8_core_logic_correction_20260725` 版本，不覆盖历史版本。

- [ ] **Step 3: 导出并查询最新任务**

Expected: 最新主题、开头和正文均包含“重新养一遍”，阶段版本号各增加 1。

### Task 3: 精准替换飞书第 8 条

**Files:**
- Modify: Feishu doc `Ie4AdE3KrosC1kxt6X6cS7XVnVg`

**Interfaces:**
- Consumes: Task 1 的 XML 段落。
- Produces: 老师可见的第 8 条最新版本。

- [ ] **Step 1: 局部获取第 8 条最新 block ID**

Run:

```bash
lark-cli docs +fetch --doc Ie4AdE3KrosC1kxt6X6cS7XVnVg --scope keyword --keyword "抑郁的孩子" --context-before 1 --context-after 12 --detail full --as user
```

Expected: 返回第 8 条标题、正文、封面标题、描述和置顶评论的 block ID。

- [ ] **Step 2: 逐 block 精准替换**

使用 `docs +update --command block_replace` 替换第 8 条标题、五段正文和发布信息；每次替换后不复用失效的目标 block ID。

- [ ] **Step 3: 回读第 8 条和第 9 条边界**

Expected: 第 8 条为最新版本，第 9 条标题和内容仍在原位置且未被修改。

### Task 4: 完整验收

**Files:**
- Verify: all Task 1–3 outputs

**Interfaces:**
- Consumes: 本地文件、SQLite 和飞书当前版本。
- Produces: 可向用户交付的验证结果。

- [ ] **Step 1: 运行 JSON、XML 和数据库一致性检查**

Expected: 所有格式可解析，正文一致，字数合规，旧错误表达不存在。

- [ ] **Step 2: 回读飞书文档**

Expected: 开头、主体、结尾都正面解释“重新养一遍”，专业边界未取代内容主题。

- [ ] **Step 3: 检查工作区差异**

Run:

```bash
git diff --check
git status --short
```

Expected: 无空白错误；只报告本次文件和用户已有改动。
