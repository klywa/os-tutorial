import {expect,it} from 'vitest';
import {taskError} from './errorSummary';
it('区分风控、索引和音频错误且摘要不包含堆栈',()=>{
 expect(taskError('B站请求失败（-352）：风控校验失败').category).toBe('risk');
 expect(taskError("Traceback\nKeyError: 'corrected_sha256'").category).toBe('transcript');
 expect(taskError('Decoded audio duration 200 differs from source 700').category).toBe('audio');
 expect(taskError('HTTP Error 503: Service Unavailable').category).toBe('network');
});
it('本地保存错误隐藏路径并提示文件占用',()=>{
 const result=taskError("[WinError 5] 拒绝访问: 'D:\\knowledge\\tmp.tmp' -> 'D:\\knowledge\\source-registry.json'");
 expect(result.category).toBe('storage');
 expect(result.summary).toBe('来源登记文件暂时无法保存');
 expect(result.hint).toContain('占用');
});

it('格式缺失不归类为风控',()=>{expect(taskError('No video formats found!').category).toBe('formats');});

it('视频不可访问不归类为网络中断',()=>{expect(taskError('B站请求失败（-404）：视频不存在').category).toBe('unavailable');});

it('报错中的网址不等于网络故障，页面解析有独立分类',()=>{
 expect(taskError('broken data; see https://github.com/yt-dlp').category).toBe('processing');
 expect(taskError('Unable to extract initial state; https://github.com/yt-dlp').category).toBe('extractor');
});

it('以服务端分类为准，并区分占用与崩溃',()=>{
 expect(taskError('HTTP Error 500',{category:'login',phase:'discovery',recoverable:false,hint:'更新登录'}).category).toBe('login');
 expect(taskError('知识库正在保存，请稍后重试').category).toBe('busy');
 expect(taskError('工作进程异常退出（退出码3221225477）').category).toBe('crash');
});
