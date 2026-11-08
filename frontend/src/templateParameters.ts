import type {ParameterType,TemplateParameter} from './templates';

export type ParameterDraft={id:string;name:string;key:string;type:ParameterType;categories:string[];suggestions:string;min:string;max:string};
export function nextParameterKey(parameters:TemplateParameter[]){let n=1;while(parameters.some(p=>p.key==='parameter_'+n))n++;return 'parameter_'+n;}
export function buildTemplateParameter(draft:ParameterDraft,existing:TemplateParameter[]):TemplateParameter{
 const name=draft.name.trim(),key=draft.key.trim();
 if(!name)throw new Error('请填写参数名称');
 if(!/^[a-z][a-z0-9_]{0,63}$/.test(key))throw new Error('参数标识须以小写字母开头，只能包含小写字母、数字和下划线，最多64位');
 if(existing.some(p=>p.key===key))throw new Error('该参数标识已存在，请使用其他标识');
 const parameter:TemplateParameter={id:draft.id,name,key,type:draft.type};
 if(draft.type==='entity'&&draft.categories.length)parameter.entity_categories=[...new Set(draft.categories)];
 if(draft.type==='text'||draft.type==='number'){
  const values=draft.suggestions.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
  if(values.length){if(draft.type==='number'&&values.some(v=>!Number.isFinite(Number(v))))throw new Error('数字参数的建议取值必须是有效数字');parameter.suggestions=draft.type==='number'?values.map(Number):values;}
 }
 if(draft.type==='number'){
  for(const key of ['min','max'] as const)if(draft[key].trim()){const value=Number(draft[key]);if(!Number.isFinite(value))throw new Error('建议范围必须是有效数字');parameter[key]=value;}
  if(parameter.min!=null&&parameter.max!=null&&parameter.min>parameter.max)throw new Error('建议下限不能大于上限');
 }
 return parameter;
}
