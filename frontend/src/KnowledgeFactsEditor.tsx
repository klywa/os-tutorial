type Value=unknown;
const labels:Record<string,string>={required_factions:'必须阵营',players:'适用棋手',core_heroes:'核心英雄',compositions:'阶段组成',early:'前期',middle:'中期',late:'后期',hero:'英雄',role:'作用',necessity:'必要性',replaces:'替换对象',replacement_note:'替换条件',ban_conditions:'禁用适用条件',matchups:'应对策略',operation_routes:'运营路线',late_variants:'后期组合',major_variants:'主要变阵',condition:'适用条件',text:'内容',name:'名称',advantages:'优势',risks:'风险',transition:'转向条件',selection:'选用条件',overview:'阵容概览'};
export default function KnowledgeFactsEditor({value,onChange,name='知识属性'}:{value:Value;onChange:(value:Value)=>void;name?:string}){
 if(Array.isArray(value))return <details className="fact-field"><summary>{name}（{value.length}）</summary>{value.map((v,i)=><div key={i}><KnowledgeFactsEditor name={String(i+1)} value={v} onChange={next=>onChange(value.map((old,j)=>j===i?next:old))}/><button type="button" onClick={()=>onChange(value.filter((_,j)=>j!==i))}>移除此项</button></div>)}<button type="button" onClick={()=>onChange([...value,value.length?structuredClone(value[value.length-1]):''])}>添加一项</button></details>;
 if(value!==null&&typeof value==='object'){
  const data=value as Record<string,unknown>;
  if('$text' in data)return <p className="muted">{name}：引用正文条目，在对应正文条目中编辑。</p>;
  return <details className="fact-field"><summary>{name}</summary>{Object.entries(data).map(([key,v])=><KnowledgeFactsEditor key={key} name={labels[key]??key} value={v} onChange={next=>onChange({...data,[key]:next})}/>)}</details>;
 }
 if(typeof value==='boolean')return <label><input type="checkbox" checked={value} onChange={e=>onChange(e.target.checked)}/>{name}</label>;
 return <label>{name}<textarea rows={2} value={value==null?'':String(value)} onChange={e=>onChange(typeof value==='number'?Number(e.target.value):e.target.value)}/></label>;
}
