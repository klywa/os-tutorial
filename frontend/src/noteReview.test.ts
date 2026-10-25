import {describe,it,expect} from 'vitest';
import {textDiff,reviewFields,applyReviewField,scopeNodes,hasReviewChanges} from './noteReviewModel';
import type {KnowledgeDocument} from './types';

const body:KnowledgeDocument={schema_version:6,nodes:[{id:'h',type:'heading',level:2,title:'英雄'},
 {id:'p',type:'entry',key:'正文',show_key:false,value:'原文'},
 {id:'s',type:'heading',level:3,title:'条件'}, {id:'q',type:'entry',key:'正文',show_key:false,value:'条件正文'},
 {id:'end',type:'heading',level:2,title:'运营'}]};
describe('note review model',()=>{
 it('keeps navigation protected while any field contains invalid unsaved text',()=>{
  expect(hasReviewChanges(body,body,{a:true,b:false})).toBe(true);
  expect(hasReviewChanges(body,body,{a:false,b:false})).toBe(false);
 });
 it('diff reconstructs both texts including unicode and repeated characters',()=>{
  for(const [a,b] of [['甲乙丙','甲新丙'],['😀条件','条件😀'],['aaa','aba'],['','新增']]){
   const diff=textDiff(a,b);
   expect(diff.filter(x=>x.kind!=='add').map(x=>x.text).join('')).toBe(a);
   expect(diff.filter(x=>x.kind!=='remove').map(x=>x.text).join('')).toBe(b);
  }
 });
 it('section scope includes nested sections but excludes next sibling',()=>{
  expect(scopeNodes(body,'h').map(n=>n.id)).toEqual(['h','p','s','q']);
  expect(scopeNodes(body,'p').map(n=>n.id)).toEqual(['p']);
 });
 it('merges changed fields independently and restores deleted nodes with stable ids',()=>{
  const next=structuredClone(body);next.nodes.splice(3,1);(next.nodes[1] as {value:string}).value='新文';
  const fields=reviewFields(body,next);
  const value=fields.find(f=>f.nodeId==='p'&&f.key==='value')!;
  let draft=applyReviewField(next,value,value.oldValue,body);
  expect(draft.nodes[1]).toEqual(body.nodes[1]);
  const removed=fields.find(f=>f.nodeId==='q'&&f.key==='$node')!;
  draft=applyReviewField(draft,removed,removed.oldValue,body);
  expect(draft.nodes.map(n=>n.id)).toEqual(body.nodes.map(n=>n.id));
  expect(next.nodes).toHaveLength(4);
 });
 it('compares semantic fields rather than replacing all structured knowledge',()=>{
  const a={...body,semantics:{route:{name:'旧',cost:2}}};
  const b={...body,semantics:{route:{name:'新',cost:3}}};
  const field=reviewFields(a,b).find(f=>f.path.join('.')==='semantics.route.cost')!;
  expect(applyReviewField(b,field,field.oldValue,a).semantics).toEqual({route:{name:'新',cost:2}});
 });
});
