# UP 主监听故障恢复实施记录

依据：本次用户批准的“UP 主监听故障恢复与自动重试”方案。

- [x] 结构化错误分类、持久重试、历史恢复及取消保护。
- [x] 标签追补自动恢复、版本围栏与短写锁。
- [x] 下载 API 回退、工作进程诊断、保守转写恢复。
- [x] 前端重试状态、README、回归与受控实测。
- [x] 独立最终审查并修复重要问题。

约束：保留本地已有改动；不提交、推送或操作服务器；真实视频实测使用独立运行目录，不重置正在运行的采集队列。

Ruling: 复用当前工作目录，不创建分支或 worktree — 用户指定在当前项目实施并保留未提交改动，.git 为只读。
Ruling: 既有 risk_retries 和 network_retries 保留兼容；新增统一重试表，并以最新任务 generation/标签 version 为围栏。风险冷却不被手动重试清除。
Pre-flight: 重试状态由后端维护，前端只展示；续传仍使用 ResumeGuard；标签写入不得持 SQLite 事务等待知识库写锁。

## 验证

- 新增恢复测试 18 项通过（temp/monitor-new-tests-final.log）：可控时钟持续退避、重启保留、真实写锁超过2秒后恢复、人工资料保留、暂停标签任务、旧generation/version围栏、手动重试保留risk gate、真实子进程异常退出回执、CPU large-v3保守参数、风控重试保留分P/检查点。
- 共享采集/字幕/原子保存回归101项通过（temp/monitor-shared-regression-final.log）。
- Python主套件193项检查通过、2项平台跳过（temp/monitor-python-final.log；最后补充的风控检查点测试及错误分类变更另经恢复18项与共享101项回归验证）。
- 前端157项通过（temp/monitor-frontend-all-final.log），生产构建通过（temp/monitor-build-final.log），仅现有大chunk建议。
- 隔离浏览器1440/390宽度：追补等待、解析错误、技术详情、手动重试清除旧状态通过；截图 temp/monitor-browser/retry-1440.png、retry-390.png。
- 真实探测两个BV：均读取到1个分P、9个播放格式；网页提取均返回HTTP412，按risk处理，未下载完整媒体、未运行完整ASR。结果 temp/monitor-real-probe/ 下各BV/result.json。
- av、ctranslate2、faster_whisper、onnxruntime分别隔离导入返回0，本机CUDA设备数0；未重现历史0xC0000005，不能声称已确认其原生组件根因或已验证真实GPU回退。模拟GPU阶段由真实退出的隔离Python子进程验证父进程恢复，模型配置由替身验证。
- Windows沙箱临时目录/SSR缓存限制导致初轮大套件setup失败；沙箱外重跑通过，未修改测试来掩盖权限故障。
- 技能结构quick_validate通过（temp/monitor-skill-validate.log）。
- 最终wxq validate通过：102篇笔记、957张卡牌，errors为空（temp/monitor-knowledge-validate.log）；未修改正式知识。

## 最终审查及修复

独立审查 monitor_resilience_review 发现并已修复：失联worker恢复绕过crash退避、CPU恢复配置随阶段更新丢失、手动重试后显示旧时间。分别有新增回归覆盖。其余未发现可证实严重缺陷；真实CDN完整下载与GPU原生崩溃仍受上述验收范围限制。

Ruling: 共享media.py增加可选runtime_options，默认路径和large-v3模型不变；仅由已确认GPU转写崩溃的worker启用CPU保守参数。共享源码位于.codex只读目录，通过针对该文件的审批工具完成，不改技能指令。
Ruling: 保留既有已派发视频历史处理需求语义；监听暂停/停用阻止新扫描及其标签工作，独立视频暂停/删除阻止自动恢复，其余有效共享需求继续处理。
