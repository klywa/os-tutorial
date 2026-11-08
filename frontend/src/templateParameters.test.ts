import {describe,it,expect} from 'vitest';
import {buildTemplateParameter,nextParameterKey,type ParameterDraft} from './templateParameters';

const draft:ParameterDraft={id:'new_param',name:'剩余金币',key:'gold',type:'number',categories:[],suggestions:'10，20',min:'0',max:'100'};
describe('parameters added while editing a template',()=>{
 it('builds typed suggestions and optional range hints',()=>{
  expect(buildTemplateParameter(draft,[])).toEqual({id:'new_param',name:'剩余金币',key:'gold',type:'number',suggestions:[10,20],min:0,max:100});
 });
 it('rejects duplicate keys and malformed numeric suggestions without changing definitions',()=>{
  const existing=[{id:'old',name:'金币',key:'gold',type:'number' as const}];
  expect(()=>buildTemplateParameter(draft,existing)).toThrow('已存在');
  expect(()=>buildTemplateParameter({...draft,suggestions:'10,abc'},[])).toThrow('数字');
  expect(existing).toHaveLength(1);
 });
 it('omits empty entity restrictions and generates an unused default key',()=>{
  expect(buildTemplateParameter({...draft,type:'entity'},[])).toEqual({id:'new_param',name:'剩余金币',key:'gold',type:'entity'});
  expect(nextParameterKey([{id:'p',key:'parameter_1',name:'参数',type:'text'}])).toBe('parameter_2');
 });
});
