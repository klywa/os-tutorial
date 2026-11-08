# Speech Template Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkboxes.

**Goal:** 实现已批准的话术模板库并发布到现有外网站点。
**Architecture:** 独立模板领域，复用身份、锁、持久化提案及Git发布基础设施。前端与后台通过统一changes契约集成。
**Tech Stack:** React19, TypeScript, Vite, Python stdlib, SQLite.
**Spec:** docs/superpowers/specs/2026-11-07-speech-template-library-design.md

## Global Constraints
- 不覆盖已有工作，不提交私有raw/凭据；保持笔记API兼容；不增加依赖。
- 模板正式写入使用revision和事务；同条件组AND、话术等概率；不实现游戏运行时。
- API统一 `/api/templates`。snapshot={schema_version,events,groups,revision}，change={kind:event|group,action:put|delete,id,value?}。

## Review Focus
- 过期导入/审批/确认必须保留草稿并拒绝覆盖。
- 修改定义不得留下无效条件或占位符。
- viewer和其他作者不能读写私有提案。
- 双端删改冲突不可覆盖网站展示版。
- 实体抓取失败或仅图片时间变化不产生误报。

## Tasks
### 1. 领域模型、事务、JSON与预警
- [x] 新增frontend/templates_schema.py、templates_store.py和test_templates.py；先写并运行失败测试。
- [x] snapshot(root), apply(root,revision,changes,actor), export_library(root,group_ids=None), preview_import(root,document)；实体引用/参数依赖/占位符严格验证。
- [x] 独立持久记录、审计与墓碑，崩溃恢复；实体语义快照与有版本确认。
- [x] Python单测覆盖往返/失败原子性/幂等/并发/预警。
### 2. HTTP、角色和提案
- [x] 新增frontend/templates_http.py、templates_proposals.py及HTTP角色测试；接入server.py和website_server.py。
- [x] GET根、export、warnings、proposals；POST changes、import/preview、import/commit、warnings/seen、warnings/confirm、proposals/ID/approve|reject|withdraw。
- [x] 编写员changes/import转私有提案，管理员审批或正式写；同步通知、锁及错误状态沿用现有机制。
### 3. 模板库前端
- [x] 新增templates.ts类型/筛选测试，TemplateLibrary/TemplateEditor/TemplateSettings及CSS；接入main.tsx。
- [x] 事件侧栏、三类筛选、条件卡牌/话术编辑、定义维护、导入预览/导出、审批差异及登录预警。
- [x] Vitest、构建及桌面/手机浏览器交互验收。
### 4. 三方同步及部署
- [x] 新增templates_sync.py及隔离Git合并测试；接入knowledge_git.py及现有发布白名单、正式快照、回滚和验证。
- [x] 同ID条件话术独立合并，冲突持久化/记录级锁/管理员解决，网站当前版保留。
- [x] 验证全体相关Python/前端回归、隔离双端演练，更新文档。
### 5. 审阅与发布
- [x] 独立审阅并修复，记录实际验证。
- [ ] 用现有publish-local.ps1/Actions部署，核验线上包含提交、服务及已登录模板API。

## Execution rulings
- 用户已明确批准并要求实施，直接执行不重复请求方案许可。
- 使用当前checkout保留已有改动，在codex/speech-template-library分支工作；用户授权发布时按既有master流程集成。
- 领域、UI、同步可在明确接口和文件所有权下并行；父代理拥有HTTP/提案及最终集成。
