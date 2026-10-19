# B站采集恢复实施

2026-10-19开始。按批准方案拆分发现／字幕／媒体、统一会话限速、结构化结果、恢复历史失败。
Ruling: 复用现有 codex/bilibili-crawler 功能分支，保留所有已有修改；字幕请求失败允许有记录地回退ASR。
专项RED已建立；不在真实数据进行编辑验收。

阶段：核心实现与275Python/46前端及构建通过；真实截图视频音频31547415字节、1698.145秒，独立large-v3 CPU全稿转写in_progress。官方latest 2026.08.19与本机相同，未升级依赖。独立审查in_progress。

## 交付结果（2026-10-19）
核心修复、真实验证与8765上线complete；恢复批量后台in_progress。

- 字幕检查与媒体格式解耦，完整元数据／无格式元数据回退，字幕受限刷新一次后自动走独立音频及large-v3，失败真实原因归档，不冒充无字幕。
- 跨进程SQLite请求限速、端点冷却及会话刷新互斥；会话身份包含配置路径与内容指纹，清空配置不复用旧身份。保留原cookies文件，不输出内容。
- 工作进程写入结构化结果，HTTP调度器只补偿异常退出，不截断覆盖已有结果。成功／排队及当前失败覆盖遗留源状态；恢复不降级complete沉淀状态。
- 独立审查3项重要问题已修复并回归：complete保护、会话身份失效、逐P错误类别及阶段保留。

## 验证
281项Python通过（含真实跨进程限速），47项前端通过，生产构建通过（现有500kB单包提示保留）。知识validate无错误、skill格式有效、diff --check通过。
桌面／420px隔离验收：旧412不显示，登录与格式错误保留技术详情，420px scrollWidth=420。截图见raw/acquisition-recovery-desktop.jpg、raw/acquisition-recovery-mobile.jpg。

真实截图视频 BV1zphC6NEH4：详情接口仍412，但音频下载31547415字节成功，解码1698.145秒；large-v3 CPU输出52段至1697.09秒。隔离文字稿校验通过后按同来源安全复用至正式任务，无重复转写；raw/BV1zphC6NEH4_p1.md 已可页内读取与复制绝对路径，校验errors=[]。
第二条真实 BV1UEeP6LEoF 也由受限字幕回退音频（约2.21MiB、231.7秒）并完成large-v3，正式文字稿校验errors=[]。另外多条真实来源已成功下载并进入ASR。没有宣称字幕／详情API已解除B站限制。
官方发布页 https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19 与已安装版本相同，未升级依赖。

## 正式恢复与保护
共60条仍有效的历史访问／格式相关任务恢复；截至核查，2条已完成，其他继续后台。主动停止、删除不恢复；其他错误不批量重试。
备份：raw/acquisition-recovery-before/，恢复清单raw/acquisition-recovery-applied.json。
正式knowledge JSON／MD哈希无变化，source-registry人工资料完全相同；原主题进程32184保留。隔离8766网页及真实验收转写均已结束，隔离数据保留供复核。
正式截图：raw/acquisition-recovery-formal.jpg。
