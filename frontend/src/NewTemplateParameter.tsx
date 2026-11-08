import {useState} from 'react';
import {categoryNames} from './EntityCards';
import {templateId,typeNames,type ParameterType,type TemplateEvent,type TemplateParameter} from './templates';
import {buildTemplateParameter,nextParameterKey,type ParameterDraft} from './templateParameters';

export default function NewTemplateParameter({event,onAdd,onCancel}:{event:TemplateEvent;onAdd:(parameter:TemplateParameter)=>void;onCancel:()=>void}){
 const [draft,setDraft]=useState<ParameterDraft>(()=>({id:templateId('parameter'),name:'',key:nextParameterKey(event.parameters),type:'text',categories:[],suggestions:'',min:'',max:''})),[error,setError]=useState('');
 function patch(value:Partial<ParameterDraft>){setDraft(d=>({...d,...value}));setError('');}
 function add(){try{onAdd(buildTemplateParameter(draft,event.parameters));}catch(e){setError((e as Error).message);}}
 return <fieldset className="template-new-parameter"><legend>新增事件参数</legend><p className="muted">为“{event.name}”增加共用参数，随本模板一起保存后生效。</p>
  <div className="template-form-grid"><label>参数名称<input autoFocus value={draft.name} onChange={e=>patch({name:e.target.value})}/></label><label>参数类型<select value={draft.type} onChange={e=>patch({type:e.target.value as ParameterType})}>{Object.entries(typeNames).map(([type,name])=><option key={type} value={type}>{name}</option>)}</select></label>
  <label>参数标识<input aria-label="参数标识" value={draft.key} maxLength={64} onChange={e=>patch({key:e.target.value})}/><small>已自动生成，可修改；话术中使用 {'{'+draft.key+'}'} 引用。</small></label>
  {draft.type==='entity'&&<label>允许的实体类别<select aria-label="允许的实体类别" multiple value={draft.categories} onChange={e=>patch({categories:Array.from(e.target.selectedOptions,o=>o.value)})}>{Object.entries(categoryNames).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select><small>不选表示所有实体类别。</small></label>}
  {(draft.type==='text'||draft.type==='number')&&<label>建议取值（可选，逗号分隔）<input value={draft.suggestions} onChange={e=>patch({suggestions:e.target.value})}/></label>}
  {draft.type==='number'&&<><label>建议下限（可选）<input type="number" step="any" value={draft.min} onChange={e=>patch({min:e.target.value})}/></label><label>建议上限（可选）<input type="number" step="any" value={draft.max} onChange={e=>patch({max:e.target.value})}/></label></>}
  </div>{error&&<p className="template-inline-error" role="alert">{error}</p>}<div className="template-inline-actions"><button type="button" onClick={onCancel}>取消新增参数</button><button type="button" className="primary" onClick={add}>添加并使用</button></div>
 </fieldset>;
}
