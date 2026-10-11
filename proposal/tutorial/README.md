# 万象棋教学研究流程

当前批次：`batch.json` 的 56 个公开视频；`sources.tsv` 保留用户原始标题。

## 阅读

直接打开上级目录的 `实战教学分析报告.html`，无需网络或本地服务。分享时携带 `tutorial/assets`。完整单视频 JSON 和 Markdown 在 `records`，完整原始 ASR 与文字稿在项目根 `raw`，不进入 Git。用户本次取消 ASR 修正；已有纠正版和纠错记录保留，新分析直接引用原始转写。

报告始终显示真实覆盖情况：未完成、失败或证据不合格的来源不进入有效事件统计。阶段结论在 `synthesis.json` 标记 provisional；全批完成且重新审核后才能改成 final。

## 运行

在项目根运行，使用安装了万象棋技能依赖的 Python（当前可复用原项目 `.wxq-runtime/Scripts/python.exe`）：

```powershell
& $wxqPython proposal/tutorial/tools/tutorial.py register
& $wxqPython proposal/tutorial/tools/tutorial.py prepare 'BV编号:p1' --reuse-root 'D:/GameProjects/os-tutorial'
& $wxqPython proposal/tutorial/tools/tutorial.py validate
& $wxqPython proposal/tutorial/tools/tutorial.py render
& $wxqPython -m unittest discover -s proposal/tutorial/tests -v
```

命令默认目的地为工具所在项目，也可显式 `tutorial.py --root 项目目录`。初次登记保留已有人工标题和备注。已有 JSON 记录优先使用，不会调用采集；已有仅 Markdown 的旧记录也阻止采集，缺少结构化数据时作为局限展示，不擅自重分析。

### 采集回退与逐个分析

CLI 412/403 时，按原技能 `references/workflow.md` 用正常浏览器确认播放，并从 pageAssets 获取实际出现的音视频 HTTPS 地址；不可猜地址、读取隐藏状态或发现登录凭据。浏览器不能直接打包 other 类型的 DASH 资源，使用技能 `download_observed` 检查完整字节数。

将实际观察的元数据和音视频 URL 写入 `raw/reports/observed-BV编号.json`：顶层 `source`、`audio`、`video`。其中 source 包含 id、bvid、part、url、title、author、duration、published、version、acquisition。

```powershell
& $wxqPython proposal/tutorial/tools/acquire_observed.py raw/reports/observed-BV编号.json --model-dir '已安装large-v3的snapshot目录'
```

用户已授权跨视频素材并行。本批运行有界流水线：2个本地 large-v3 ASR 工作线程，每个8个CPU线程；素材下载并行进行，每条完整音频就绪立即进入 ASR 队列。原始转写采用模型原生分段时间戳，跳过额外逐词对齐和人工修正。教学事件及截图仍逐个视频人工核对。避免重复启动多个流水线进程。

遇到整文件截断时，`recover_audio_intervals.py` 从浏览器实际观察的音频地址按20秒区间获取并校验PCM片段；全部区间完整后拼接为WAV，不填充虚构静音，保留原始时间轴。`remote_frames.py` 从实际观察的视频地址定位所需教学画面，获得后须逐张人工审阅才可进入记录。两者都在检查已有分析记录后才执行，不调用LLM。

```powershell
& $wxqPython proposal/tutorial/tools/pipeline.py raw/reports/observed-BV编号1.json raw/reports/observed-BV编号2.json --model-dir '已安装large-v3的snapshot目录' --download-workers 3
```

已有记录优先跳过，已保存原始 ASR 不重新解码；ASR 完成后立即导出全文，即使视频传输失败也保留文字产物。单来源失败不阻止其他来源，最终运行状态保存到 raw/reports/pipeline-last-run.json。transcribing / prepared 均不等于教学分析完成。工具不会用旧技能的 finish 标记教学完成，也不删除未核对的素材。

## 记录契约

记录 schema_version=1。source 使用稳定 BVID:pN；status 为 pending、in_progress、completed、failed。完成记录需提供 source.duration、完整阅读声明、核对时间范围、events 和 unresolved。

每条 event 使用 `BV编号:pN:e001` 等稳定 ID，并填写 start/end、scene（前置讲解／模拟演示／实战）、timing、content、background、goal、quote、segment_ids、template_id 和 screenshots。background/goal 的 basis 为明确说明或分析推断。每张截图使用相对 proposal 的 `tutorial/assets/...` 路径、实际 time、reviewed=true、具体 observation；可带 sha256。完成记录必须保留非空 ASR，并用 transcript_file 标明原始或既有纠正版；原话须出自所引用段落，段落时间须位于事件区间。截图须处于讲解段内，过渡画面与引用段落最多相隔15秒，仍需人工核对相关性。摘要用于检查审阅后是否发生变化。

不以操作结果或战斗获胜泛化策略；缺乏解释的操作、闲聊和吐槽不记录。不同时间的教学分别保存，按触发条件＋内容＋学习目标归入共同模板。模板频次同时提供事件数、不同视频数和作者数。

`analyze_cached.py` 消费代理实际审阅后填写的 `raw/reports/tutorial-annotations-BV编号.json`，验证原话后复制截图并保存 Markdown 与 JSON，不执行语义分类。`review_corrections.py` 消费明确带证据的段落内纠错 ledger，保留原始 ASR，不更新全局别名。存在记录时 save-record 不覆盖；需要人工修订时直接审阅原文件及摘要，并重新 validate，不能自动重采集。

## 增量汇总与验证

在 batch.json 添加来源，登记后逐个处理；完成单视频才写 records。更新 templates.json 与 synthesis.json 的事件引用，运行 validate 和 render。汇总只纳入本批完成且验证通过的记录，缺字段的旧记录保留并显示原因。

HTML 内嵌数据、CSS 和 JS，无 CDN、fetch 或运行时依赖。JSON 转义 HTML 特殊字符，动态内容通过 textContent 展示。图片按需加载，支持关键词、视频、作者、场景及模板筛选、空结果提示、图像对话框和事件锚点。

本批后续教学分析直接引用 asr.raw.json（记录 transcript_file）；不再进行人工 ASR 修正。既有纠正版及已完成记录保留。下载和 large-v3 ASR 均为本地脚本，不调用 LLM。
