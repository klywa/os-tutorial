# 加速笔记载入：先显示缓存，后台更新

批准方案：IndexedDB缓存目录/选项/卡牌和最近20篇阅读，50MB；当前笔记优先，轻量目录与全文搜索API；读取投影可恢复、版本失效；缓存核验前只读，草稿保护。JSON唯一事实源，不提交Git。

- [x] 后端摘要/搜索投影、增量恢复与ETag接口，首次后台重建。
- [x] IndexedDB、条件读取、工作区/分支隔离与缓存淘汰。
- [x] 阅读器目录/正文分离、后台校验、搜索及草稿保护。
- [x] 性能/功能回归、浏览器/正式只读校验、独审及空闲服务重载。

Ruling: 沿用当前有未提交官方同步和source-registry修改的工作区，逐项叠加，不重置或提交。
Ruling: 后端派生缓存写入失败不丢正式正文；以revision和文件签名判旧并后台重建，读取不采用不匹配投影。

## 2026-10-26 长笔记阅读交互优化（批准方案）

### Phase 1: 生产基线与热点确认
**Status:** complete

### Phase 2: 正文缓存、卡牌定向订阅和滚动监听优化
**Status:** complete

### Phase 3: 全量测试、宽窄屏及第二长笔记验收、独审
**Status:** complete

保留连续全文、知识只读、不提交Git；报告 raw/reading-interaction-delivery.json。


## Follow-up: 5条运营与表达批注修订（2026-10-27）

### Phase 6: Evidence and revision
- [x] 最新5条批注锚点与正文附件快照
- [x] 同批保存正文附件与技能规范
- [x] 校验、浏览器验收与完成批注
- **Status:** complete

本次交付：raw/reports/changxiaoe-annotation-five/delivery.json；5条批注已完成，无本次待核实项。
