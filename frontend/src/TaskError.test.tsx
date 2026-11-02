import {expect,it} from 'vitest';
import TaskError from './TaskError';
it('风控冷却、登录及格式错误均保留状态说明',()=>{
 expect(TaskError({error:'HTTP 412'})).not.toBeNull();
 expect(TaskError({error:'登录失效'})).not.toBeNull();
 expect(TaskError({error:'No video formats found'})).not.toBeNull();
});
