import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import TaskError from './TaskError';
it('风控自动恢复不再展示提示，其他错误保留',()=>{
 const html=renderToStaticMarkup(createElement(TaskError,{error:'B站请求失败（-352）：风控',retry:{attempt:2,next_retry_at:'2026-10-17T15:40:00+08:00'}}));
 expect(html).toBe('');
 expect(renderToStaticMarkup(createElement(TaskError,{error:'[WinError 5] 拒绝访问'}))).toContain('来源登记文件暂时无法保存');
});
