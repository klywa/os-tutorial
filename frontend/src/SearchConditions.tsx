export function searchKeywords(rows:string[]):string[]{return [...new Set(rows.map(s=>s.trim()).filter(Boolean))];}
export function pasteConditions(rows:string[],index:number,text:string):string[]{
 return searchKeywords([...rows.slice(0,index),...text.split(/\r?\n/),...rows.slice(index+1)]);
}
export default function SearchConditions({rows,strict,onRows,onStrict}:{rows:string[];strict:boolean;onRows:(rows:string[])=>void;onStrict:(value:boolean)=>void}){
 return <fieldset className="search-conditions"><legend>关键词条件</legend>
 {rows.map((value,i)=><div className="search-clause" key={i}>{i>0&&<span className="or-divider">或</span>}<div className="search-clause-input"><input aria-label={`搜索条件 ${i+1}`} value={value} placeholder="例如：姜导 韩信" onChange={e=>onRows(rows.map((s,j)=>i===j?e.target.value:s))} onPaste={e=>{const text=e.clipboardData.getData('text');if(/[\r\n]/.test(text)){e.preventDefault();onRows(pasteConditions(rows,i,text));}}}/><button type="button" aria-label={`删除条件 ${i+1}`} title="删除此条件" disabled={rows.length===1&&!value} onClick={()=>onRows(rows.length===1?['']:rows.filter((_,j)=>i!==j))}>×</button></div></div>)}
 <button type="button" className="add-or" onClick={()=>onRows([...rows,''])}>＋ 添加或条件</button>
 <label className="check-label strict-toggle"><input type="checkbox" checked={strict} onChange={e=>onStrict(e.target.checked)}/>严格匹配</label>
 <p className="muted search-rule">每行单独搜索；行内所有词须出现在标题中，行间满足任意一项。支持粘贴多行。</p>
 </fieldset>;
}
