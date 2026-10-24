import type {Meta,Overview,OverviewPreset,Member,Note,OverviewOperations,OverviewOperation} from './types';
import {claimMarkdown} from './reading';
export const stages=['early','middle','late'] as const;
export function newPreset(id:string,name:string,variant_id='',players:string[]=[]):OverviewPreset{return {id,name,variant_id,description:'',placements:[],reserves:[],talents:[],effect_cards:[],talent_note:'',effect_note:'',players:players.map(player=>({player,skills:[],secret:[],exclusive:[],description:''})),stages:{early:{rounds:'',description:'',claim_refs:[],reserves:[]},middle:{rounds:'',description:'',claim_refs:[],reserves:[]},late:{rounds:'',description:'',claim_refs:[],reserves:[]}}};}
export function overviewFor(meta:Meta):Overview{return meta.overview??{version:1,presets:meta.late_variants?.length?meta.late_variants.map(v=>newPreset(v.id,v.name,v.id,meta.players)):[newPreset('default','默认阵容','',meta.players)]};}
export function membersFor(meta:Meta,preset:OverviewPreset,stage:typeof stages[number]):Member[]{return stage==='late'&&preset.variant_id?meta.late_variants?.find(v=>v.id===preset.variant_id)?.members??[]:meta.compositions[stage];}
export function compatibleRoute(meta:Meta,preset:OverviewPreset,routeId:string){const route=meta.operation_routes?.find(r=>r.id===routeId);return !!route&&(!preset.variant_id||route.variant_ids.includes(preset.variant_id));}
export function moveHero(preset:OverviewPreset,cell:number,hero:string){const row=Math.floor(cell/7),col=cell%7,original=preset.placements.find(p=>p.hero===hero);const next=preset.placements.filter(p=>!(p.row===row&&p.col===col)&&p.hero!==hero);return hero?[...next,{hero,row,col,equipment:original?.equipment??[]}]:next;}

export function stageOperations(note:Note,preset:OverviewPreset,stage:typeof stages[number],operations?:OverviewOperations,routeId=''){
 const meta=note.meta!,config=preset.stages[stage],route=meta.operation_routes?.find(r=>r.id===routeId),compatible=compatibleRoute(meta,preset,routeId);
 const hidden=new Set(Object.entries(note.reading_layout?.supporting_claim_refs??{}).filter(([,refs])=>(Array.isArray(refs)?refs:[refs]).some(id=>note.claims.some(c=>c.id===id))).map(([id])=>id));
 const candidates:OverviewOperation[]=[...(operations?.[stage]??[])];
 for(const id of note.document&&operations?[]:[...config.claim_refs,...compatible&&route?route.phases[stage]:[]]){
  const claim=note.claims.find(c=>c.id===id);
  if(claim&&!hidden.has(id))candidates.push({markdown:claimMarkdown(claim,note.reading_layout?.version),claim_refs:[id],route_ids:[],route_names:[]});
 }
 const normalize=(text:string)=>text.replace(/\s+/g,'').trim();
 const seen=new Set(config.description?[normalize(config.description)]:[]),refs=new Set<string>();
 function unique(rows:OverviewOperation[]){return rows.filter(row=>{
  if(row.route_ids.length&&(!routeId||!compatible||!row.route_ids.includes(routeId)))return false;
  if(row.claim_refs.some(id=>refs.has(id)||hidden.has(id))||seen.has(normalize(row.markdown)))return false;
  seen.add(normalize(row.markdown));row.claim_refs.forEach(id=>refs.add(id));return true;
 });}
 const advice=unique(candidates);
 const improvement=stage==='late'?unique(operations?.improvement??[]):[];
 return {advice,improvement};
}
