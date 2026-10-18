import {useEffect,useRef,useState} from 'react';
export function LineupConfirm({message,onAnswer}:{message:string;onAnswer:(answer:boolean)=>void}){
 const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{ref.current?.showModal();},[]);
 return <dialog ref={ref} className="creator-dialog lineup-confirm" aria-label="确认阵容操作" onCancel={e=>{e.preventDefault();onAnswer(false);}}><h3>确认阵容操作</h3><p>{message}</p><div className="action-line"><button type="button" autoFocus onClick={()=>onAnswer(false)}>取消</button><button type="button" className="primary" onClick={()=>onAnswer(true)}>确认</button></div></dialog>;
}
export function useLineupConfirm(){
 const [pending,setPending]=useState<{message:string;resolve:(answer:boolean)=>void}|null>(null);
 function ask(message:string){return new Promise<boolean>(resolve=>setPending({message,resolve}));}
 return {ask,confirmation:pending?<LineupConfirm message={pending.message} onAnswer={answer=>{pending.resolve(answer);setPending(null);}}/>:null};
}
