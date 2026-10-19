import {expect,it} from 'vitest';
import TaskError from './TaskError';
it('风控提示隐藏但登录及格式错误仍显示',()=>{
 expect(TaskError({error:'HTTP 412'})).toBeNull();
 expect(TaskError({error:'登录失效'})).not.toBeNull();
 expect(TaskError({error:'No video formats found'})).not.toBeNull();
});
