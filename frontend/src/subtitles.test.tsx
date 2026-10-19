import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import TaskControls from './TaskControls';
import {progressLabel} from './acquisition';
import type {CrawlItem} from './types';
it('shows subtitle phases and permits only download stop while fetching',()=>{
 expect(progressLabel({phase:'checking_subtitles'})).toBe('检查字幕');
 expect(progressLabel({phase:'fetching_subtitles'})).toBe('获取字幕');
 const html=renderToStaticMarkup(createElement(TaskControls,{item:{state:'running',progress:{phase:'fetching_subtitles'}} as CrawlItem,busy:false,onAction:()=>{}}));
 expect(html).toMatch(/<button(?![^>]*disabled)[^>]*aria-label="停止下载"/);
 expect(html).toMatch(/<button[^>]*disabled[^>]*aria-label="停止转录"/);
});
