import {describe,it,expect} from 'vitest';
import {sourceMatches,visibleSelection,progressLabel} from './acquisition';
import type {Source} from './types';

const row:Source={id:'BV1:p1',url:'https://www.bilibili.com/video/BV1',title:'教学',stage:'prepared',knowledge_status:'unprocessed',linked_notes:[],published:'2026-10-16',view_count:100,keywords:['李信'],batches:['batch1'],transcript_status:'ready'};
describe('acquisition interactions',()=>{
  it('filters date boundaries, keywords, batch and numeric unknowns',()=>{
    expect(sourceMatches(row,{date_from:'2026-10-16',date_to:'2026-10-16',keyword:'李信',batch:'batch1',min_views:'100'})).toBe(true);
    expect(sourceMatches({...row,view_count:undefined},{min_views:'100'})).toBe(false);
    expect(sourceMatches(row,{keyword:'其他'})).toBe(false);
  });
  it('selects the full filtered set and preserves prior page selections',()=>{
    expect(visibleSelection(['old'],[row])).toEqual(['old','BV1:p1']);
    expect(visibleSelection(['BV1:p1'],[row])).toEqual(['BV1:p1']);
  });
  it('reports measured progress only',()=>{
    expect(progressLabel({phase:'downloading'})).toBe('下载中');
    expect(progressLabel({phase:'transcribing',processed_seconds:30,total_seconds:60})).toContain('50%');
  });
  it('filters both queue state and current processing stage',()=>{
    const running={...row,stage:'transcribing',acquisition_state:'running',transcript_status:'missing'};
    expect(sourceMatches(running,{stage:'transcribing'})).toBe(true);
    expect(sourceMatches(running,{stage:'running'})).toBe(true);
  });
});
