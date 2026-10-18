# 阵容主要变阵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** 让skill与现有四篇阵容以证据区分主要变阵、节奏及工具位，并共享结构化阅读。
**Architecture:** schema4新增major_variants，引用现有claims/late_variants/routes；统一阅读投影，保留成员及适配的唯一来源。
**Tech Stack:** Python统一知识事务，React/TypeScript现有编辑器与Markdown。
**Spec:** 用户2026-10-18批准的《阵容笔记“主要变阵”与技能规范升级》完整五节方案。

## Global Constraints
仅核查本地已有有效转写及画面，不新搜索下载；不改动三篇非阵容笔记；人工保护、原ID/证据/历史及已排除打法保留；下载/ASR/主题队列继续。常小娥以共同成长机制为基准。统计组合不自动成为攻略。

## Review Focus
人工清空引用、共享引用重复、路线与组合错误笛卡尔适配、旧schema持久化、未经证据把对策写成变阵。

### Task 1: 数据契约与事务
- [x] RED：新增test_major_variants.py验证六维证据、悬空引用、重映射/删除保护及schema4。
- [x] GREEN：major_variants.py负责校验/引用/渲染；tactics/workspace接入与schema4持久化；实体扫描沿claims及原成员引用。
- [x] 运行专项与既有回归。

### Task 2: 阅读与编辑
- [x] RED：四篇统一阅读、每条结论一次、章节空状态与同源导出测试。
- [x] GREEN：lineup_layout/wxq共享投影；React MajorVariantsEditor与类型；删除组合/路线先解除引用；网站相似组合改名。
- [x] 前端测试和生产构建。

### Task 3: 四篇内容与技能
- [x] 检查原claims/相关有效文字稿，记录分类与证据位置；常小娥按机制合并实质分支，不照抄14组合。
- [x] 用统一persist保存四篇meta/历史，更新重放输入，保护人工内容，不伪造依据。
- [x] skill入口/契约/组织/覆盖/验收更新；skill格式与知识validate。

### Task 4: 验收交付
- [x] Python/前端全回归、构建；隔离编辑桌面/420px，正式只读页面与HTML检查。
- [x] 一次fresh-context最终代码审查，Important修复RED→GREEN；交付分类与待确认报告，保留功能分支，不自动commit/push。
