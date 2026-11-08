import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import TemplateUtterances from './TemplateUtterances';

describe('template utterance actions',()=>{
 const utterances=[{id:'one',text:'第一条话术'},{id:'two',text:'第二条话术'}];
 it('offers separate add, edit and delete actions to editors',()=>{
  const html=renderToStaticMarkup(<TemplateUtterances utterances={utterances} editable onSave={async()=>{}}/>);
  for(const label of ['新增话术','编辑话术1','删除话术1','编辑话术2','删除话术2','第一条话术','第二条话术'])expect(html).toContain(label);
 });
 it('keeps all text readable and hides write actions for viewers',()=>{
  const html=renderToStaticMarkup(<TemplateUtterances utterances={utterances} editable={false}/>);
  expect(html).toContain('第一条话术');expect(html).toContain('第二条话术');
  expect(html).not.toContain('新增话术');expect(html).not.toContain('编辑话术');expect(html).not.toContain('删除话术');
 });
 it('prevents deleting the final utterance',()=>{
  const html=renderToStaticMarkup(<TemplateUtterances utterances={utterances.slice(0,1)} editable onSave={async()=>{}}/>);
  expect(html).toMatch(/<button[^>]*aria-label="删除话术1"[^>]*disabled=""/);
 });
});
