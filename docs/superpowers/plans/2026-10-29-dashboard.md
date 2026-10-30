# 看板 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in the current session. The user approved the full design and requested implementation.

**Goal:** 新增实时汇总笔记数量、七维覆盖率和逐篇覆盖矩阵的看板。

**Architecture:** Python 从正式 JSON 索引及正文生成一致的只读统计；React 独立看板组件以三秒轮询更新，复用现有笔记导航。

**Tech Stack:** Existing Python HTTP server, React 19, TypeScript, Vitest; no new dependencies.

**Spec:** 用户于2026-10-29批准的《新增“看板”Tab》方案。

## Global Constraints
- 七维：运营节奏、英雄、拍卖、关键装备、推荐天赋、克制本阵容、关键操作。
- 当前正文至少一条实质内容即覆盖；纯标题、占位、链接及内部支撑材料不计。
- 默认覆盖率升序，同分中文标题排序；百分比一位小数，空库显示“—”。
- 可见时3秒刷新、聚焦和保存刷新、隐藏暂停、手动刷新；失败保留旧结果。
- 不修改知识，不新增依赖，不提交Git。保留工作区已有改动。

## Review Focus
- 具名占位句、混合正文、否定行动建议不能被关键词误判。
- 一份响应内数量与矩阵一致，文件异常不能当成未覆盖。
- 旧章节与分支章节映射，制敌不能算克制本阵容。
- 跳转需要等异步正文加载完成，且保护未保存修改。
- 隐藏页面停轮询，失败或过期请求不能覆盖最新快照。

## Task 1: 只读聚合与接口
Files: `frontend/dashboard.py`, `frontend/test_dashboard.py`, `frontend/server.py`.
Interface: `dashboard.snapshot(root) -> {revision, generated_at, counts, summary, fields, notes}`；字段覆盖带 `covered, section, node_id`。
- [x] 先写正文覆盖、公式、索引新增删除、文件异常和快照变化测试，运行确认失败。
- [x] 实现正文标题映射、占位规则、文件签名缓存和一致快照重试，接入 GET /api/dashboard。
- [x] 运行后端测试，确认通过。

## Task 2: 看板视图与刷新
Files: `frontend/src/Dashboard.tsx`, `dashboardModel.ts`, `dashboard.css`, `dashboard.test.tsx`, `main.tsx`.
- [x] 先写排序、空状态、矩阵和刷新调度测试，确认失败。
- [x] 实现顶部统计、七项条形统计、可排序矩阵；复用深蓝/玉绿/金色，无新增装饰渐变。
- [x] 增加顶级导航、延迟章节定位及保存后失效通知，保留未保存保护。
- [x] 前端测试及构建通过。

## Task 3: 验收交付
- [x] 运行相关前后端回归，检查正式知识哈希未变化。
- [x] 独立整体审查并处理重要问题。
- [x] 实际运行服务验收1440px/420px、导航、刷新与失败保留；不写入正式知识。
- [x] 更新计划与交付报告，不提交Git。
