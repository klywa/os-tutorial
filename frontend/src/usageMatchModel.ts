export type UsagePair={id:string;source_id:string;source_name:string;player_id:string;player_name:string;heroes:string[];hero_names?:string[];rank:number;pair_revision:string;manual_note_id:string|null;automatic_note_id?:string|null;manual_error?:string;candidates?:string[]};
export type MatchNote={id:string;title:string;player_id:string;formations:string[][]};
export type UsageMatchData={revision:string;pairs:UsagePair[];notes:MatchNote[]};
export function matchingOptions(data:UsageMatchData,pair:UsagePair,query:string){
 const suggested=new Set(pair.candidates??[]),q=query.trim().toLocaleLowerCase();
 return data.notes.filter(n=>n.player_id===pair.player_id&&n.title.toLocaleLowerCase().includes(q)).sort((a,b)=>Number(suggested.has(b.title))-Number(suggested.has(a.title))||a.title.localeCompare(b.title,'zh-CN')||a.id.localeCompare(b.id));
}
export const initialMatch=(pair:UsagePair)=>pair.manual_note_id??pair.automatic_note_id??'';
