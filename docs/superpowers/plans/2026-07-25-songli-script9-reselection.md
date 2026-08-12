# Songli Script 9 Reselection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用《不要和孩子说别早恋》替换宋立心理第一轮第 9 条的薄素材，并完成可追溯的低重构二创交付。

**Architecture:** 将成功搜索与转写结果写入正式素材库，更新三层 Playbook 后，用独立创作任务承载新素材的完整阶段链。最后只替换首轮交付和飞书第 9 条，保留旧任务作为历史记录。

**Tech Stack:** Markdown、JSON、SQLite、lark-cli docs、Codex MCN Ops creation workflow

## Global Constraints

- 唯一底稿为 `https://www.iesdouyin.com/share/video/7375460075906878735`。
- 最终正文 380—480 字。
- 原开头与内容任务只做最小必要转换。
- 不使用外部原创补足篇幅。
- 不覆盖原第 9 条历史素材和历史创作任务。

---

### Task 1: 素材入库与 Playbook 沉淀

**Files:**
- Create: `runs/collection-reports/songli-script9-reselection-source-20260725.json`
- Modify: `data/mcn_ops.sqlite`
- Modify: `knowledge/creation/material-selection-playbook.md`
- Modify: `knowledge/creation/global-rewrite-playbook.md`
- Modify: `knowledge/ip/songlixinli/creation-playbook.md`
- Modify: `knowledge/ip/宋立心理/creation-playbook.md`

**Interfaces:**
- Consumes: MXNZP 搜索结果与完整转写。
- Produces: 唯一新 `material_id` 和三层一致的低重构规则。

- [x] 写入带真实数据、原文转写与选择分析的来源审计文件。
- [x] 将新素材、候选记录和人工补录采集记录写入 SQLite。
- [x] 将薄素材降级、厚度门槛和低原创度阶段规则写入三层 Playbook。
- [x] 校验素材链接唯一、转写长度大于 900 字、Playbook 不互相矛盾。

### Task 2: 完整二创阶段链

**Files:**
- Create: `runs/creation-deliveries/songlixinli-script9-reselection-20260725.json`
- Modify: `data/mcn_ops.sqlite`
- Create: `runs/creation-deliveries/latest/<new-task-id>-latest.md`

**Interfaces:**
- Consumes: Task 1 的新 `material_id`。
- Produces: rewrite、hook、risk、publish、delivery 五阶段终稿。

- [x] 生成忠于原素材的 380—480 字 rewrite draft。
- [x] 只对开头做最小增强，保留原冲突。
- [x] 局部替换风险表达，不改变主体逻辑。
- [x] 生成封面、视频标题、描述、置顶评论和最终正文。
- [x] 写入独立创作任务并导出最新审计 Markdown。

### Task 3: 替换第 9 条交付

**Files:**
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.feishu.xml`
- Modify: Feishu doc `Ie4AdE3KrosC1kxt6X6cS7XVnVg`

**Interfaces:**
- Consumes: Task 2 的发布包。
- Produces: 新第 9 条当前交付。

- [x] 用新素材信息和发布包替换本地第 9 条。
- [x] 获取飞书第 9 条最新 block ID，精准替换标题、素材链接、正文和发布信息。
- [x] 回读第 8、9、10 条边界，确认相邻内容未改。

### Task 4: 验收

**Files:**
- Verify: Tasks 1–3 outputs

**Interfaces:**
- Consumes: 素材库、创作任务、本地交付和飞书。
- Produces: 完整验证证据。

- [x] 比较本地发布包、数据库最新阶段与飞书正文。
- [x] 验证正文长度、旧素材链接消失、新素材链接存在。
- [x] 运行 SQLite integrity check、JSON/XML 解析、`git diff --check` 和项目测试。
