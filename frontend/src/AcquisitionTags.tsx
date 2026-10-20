import {useEffect,useState} from 'react';
import {TagInput} from './SourceAnnotations';
import {api} from './model';
export default function AcquisitionTags({value,onChange}:{value:string[];onChange:(tags:string[])=>void}){
 const [choices,setChoices]=useState<string[]>([]),[error,setError]=useState('');
 useEffect(()=>{void api<string[]>('sources/tags').then(setChoices).catch(e=>setError(e.message));},[]);
 return <div className="acquisition-tags"><span>采集标签</span><TagInput value={value} choices={choices} onChange={onChange} autoFocus={false} hint="命中的来源会追加这些标签，已有标签保留。"/>{error&&<small className="muted">已有标签加载失败，仍可输入新标签：{error}</small>}</div>;
}
