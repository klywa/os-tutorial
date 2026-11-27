# 模板生成工作流局势组扩充实施计划

> **For agentic workers:** Use superpowers:dispatching-parallel-agents for independent editorial batches and verify the merged artifact in the workflow.

**目标**是从同一初始库和 Markdown 生成覆盖更多独立局势的 v4。

**设计**见 [局势组扩充设计](../specs/2026-11-27-template-scenario-discovery-design.md)。

- [x] 为已有基础组的引用和整库胜出、回退补回归检查。
- [x] 在知识识别和溯源中增加逐段覆盖，并让局势组引用已校验的基础组。
- [x] 按素材类型审编局势组，合并、核对依据和首次决策覆盖。
- [x] 用 v3 的初始库和本地配置生成 v4，按 v0.5 验收主库和溯源并对照 v3。

v4 共 139 组、834 条话术。相比 v3 新增 70 组，按实际核对的卡面限定为 S1。154 个原文段落均有记录，21 个细分组通过基础组回退测试。工作流和条件求值共 53 项测试通过。
