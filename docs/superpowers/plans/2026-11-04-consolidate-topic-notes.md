# 专题笔记合并实现记录

执行用户批准的计划：昭君成长技能选择合入昭君；拍卖机制、装备详解、等级转移、牌库合入游戏机制，删除五个独立活动笔记，保留历史及旧 ID 解析。

- [x] 读取最新正文与 revision，逐条建立63条内容去向及来源备份。
- [x] 使用纯 key-value 整理多级章节、合并重复规则和证据，完成保义润色及说人话 review。
- [x] 为统一 commit 增加显式 retire 映射，验证来源/目标 revision、人工保护及同步冲突；原子保存归档、目标、别名和索引后才移除源正文及附件。
- [x] CLI 转发可选 retire 参数，更新知识契约。
- [x] 清理活动引用，验证五个旧入口均解析到目标笔记，退役快照可追溯。
- [x] Python JSON 回归23项、合并事务5项通过；前端179项测试与生产构建通过；skill quick_validate及全库知识校验通过（100篇、957张卡牌，无错误）。
- [x] 隔离浏览器1440px/390px验证游戏机制多级章节新增、key-value编辑、保存和刷新，无页面错误；真实本地前端代理验证全部五个旧ID。

审阅范围、排除项及官网查询限制见 raw/reports/consolidation-review.md；逐条去向见 raw/reports/consolidation-destinations.json；备份位于 raw/backups/knowledge/2026-11-04-consolidation。

默认不部署、不提交Git。此前同一聊天的未提交前端和四篇通用笔记改动保留。
