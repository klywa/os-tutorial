export type PromptItem={id:string;title:string;location:string;notes:string};
const oneLine=(value:string)=>value.trim().replace(/\s*\r?\n\s*/g,' ');
export const DEFAULT_SOURCE_PROMPT_TEMPLATE=`根据以下内容，整理【{阵容名}】阵容的打法知识。

注意：

1. 若已有对应知识笔记，则在原笔记的基础上进行内容补充。若有冲突，则让用户裁决。
2. 甄别内容是否真的与当前阵容相关，无关内容自动忽略

内容如下：

{内容列表}`;
export function buildSourcePrompt(name:string,items:PromptItem[],template=DEFAULT_SOURCE_PROMPT_TEMPLATE){
 const content=items.map(item=>{const notes=oneLine(item.notes);return `- ${oneLine(item.title)||item.id}：${item.location}${notes?`（${notes}）`:''}`;}).join('\n');
 return template.replace(/\{阵容名\}|\{内容列表\}/g,token=>token==='{阵容名}'?(name||'{阵容名}'):content);
}
export function removeSubmittedSelection(selected:string[],submitted:string[]){const ids=new Set(submitted);return selected.filter(id=>!ids.has(id));}
export function newerBasket<T extends {revision:number;project_key:string}>(current:T,incoming:T):T{return current.project_key===incoming.project_key&&current.revision>incoming.revision?current:incoming;}
export function singleFlight<T>(work:()=>Promise<T>){
 let pending:Promise<T>|null=null;
 return ()=>{if(!pending)pending=work().finally(()=>{pending=null;});return pending;};
}

/** Retain a failed write until a successful retry, so readers never silently omit it. */
export class StagingWriteGate{
 private current:Promise<unknown>=Promise.resolve();
 private pending=false;
 run<T>(work:()=>Promise<T>):Promise<T>{
  if(this.pending)return Promise.reject(new Error('暂存正在更新，请稍后重试。'));
  this.pending=true;
  const task=Promise.resolve().then(work).finally(()=>{this.pending=false;});
  this.current=task;void task.catch(()=>{});return task;
 }
 async wait(){await this.current;}
 async read<T>(work:()=>Promise<T>):Promise<T>{
  for(let attempt=0;attempt<3;attempt++){
   const write=this.current;await write;
   const result=await work();
   if(write===this.current)return result;
  }
  throw new Error('暂存正在持续更新，请稍后重试；编辑草稿已保留。');
 }
}
export function keepSelection(ids:string[],sources:{id:string;ignored?:boolean}[]){const allowed=new Set(sources.filter(s=>!s.ignored).map(s=>s.id));return [...new Set(ids)].filter(id=>allowed.has(id));}

export async function copyOrFallback(text:string,write:(text:string)=>Promise<void>){try{await write(text);return '';}catch{return text;}}
