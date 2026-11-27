import {describe,expect,it} from 'vitest';
import {loadTemplateTrace,parseTemplateTrace} from './templateTrace';

const library={name:'模板.json',raw:'{"title":"模板"}'};
const writing={limited:'限制',not_limited:'不限制',expected:'预期',wording:'用语建议'};
const trace={
 schema_version:2,run_id:'run-1',library_name:library.name,
 library_sha256:'183ab18560d5e3bfd415c84c2d135e3d22140ba9715cf915489be3b2fe13619a',
 knowledge_lists:{list:[{original:'知识原句',type:'常规',prerequisite:'前提',related_knowledge:'补充'}]},
 prompts:{prompt:'完整知识识别提示词'},
 points:{point:{knowledge:'补充后的知识',events:[{id:'event',event:'触发事件',expected:'目标'}],conditions:[{
  id:'condition',event_id:'event',expression:'触发条件',reason:'理由',...writing,
 }]}},
 groups:{group:{point_id:'point',event_id:'event',condition_id:'condition',knowledge_list_id:'list',
  prompt_ids:{identify:'prompt'},writing,sentences:Object.fromEntries(Array.from({length:6},(_,i)=>[`sentence${i}`,`生成的句子 ${i+1}`]))}},
};

describe('compact template trace',()=>{
 it('resolves the five stages through the shared point, knowledge list and prompts',()=>{
  expect(parseTemplateTrace(JSON.stringify(trace))).toEqual(trace);
 });

 it('rejects the previous format and broken group references',()=>{
  expect(()=>parseTemplateTrace(JSON.stringify({...trace,schema_version:1}))).toThrow('格式');
  expect(()=>parseTemplateTrace(JSON.stringify({...trace,points:{}}))).toThrow('模板组');
  expect(()=>parseTemplateTrace(JSON.stringify({...trace,groups:{group:{...trace.groups.group,sentences:{sentence:'只有一句'}}}}))).toThrow('模板组');
 });

 it('distinguishes an edited main library from an unrelated trace',async()=>{
  const handle={name:'模板-detail.json',getFile:async()=>({text:async()=>JSON.stringify(trace)})};
  await expect(loadTemplateTrace(handle,library)).resolves.toMatchObject({modified:false});
  await expect(loadTemplateTrace(handle,{...library,raw:'{}'})).resolves.toMatchObject({modified:true});
  await expect(loadTemplateTrace({...handle,getFile:async()=>({text:async()=>JSON.stringify({...trace,library_name:'其他.json'})})},library)).rejects.toThrow('不匹配');
 });
});
