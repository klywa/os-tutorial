export default function NoteTitleField({value,onChange,readOnly=false,shared=false,disabled=false}:{value:string;onChange:(value:string)=>void;readOnly?:boolean;shared?:boolean;disabled?:boolean}){
 return <label>笔记标题<input aria-label="笔记标题" value={value} readOnly={readOnly} disabled={disabled} onChange={e=>onChange(e.target.value)}/>{shared&&<small className="muted">整篇笔记共用此标题，修改后同步到所有棋手分支。</small>}</label>;
}
