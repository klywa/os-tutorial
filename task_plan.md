# 笔记局部编辑、批注与历史对比（2026-10-25）

用户已批准完整方案并要求实现。代码分支 codex/note-edit-comments-history，未提交Git。

- [x] 统一事务历史快照、版本查询、逐字段恢复与证据校验。
- [x] 批注 HTTP/CLI、锚定与并发校验、有限保护授权、完成读回校验。
- [x] 前端章节与段落局部编辑、失焦警告、实时diff、历史合并、批注管理。
- [x] wanxiangqi-knowledge 批注模式与纯措辞授权入口。
- [x] 独立代码审阅及两项草稿保护问题修复。
- [x] 最后回归：完整Python489项、前端94项、构建、quick_validate、正式库validate均通过；浏览器与真实CLI批注闭环通过。

浏览器临时知识库验收已通过，截图和脚本在raw/note-review-*；正式库validate errors[]。
细节计划 docs/superpowers/plans/2026-10-25-note-review.md。
此前77组知识交付已完成，详见raw/reports/batch77/priority-delivery.json与progress.md，不重做。
