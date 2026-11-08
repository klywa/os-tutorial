import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {TemplateConflictChoices,conflictCandidates,type TemplateConflict} from './TemplateConflicts';
import type {TemplateEvent} from './templates';
describe('template conflict version review',()=>{
 it('presents every pending incoming version and selects the exact chosen record',()=>{
  const first:TemplateEvent={id:'e',name:'第一个传入事件',parameters:[]},second={...first,name:'第二个传入事件'},current={...first,name:'网站当前事件'};
  const item:TemplateConflict={id:'conflict',name:'事件冲突',kind:'event',record_id:'e',revision:'both-seen',base:null,current,incoming:second,versions:[{id:'request-first',base:null,current,incoming:first},{id:'request-second',base:null,current,incoming:second}]};
  const candidates=conflictCandidates(item);
  expect(candidates.map(c=>c.value?.name)).toEqual(['网站当前事件','第一个传入事件','第二个传入事件']);
  expect(candidates.find(c=>c.key==='incoming:request-first')?.value).toEqual(first);
  const html=renderToStaticMarkup(<TemplateConflictChoices item={item} choice="incoming:request-second" onChoose={()=>{}}/>);
  expect(html).toContain('第一个传入事件');expect(html).toContain('第二个传入事件');expect(html.match(/type="radio"/g)).toHaveLength(3);
 });
});
