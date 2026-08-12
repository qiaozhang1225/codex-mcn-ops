# Songli Script 8 Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写宋立心理第 8 条抑郁主题文案，恢复抑郁钩子和女孩自述转案例的传播机制，并同步本地记录、数据库与飞书文档。

**Architecture:** 以正式素材转写为唯一内容源，以宋立心理 Playbook 约束受众、说话者兼容和专业边界。完成文案后，以新版本记录更新创作账本，并对飞书第 8 条做局部替换和回读。

**Tech Stack:** Markdown, JSON, SQLite, lark-cli Docx.

## Global Constraints

- 首句直接点名抑郁，并保留“逼爸妈做一件事”的悬念机制。
- 将 16 岁女孩自述转为宋立老师讲述的案例，不冒充当事人。
- 保留锁门、少吃、打游戏、休学和自伤等高识别度画面。
- 不写成抑郁的唯一病因、诊断结论或康复保证。
- 出现自伤或自杀风险时保留专业评估和现实危机支持边界。
- 只替换飞书第 8 条，不修改其他文案。

---

### Task 1: Rewrite and validate the publish package

**Files:**
- Create: `runs/creation-deliveries/songlixinli-script8-revision-20260725.json`

- [x] 核对正式素材转写、宋立心理 Playbook 和权威医学边界。
- [x] 生成正文、封面标题、视频标题、描述和置顶评论。
- [x] 检查钩子、案例转译、口播顺畅度、字符数和风险表达。

### Task 2: Synchronize local records and ledger

**Files:**
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.json`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.md`
- Modify: `runs/creation-deliveries/songlixinli-first-round-20260723.feishu.xml`
- Modify runtime data: `data/mcn_ops.sqlite`

- [x] 用新版本替换三个交付文件中的第 8 条。
- [x] 为原创作任务写入新的阶段版本和发布包装。
- [x] 回读数据库，确认第 8 条的最终正文与新版本一致。

### Task 3: Replace and verify the Feishu section

**External target:** `宋立心理 IP 账号诊断与内容定位建议（第一版）`

- [x] 只替换第 8 条标题、正文和发布包装 block。
- [x] 回读第 8 条，确认新钩子、案例、标题和边界完整存在。
- [x] 确认第 7 条和第 9 条标题仍在，证明替换范围没有越界。
