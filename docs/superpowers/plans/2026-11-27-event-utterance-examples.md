# 按事件接入人工话术样例实施计划

> **For agentic workers:** Use superpowers:dispatching-parallel-agents for independent source review and verify the integrated export.

**目标**是让话术生成节点读取各事件文档中已核实的人工原句和条件。设计见 [按事件为话术生成加入人工样例](../specs/2026-11-27-event-utterance-examples-design.md)。

- [x] 按事件回查人工样例、适用条件和来源。记录资料不足的案例。
- [x] 增加确切事件匹配的样例导出和话术 prompt 注入。覆盖多事件、种子组和不同拍卖轮次。
- [x] 检查导出同步、溯源内容和现有工作流测试。

核实并导出 104 条人工原句，覆盖 24 个正式事件。25 份事件文档均有已核实样例区，其中对目标使用棋手技能和阵容成型后的提升方向暂无可纳入案例。42 项工作流测试通过。

按后续确认，工作流样例 JSON 由工作流独立维护，初始导出是一次性整理。校验使用工作流的事件定义和条件语法。
