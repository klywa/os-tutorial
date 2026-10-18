# 主要变阵实施与验收

方案：docs/superpowers/plans/2026-10-18-major-variants.md

阶段：契约 complete；阅读与编辑 complete；四篇内容与 skill complete；回归和正式应用 complete。

复用 codex/bilibili-crawler 当前工作目录，保留既有未提交工作；未提交、推送或创建新笔记。原后台下载、ASR、主题进程继续运行，仅重载8765 HTTP进程。

## 实现

- schema 4；可选 major_variants、六维证据引用、旧数据兼容、删除降级／关联保护、结论合并重映射与原修订冲突机制。
- 四篇统一阅读投影、章节内引用跳转和主要变阵编辑；静态网站数据改称网站相似组合（统计参考）。
- 保留人工元数据；旧导入遗漏新字段不清空；完整比较和分类报告见 major-variants-review.md。
- 独立 export_reading.py 以同一投影生成四篇HTML，沿用已有阅读版配色样式。

## 数据结果

昭君0、安琪拉0、常小娥6、李信0；共170条原结论完整保留。常小娥14套组合和5条路线不机械转换为变阵。其他3篇非阵容笔记完整记录未变。正式应用无人工冲突。

备份：raw/reports/major-variants-before.json；重放：major-variants-replay.json；正式API／MD／HTML逐条核验：major-variants-final-proof.json。

## 验证

- Python227项通过（raw/major-regression-final.log）；前端33项通过；生产构建通过，仍有原有>500KB打包提示。
- 知识库 validate：7篇、945卡、errors=[]；skill-creator quick_validate 使用UTF-8通过。
- 新用例先复现再修复：六维已知状态无依据、悬空引用、旧导入丢字段、旧无显式ID、主干引用章节错位、共享阅读丢禁用提示、同源HTML缺失及强调标题。
- 新鲜最终审查3项P2均修复：主干不被提前消费、逐组合禁用提示恢复、旧ID统一计算。全部170条结论在MD／网页／HTML主要位置各一次。
- 桌面和420px阅读、章节跳转、键盘Tab、编辑保存通过；编辑使用隔离副本，正式内容没有验收用的假标题。手机正文宽420/scroll420；HTML宽405/scroll405。
- 正式HTTP显示下载1、转写1，原队列仍在工作。没有新攻略搜索、下载或ASR重跑。

截图：raw/major-live.jpg、raw/major-mobile-editor.jpg、raw/major-html-desktop.jpg、raw/major-html-mobile.jpg。

## 过程记录

一次文件工具自动审批超时，按工具允许重试一次成功；没有安全拒绝。一次完整测试遇到隔离后台短时写锁竞争，随后完整227项通过。历史教学快照曾被维护脚本附加新字段，发现后恢复旧结构，脚本现排除before／backup／release快照。

收尾：临时8766/8767服务及验收标签已关闭，8765加载最终实现；Markdown末尾规范后专项14项再次通过，git diff --check通过。正式主题32184和ASR43300进程在服务重载后仍存活。
