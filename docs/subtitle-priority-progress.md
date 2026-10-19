# 字幕优先与统计单行实施记录
Plan: 用户批准的任务统计单行展示与B站字幕优先。
Task 1 字幕适配/归档 complete；Task 2 索引/编辑/队列兼容 complete；Task 3 UI/回归/上线 complete；真实字幕下载验收受B站412限制。
Ruling: 复用当前功能分支，正式后台不停止；字幕导入使用独立原始/纠正版文件，不伪造ASR。网页通过prepare注入字幕适配器，CLI仍按原需画面流程运行。测试已观察缺函数RED。

Task 1/2已接入：8新后端专项通过，250Python/42前端/生产构建通过；字幕独立索引、人工编辑保护、路径复制、缓存复用、主题入队及阶段取消已验证。真实2条字幕检查均B站412，尚无真实字幕成功证据，不作成功宣称。正在隔离UI与最终审查。

最终一次审查发现2项重要缺口，已新增3专项RED→GREEN：字幕后续commit/validate/finish与CLI补帧、坏JSON候选回退。另加多分P混合路径测试。最终254Python通过；42前端/构建通过，知识validate 7篇/945卡/errors=[]。真实刷新会话一次后仍412，不继续手动请求。真实字幕成功验收受外站限制；程序模拟通过不冒充真实成功。
UI桌面统计height41/各项同top，420px统计width375/scroll618/各项同top，body width=scrollWidth=420；截图raw/subtitle-stats-desktop.jpg、mobile.jpg。资料测试均隔离。

正式8765已加载，HTTP来源接口通过，重载前后旧任务配置和知识索引保持；独立主题队列继续。临时8766/隔离主题进程已清理。技能格式校验通过。字幕真实验证未通过外站访问，明确保留限制报告raw/subtitle-real-report.json及refresh-report.json；未把模拟文字稿写入正式库。
