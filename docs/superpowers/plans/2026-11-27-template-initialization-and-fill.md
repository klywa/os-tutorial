# 万象棋模板库初始化与补全实施计划

> **For agentic workers:** Use superpowers:dispatching-parallel-agents for independent changes and verify integration before publication.

**目标**是从阵容资料生成空库，并从指定 Markdown 同时补全空组和发现新组。

**架构**沿用 Python 工作流、正式事件注册表和主库与溯源的配对发布。空组走独立分支，新增组沿用现有发现流程。

**设计**见 [模板库设计](../specs/2026-11-27-template-initialization-and-fill-design.md)。

- [x] 在 `workflow/template_generation/initialize.py` 实现资料归一和确定性建组，新增项目 skill。先验证指定 JSON 的成员、轮次、固定条件与具名指令，再覆盖 Markdown 和阵容表入口。
- [x] 在工作流运行器增加已有库快照、补全分支、合并与溯源。先用测试覆盖空组补全、已有组保留和重复新增阻止，再运行现有工作流测试。
- [x] 在成品文件读写链路保留 `instruction`。验证新库和缺省字段的旧库可读，保留将空库作为工作流输入的边界。
- [x] 用指定知识 JSON 写入初始库，再用指定个人 Markdown 和初始库生成 v3。逐组校对结构、话术和溯源，并检查新组存在。

自动审批拦截了通过 CLI 发送个人笔记的运行。样例使用本地审编回复通过同一工作流的节点检查和发布，回放核对主库一致。结果包含 64 个补全组和 5 个新增组，共 414 条话术。
