import type { Entity, Note } from './types';
export function entityLabel(entity:Entity){return entity.name+(entity.properties?.type===9?'（觉醒）':'');}
export function availability(note:Note,banned:string[]):'playable'|'unplayable'|'unknown'{
  if(!banned.length)return 'playable';
  if(banned.some(f=>note.meta?.required_factions.includes(f)))return 'unplayable';
  const states=banned.map(f=>note.meta?.ban_conditions.find(c=>c.faction===f)?.status??'unknown');
  return states.includes('unplayable')?'unplayable':states.includes('unknown')?'unknown':'playable';
}
export function matches(note:Note,query:string,entities:Entity[]){
  const refs=[...note.entities,...note.core,...(note.meta?.core_heroes??[]),...(note.meta?.players??[]),...Object.values(note.meta?.compositions??{}).flat().map(m=>m.hero)];
  const text=[note.title,...(note.aliases??[]),...note.claims.map(c=>c.text),...entities.filter(e=>refs.includes(e.id)).flatMap(e=>[e.name,...(e.aliases??[])])].join(' ').toLowerCase();
  return query.trim().toLowerCase().split(/\s+/).every(q=>text.includes(q));
}
export function sectionText(note:Note,section:string){return note.claims.filter(c=>c.section===section).map(c=>c.text).join('\n\n');}
export async function api<T>(url:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch('/api/'+url,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.error??'请求失败，请重试');return data;
}
