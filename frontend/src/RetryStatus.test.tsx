import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import RetryStatus from './RetryStatus';
import TaskError from './TaskError';

it('显示重试次数和真实时间，保留技术详情',()=>{
 const retry={attempt:6,next_retry_at:'2026-11-02T10:30:00+08:00',category:'extractor',error:'Unable to extract initial state'};
 const html=renderToStaticMarkup(<TaskError error={retry.error} retry={retry}/>);
 expect(html).toContain('等待自动重试');expect(html).toContain('6');expect(html).toContain('10:30');
 expect(html).toContain('技术详情');expect(html).toContain('Unable to extract initial state');
});
it('无重试时不显示倒计时',()=>{
 expect(renderToStaticMarkup(<RetryStatus/>)).toBe('');
});
