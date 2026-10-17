export function taskError(error:string){
 if(/WinError (?:5|32|33)\b|PermissionError|拒绝访问|Permission denied/i.test(error))return {category:'storage',summary:'来源登记文件暂时无法保存',hint:'自动重试后仍无法保存，请检查文件占用或目录权限，再重新检查。'};
 if(/-frames:v|extract_frames|frame.*extraction/i.test(error))return {category:'frames',summary:'关键帧提取失败',hint:'已有文字稿可继续使用；视频保留，待补取画面。'};
 if(/-352|-401|风控|412/.test(error))return {category:'risk',summary:'等待解除B站风控',hint:'在浏览器确认空间可访问，检查本机cookies后重新检查。'};
 if(/-101|登录|cookies.*过期/i.test(error))return {category:'login',summary:'需要更新登录信息',hint:'在B站连接设置中更新本机cookies后重试。'};
 if(/corrected_sha256|index needs verification|文字稿|Transcript/i.test(error))return {category:'transcript',summary:'文字稿校验未通过',hint:'重试将复用已有转写；无法验证的内容需人工核对。'};
 if(/Decoded audio|Invalid data|音频|duration.*differs/i.test(error))return {category:'audio',summary:'音频损坏或时长不完整',hint:'重试将重新获取音频，并保留失败材料。'};
 if(/HTTP|connection|timed? ?out|Downloaded.*expected|网络/i.test(error))return {category:'network',summary:'网络连接或下载中断',hint:'保留可续传文件，稍后重试。'};
 return {category:'processing',summary:error.split('\n')[0].slice(0,100)||'任务处理失败',hint:'查看技术详情，修复后重试。'};
}
