# Knowledge Sync Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development with sequential implementers and a final independent review.

**Goal:** 双端安全合并、网页逐段冲突处理、当前meta不再携带全量旧正文。
**Architecture:** schema6正文不变；显式storage_version=2启用外置不可变历史；纯三方合并器生成待合并请求，Git集成与管理员网页共用事件存储；服务器实际展示快照固定冲突笔记。
**Tech Stack:** Python stdlib、Git、React/TypeScript、unittest/Vitest。
**Spec:** docs/superpowers/specs/2026-11-03-knowledge-sync-design.md

## Global Constraints
- 当前干净检出使用codex/knowledge-sync分支；未验收不推master，不自动迁移当前知识。
- 正文schema6、稳定ID、人工保护、来源、历史不丢失；raw/账号/私有提案不入Git。
- 兼容代码先部署两端，再备份迁移；现有Actions/timer/回滚保留。
- 新流程只锁冲突笔记，不长期持锁等待网络；同步重试与解决操作均幂等。

## Review Focus
- 服务器当前展示版与远端Git不同：以实际运行快照固定，激活前再次检查。
- 第三个版本或旧请求重试：追加且去重，过期裁决409，不复活已解决输入。
- 相同正文不同证据：按稳定ID保留证据，人工保护不削弱。
- 新增/删除/排序和新建身份碰撞：完整保留两端，转可读冲突。
- 断点事务/历史迁移/跨release：同批恢复，旧ID映射，状态不绑定失效目录。

## Task 1 — 历史兼容与迁移
- [ ] RED：外置历史后meta不嵌套旧正文、重试幂等、历史/证据/旧版本ID可回读。
- [ ] 实现scripts/knowledge_history.py；修改json_store.py、note_review.py；新增迁移脚本及测试。
- [ ] storage_version=2仅显式迁移启用，旧根目录正常读写；交易先写不可变历史再正文/附件/索引，revision不依赖历史累计。
- [ ] 验证兼容存储/版本/恢复测试；只改代码，不迁移正式库；任务审阅。

## Task 2 — 三方合并与冲突事件
- [ ] RED：纯三方合并不同节点、相同变化、删改、排序、meta-only、人工保护及重复输入。
- [ ] 新增scripts/knowledge_merge.py：merge_record(base,left,right,preferred='right')->{record,conflicts}，所有输入深拷贝，不写盘。
- [ ] 新增frontend/knowledge_conflicts.py：不可变requests/resolutions，按note聚合，revision校验、可读分歧、原始快照完整保留；服务器缓存仅派生。
- [ ] resolve(root,note_id,payload)在知识事务中保存正文/meta/历史/解决事件；get/list不泄露meta，仅管理员API返回。
- [ ] 阶段审阅；接口约定GET /api/sync-conflicts、GET /api/sync-conflicts/:note_id、POST /api/sync-conflicts/:note_id/resolve；payload={revision,note_revision,choices}，choice含conflict_id与action=current|incoming|manual、可选text。

## Task 3 — 发布、网站同步、部署门禁
- [ ] RED隔离Git测试：自动合并、冲突仅暂停单篇且其它变化发布、服务端固定展示版、第三版本/断网重试。
- [ ] 新增frontend/knowledge_git.py处理Git三版本、整体索引重建、请求及历史树并集；本地与网站调用。
- [ ] 更新local_sync.py、website_sync.py、release.py、site_access.py和server.py，白名单/校验/快照兼容新目录。
- [ ] 不在活跃目录合并代码；网络阶段不长期阻塞其它笔记保存；激活前快照变化继续保留旧站。
- [ ] API沿现有Origin/管理员保护，per-note门禁、全局状态附conflict_note_ids；历史API兼容。
- [ ] 阶段审阅。

## Task 4 — 网页冲突处理
- [ ] RED组件/模型测试：三方显示、选择/手工合并、第三版409保留稿、权限和只锁当前笔记。
- [ ] 新增SyncConflicts.tsx与样式，接入管理员入口，auth/useReview改按note门禁；复制/正文阅读不变。
- [ ] 支持多个输入版本、删除和顺序；不显示meta，真实身份/证据问题用可读选项。
- [ ] 前端测试/构建，隔离浏览器桌面与窄屏验收；阶段审阅。

## Task 5 — 回归、隔离迁移、两端启用
- [ ] 全量相关Python、前端、构建、skill quick_validate、wxq validate；独立整分支审阅。
- [ ] 补知识契约、技能写入要求、部署运行说明；备份并在隔离副本迁移/回读/恢复/双端演练。
- [ ] 兼容代码合入master并部署成功后，再两端备份、显式迁移、发布及验收；保存审计/回退映射。
- [ ] 不变notes无意外变化；提交最终验证链接。
