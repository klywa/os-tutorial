import {matches,lineupHeroes} from './model';
import type {Entity,Note} from './types';
export type DirectoryFilters={query:string;player:string;hero:string;type:string};
export function normalizeDirectoryType(type:string){return type==='lineup'||type==='player'?'tactics':type;}
export function filterNotes(notes:Note[],filter:DirectoryFilters,entities:Entity[]){
 return notes.filter(n=>(!filter.type||(filter.type==='tactics'?(n.type==='lineup'||n.type==='player'):n.type===filter.type))&&matches(n,filter.query,entities)
  &&(!filter.player||(n.player_id?n.player_id===filter.player:n.meta?.players.includes(filter.player)||n.entities.includes(filter.player)))
  &&(!filter.hero||lineupHeroes(n).includes(filter.hero)));
}
export function noteCounts(notes:Note[],filter:DirectoryFilters,entities:Entity[]){
 const all=filterNotes(notes,{...filter,type:''},entities);
 return {'':all.length,tactics:all.filter(n=>n.type==='lineup'||n.type==='player').length,other:all.filter(n=>n.type==='other').length};
}
export function restoreNoteSelection(notes:Note[],selected:string,player?:string){
 if(notes.some(n=>n.id===selected))return selected;
 const migrated=notes.filter(n=>n.migration?.note_id===selected);
 if(migrated.length)return (migrated.find(n=>n.player_id===player)??migrated[0]).id;
 const linked=notes.filter(n=>n.lineup_links?.some(link=>link.lineup===selected)||n.lineup_ids?.includes(selected));
 const primary=linked.filter(n=>n.lineup_links?.some(link=>link.lineup===selected&&link.role==='primary'));
 return (primary.length===1?primary[0]:linked.length===1?linked[0]:notes.find(n=>n.type==='lineup')??notes[0])?.id??'';
}
