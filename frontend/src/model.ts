import type { Entity, Note, CardSummary, CardFilters, Meta, LateVariant } from './types';
import {documentMarkdown} from './jsonDocument';
export function cardMatches(card:CardSummary,filters:CardFilters){
  const text=[card.name,...card.aliases,card.effect,card.faction.name].join(' ').toLowerCase();
  return filters.query.trim().toLowerCase().split(/\s+/).every(q=>text.includes(q))
    &&(!filters.category||card.category===filters.category)
    &&(!filters.faction||(card.faction.id||'none')===filters.faction)
    &&(!filters.tier||(card.category==='heroes'&&String(card.tier)===filters.tier))
    &&(!filters.awakened||(card.category==='heroes'&&card.awakened===(filters.awakened==='awakened')));
}
export function entityLabel(entity:Entity){return entity.name+(entity.properties?.type===9?'（觉醒）':'');}
export function variantAvailability(meta:Meta,variant:LateVariant,banned:string[]):'playable'|'unplayable'|'unknown'{
  const unique=[...new Set(banned)];
  if(!unique.length)return 'playable';
  if(unique.some(f=>[...meta.required_factions,...variant.required_factions].includes(f)))return 'unplayable';
  const shared=Object.fromEntries(meta.ban_conditions.map(c=>[c.faction,c.status]));
  if(unique.some(f=>shared[f]==='unplayable'))return 'unplayable';
  const conditions={...shared,...Object.fromEntries(variant.ban_conditions.map(c=>[c.faction,c.status]))};
  if(unique.some(f=>conditions[f]==='unplayable'))return 'unplayable';
  if(unique.length>1)return variant.ban_combinations?.find(c=>c.factions.length===unique.length&&c.factions.every(f=>unique.includes(f)))?.status??'unknown';
  return conditions[unique[0]]??'unknown';
}
export function lineupHeroes(note:Note){return [...(note.meta?.core_heroes??note.core),...(note.meta?.late_variants??[]).flatMap(v=>v.core_heroes)];}
export function availability(note:Note,banned:string[]):'playable'|'unplayable'|'unknown'{
  if(!banned.length)return 'playable';
  if(note.meta?.late_variants?.length){const states=note.meta.late_variants.map(v=>variantAvailability(note.meta!,v,banned));return states.includes('playable')?'playable':states.includes('unknown')?'unknown':'unplayable';}
  if(banned.some(f=>note.meta?.required_factions.includes(f)))return 'unplayable';
  const states=banned.map(f=>note.meta?.ban_conditions.find(c=>c.faction===f)?.status??'unknown');
  return states.includes('unplayable')?'unplayable':states.includes('unknown')?'unknown':'playable';
}
export function matches(note:Note,query:string,entities:Entity[]){
  if(!query.trim())return true;
  const refs=[...note.entities,...note.core,...(note.meta?.core_heroes??[]),...(note.meta?.players??[]),...(note.meta?.late_variants??[]).flatMap(v=>[...v.core_heroes,...v.members.flatMap(m=>[m.hero,m.replaces])]),...Object.values(note.meta?.compositions??{}).flat().map(m=>m.hero)];
  const text=[note.title,note.document?documentMarkdown(note.document):'',...refs.filter((r):r is string=>typeof r==='string'&&r.startsWith('pending:')).map(r=>r.slice(8)),...(note.meta?.operation_routes??[]).flatMap(r=>[r.name,r.condition,r.advantages,r.risks,r.transition]),...(note.meta?.late_variants??[]).flatMap(v=>[v.name,v.condition,...v.members.map(m=>m.role+' '+m.replacement_note)]),...(note.aliases??[]),...note.claims.map(c=>c.text),...entities.filter(e=>refs.includes(e.id)).flatMap(e=>[e.name,...(e.aliases??[])])].join(' ').toLowerCase();
  return query.trim().toLowerCase().split(/\s+/).every(q=>text.includes(q));
}
export function sectionText(note:Note,section:string){return note.claims.filter(c=>c.section===section).map(c=>c.text).join('\n\n');}
export async function api<T>(url:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch('/api/'+url,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.error??'请求失败，请重试');return data;
}
