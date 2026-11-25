import {useContext,useState} from 'react';
import MetadataSuggestions,{lastMetadataTerm,replaceLastMetadataTerm,TemplateMetadataChoices,templateMetadataScope} from './MetadataSuggestions';
import {TemplateDialog} from './TemplateEditor';
import {appendTemplateMetadata,templateMetadataLabels,type TemplateGroup,type TemplateMetadataField} from './templates';

export default function TemplateBatchMetadata({field,groups,proposal,onSave,onClose}:{
 field:TemplateMetadataField;groups:TemplateGroup[];proposal:boolean;
 onSave:(values:string[])=>Promise<void>;onClose:()=>void;
}){
 const label=templateMetadataLabels[field];
 const choices=useContext(TemplateMetadataChoices)[field];
 const [input,setInput]=useState(''),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const values=[...new Set(input.split(/[,，、\n]/).map(value=>value.trim()).filter(Boolean))];
 const tooLong=values.some(value=>Array.from(value).length>40);
 const count=appendTemplateMetadata(groups,field,values).length;
 async function save(){
  if(saving||tooLong||!count)return;
  setSaving(true);
  setError('');
  try{await onSave(values);onClose();}
  catch(error){setError((error as Error).message);}
  finally{setSaving(false);}
 }
 function close(){if(!saving)onClose();}
 return <TemplateDialog title={'批量添加'+label} onClose={close}>
  <form className="template-form template-batch-form" onSubmit={event=>{event.preventDefault();void save();}}>
   <p>已选择 <strong>{groups.length}</strong> 个模板组。添加时会保留已有{label}。</p>
   <label>要添加的{label}
    <textarea rows={3} value={input} aria-describedby="template-batch-hint" aria-invalid={tooLong}
     disabled={saving} onChange={event=>setInput(event.target.value)}/>
   </label>
   <MetadataSuggestions scope={templateMetadataScope(label)} choices={choices} query={lastMetadataTerm(input)}
    selected={values} label={'匹配'+label} onPick={value=>setInput(current=>replaceLastMetadataTerm(current,value)+'、')}/>
   <p id="template-batch-hint" className={tooLong?'error':'muted'}>{tooLong?('每个'+label+'最多 40 个字符。'):'多项可用逗号、顿号或换行分隔。'}</p>
   {values.length>0&&!tooLong&&<p role="status">{count?'将更新 '+count+' 个模板组。':'所选模板组已包含这些'+label+'。'}</p>}
   {error&&<p role="alert" className="error">{error}</p>}
   <footer><button type="button" disabled={saving} onClick={close}>取消</button>
    <button className="primary" disabled={saving||tooLong||!count}>{saving?'保存中…':proposal?'提交提案':'确认添加'}</button></footer>
  </form>
 </TemplateDialog>;
}
