import type {Lineup} from './types';
import {lineupSearch} from './lineupNames';
export type NameDraft={id:string;revision?:number;common_name:string;aliases:string[];text:string;baseCommon:string;baseAliases:string[]};
export type NameDrafts=Record<string,NameDraft>;
export type ListStatus='all'|'enabled'|'disabled'|'deleted';
export const splitAliases=(value:string)=>[...new Set(value.split(/[,，;；\n\r]+/).map(v=>v.trim()).filter(Boolean))];
export const draftAliases=(d:NameDraft)=>[...new Set([...d.aliases,...splitAliases(d.text)])];
export function changeNameDraft(drafts:NameDrafts,row:Lineup,patch:Partial<Pick<NameDraft,'common_name'|'aliases'|'text'>>){
 const d={...(drafts[row.id]??{id:row.id,revision:row.revision,common_name:row.common_name??'',aliases:[...row.aliases??[]],text:'',baseCommon:row.common_name??'',baseAliases:[...row.aliases??[]]}),...patch};
 const next={...drafts,[row.id]:d};
 if(d.common_name===d.baseCommon&&!d.text&&JSON.stringify(d.aliases)===JSON.stringify(d.baseAliases))delete next[row.id];
 return next;
}
export const namePayload=(drafts:NameDrafts)=>Object.values(drafts).map(d=>({id:d.id,revision:d.revision,common_name:d.common_name.trim(),aliases:draftAliases(d)}));
export function prefillDetail(row:Lineup,draft?:NameDraft){
 const edit={...row,heroes:[...row.heroes],note_ids:[...row.note_ids],...(draft?{common_name:draft.common_name,aliases:draftAliases(draft),revision:draft.revision}:{})};
 return {edit,aliases:(edit.aliases??[]).join('\n'),base:JSON.stringify({edit:row,aliases:(row.aliases??[]).join('\n')})};
}
export function detailAfterSave(edit:Lineup,aliases:string,base:Lineup,baseAliases:string,server:Lineup,savedFields:string[]){
 const pending=Object.fromEntries((['name','common_name','heroes','sort_order','enabled','note_ids','variants'] as const).filter(key=>!savedFields.includes(key)&&JSON.stringify(edit[key])!==JSON.stringify(base[key])).map(key=>[key,edit[key]]));
 return {edit:{...server,...pending},aliases:!savedFields.includes('aliases')&&aliases!==baseAliases?aliases:(server.aliases??[]).join('\n')};
}
export function filterManagedLineups(rows:Lineup[],query:string,status:ListStatus,drafts:NameDrafts){
 const words=query.toLowerCase().trim().split(/\s+/);
 return rows.filter(r=>!r.merged_into&&(status==='deleted'?!!r.deleted_at:!r.deleted_at&&(status==='all'||(status==='enabled'?r.enabled!==false:r.enabled===false)))).filter(r=>{
  const d=drafts[r.id];const text=[lineupSearch(r),r.description??'',r.id,d?.common_name??'',...(d?draftAliases(d):[])].join(' ').toLowerCase();return words.every(w=>text.includes(w));
 });
}
