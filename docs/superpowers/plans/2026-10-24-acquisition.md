# 特殊获取知识、全笔记与复制格式实施清单

依据：本聊天已批准的完整方案。当前工作区就地实施，不自动提交Git。

- [x] 复制：jsonDocument.ts 新增 documentClipboard、sectionClipboard；copyEntry 接收正文定位上下文；JsonReading 和整篇入口接入。先写精确输出回归再实现。
- [x] 知识：特殊获取关系模块由官方实体生成，普通/觉醒区分，关系保留依据；reference_store 同步持久化补充并隐藏版本/同步meta。先验证随机渠道、证据、同步幂等。
- [x] 全量审读：逐篇阅读49正文及目标来源，确认供牌英雄、目标牌、昭君6级和三分倒转具体操作。修复标签拆分和版本过程文字，使用统一commit保留ID、证据、人工历史。
- [x] 技能：同步入口、契约、教学和验收；无特殊途径省略字段；正文只显示当前机制。
- [x] 验收：全回归/构建/quick_validate/wxq validate、双入口桌面420px、实际剪贴板/下载/隔离编辑409。

选择：获得途径为显示字段名；无标题正文复制采用最近章节名，无则笔记标题。保留Markdown导出，不全局删方括号或正文加粗。备份 raw/backups/knowledge/acquisition-v1-before.zip。
