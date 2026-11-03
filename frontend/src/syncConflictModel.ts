import type {KnowledgeDocument,Note} from './types';
import {api} from './model';
export type ConflictValue=string|null|string[];
export type SyncConflict={id:string;path:string;reason:string;base:ConflictValue;current:ConflictValue;incoming:ConflictValue;variant_id:string;variants:{variant_id:string;value:ConflictValue}[]};
export type ConflictGroup={note_id:string;title?:string;revision:string;note_revision:string;request_ids:string[];current:{variant_id:string;body:KnowledgeDocument|null};variants:{variant_id:string;body:KnowledgeDocument|null}[];conflicts:SyncConflict[]};
export type ConflictDraft={action?:'current'|'incoming'|'manual';variant_id?:string;text?:string};
export type ConflictDrafts=Record<string,ConflictDraft>;
export const allowsManual=(path:string)=>/^body\/nodes\/(?!order$)[^/]+(?:\/(?:value|title))?$/.test(path);
export function conflictPayload(group:ConflictGroup,drafts:ConflictDrafts){
 const choices=group.conflicts.map(conflict=>{
  const draft=drafts[conflict.id];if(!draft?.action)throw new Error('请逐项选择最终方案');
  if(draft.action==='manual'){if(!allowsManual(conflict.path))throw new Error('此项需要选择完整方案');return {conflict_id:conflict.id,action:draft.action,text:draft.text??''};}
  if(draft.action==='incoming'){
   const variants=conflict.variants?.length?conflict.variants:[{variant_id:conflict.variant_id,value:conflict.incoming}];
   const id=draft.variant_id??(variants.length===1?variants[0].variant_id:undefined);
   if(!variants.some(v=>v.variant_id===id))throw new Error('请选择另一端版本');
   return {conflict_id:conflict.id,action:draft.action,variant_id:id};
  }
  return {conflict_id:conflict.id,action:draft.action};
 });return {revision:group.revision,note_revision:group.note_revision,choices};
}
export function refreshConflictDrafts(drafts:ConflictDrafts):ConflictDrafts{return Object.fromEntries(Object.entries(drafts).map(([id,draft])=>[id,{text:draft.text}]));}
export async function resolveConflict(group:ConflictGroup,drafts:ConflictDrafts,request:typeof api=api){
 try{return {stale:false as const,saved:await request<Note|null|{note:Note|null}>('sync-conflicts/'+encodeURIComponent(group.note_id)+'/resolve','POST',conflictPayload(group,drafts))};}
 catch(error){if((error as {status?:number}).status!==409)throw error;return {stale:true as const,group:await request<ConflictGroup>('sync-conflicts/'+encodeURIComponent(group.note_id))};}
}
export function conflictField(path:string){if(path==='body/nodes/order')return '段落顺序';if(path==='record')return '笔记保留或删除';if(path.includes('semantics')||path.includes('metadata'))return '正文关联信息';if(path.endsWith('/title'))return '章节标题';return '正文段落';}
export function bodyText(body:KnowledgeDocument|null){return body?body.nodes.map(n=>n.type==='heading'?n.title:(n.show_key?n.key+'：':'')+n.value).join('\n\n'):'已删除';}
export function conflictText(value:ConflictValue,group:ConflictGroup,path="body/nodes/order"){if(value===null)return '已删除';if(Array.isArray(value)){if(!path.endsWith("/order"))return value.length?value.join("、"):"无";const nodes=[...(group.current.body?.nodes??[]),...group.variants.flatMap(v=>v.body?.nodes??[])];return value.length?value.map(id=>{const node=nodes.find(n=>n.id===id);return node?(node.type==='heading'?node.title:node.key||node.value):'未命名段落';}).join(' → '):'无段落';}return value;}
