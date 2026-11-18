import {textDiff,type DiffPart} from './noteReviewModel';

let worker:Worker|undefined;
let sequence=0;
const pending=new Map<number,(parts:DiffPart[])=>void>();

export function needsDiffWorker(before:string,after:string){
 return before!==after&&(before.length+after.length>=4096||before.length*after.length>=10000);
}

export function initialDiff(before:string,after:string):DiffPart[]{
 if(before===after)return after?[{kind:'same',text:after}]:[];
 return needsDiffWorker(before,after)?textDiff(before,after,0):textDiff(before,after);
}

export function calculateReviewDiff(before:string,after:string,receive:(parts:DiffPart[])=>void){
 if(!needsDiffWorker(before,after)){
  receive(before===after?(after?[{kind:'same',text:after}]:[]):textDiff(before,after));
  return ()=>{};
 }
 const id=++sequence;
 const fallback=()=>textDiff(before,after,0);
 try{
  if(!worker){
   worker=new Worker(new URL('./reviewDiff.worker.ts',import.meta.url),{type:'module'});
   worker.onmessage=({data})=>{const callback=pending.get(data.id);pending.delete(data.id);callback?.(data.parts);};
   worker.onerror=()=>{
    worker?.terminate();
    worker=undefined;
    for(const callback of pending.values())callback([]);
    pending.clear();
   };
  }
  pending.set(id,parts=>receive(parts.length?parts:fallback()));
  worker.postMessage({id,before,after});
 }catch{
  pending.delete(id);
  receive(fallback());
 }
 return ()=>{pending.delete(id);};
}
