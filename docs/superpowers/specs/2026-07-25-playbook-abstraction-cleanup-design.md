# Playbook Abstraction Cleanup Design

## Goal

把 Codex MCN Ops 的创作 Playbook 从“案例驱动的固定写法”调整为“原则驱动的判断系统”。规则仍要能约束阶段边界、传播机制、IP 适配和风险，但不能把某一次成功修改固化成默认模板。

## Scope

- 全局创作 Playbook：选材、Brief、Rewrite、Hook、Risk Cleanup、Publish Format。
- IP 专属 Playbook：宋立心理两个运行路径、思成说。
- 运行时兜底：`src/mcn_ops/creation/workflow.py` 中的内置 Playbook。
- 相关测试与创作工作流说明。

## Abstraction Model

每条规则只属于以下三类之一：

1. **Hard boundary**：阶段职责、身份真实性、隐私、医疗或结果承诺等不可越过的边界。
2. **Decision principle**：说明需要判断什么、优先保护什么，以及发生冲突时如何取舍。
3. **Quality signal**：用于验收结果，但不规定必须使用哪种结构或句式。

以下内容不再放在核心 Playbook 中：

- 固定的多步正文模板。
- 单条文案形成的推荐句式。
- 把“案例、专家身份、自测、CTA”等组件规定为每条必备。
- 针对某一主题穷举所有动作。
- 同一原则在多个章节反复解释。

## Layering

- 全局层只定义跨 IP 通用的方法和阶段边界。
- IP 层只定义受众、角色、内容张力、专业解释范围和风险差异。
- 具体案例和单次人工反馈不升级为通用规则；只有可跨题材复用的判断原则才进入 Playbook。

## Songli Abstraction

从手机文案中沉淀的不是固定结构，而是三个原则：

- 反常识钩子引发反感时，先判断反感是否正是留人机制，不能因观众不舒服就自动降温。
- 主体需要处理钩子制造的核心异议，否则钩子与正文脱节。
- 对家长内容既不能回避方法问题，也不能把合理焦虑写成人格错误；解释与方案应回应行为背后的功能。

## Verification

- 两份宋立 Playbook 保持同一内容，避免路径漂移。
- 文件版与代码内置的 Global Rewrite Playbook 保持一致。
- 测试不再锁定具体案例句式，而是锁定抽象原则和阶段边界。
- 全量测试通过，且差异审查确认没有误改素材、数据库或非 Playbook 业务逻辑。
