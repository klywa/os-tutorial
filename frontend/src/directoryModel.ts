import {matches,lineupHeroes} from './model';
import type {Entity,Note} from './types';
export type DirectoryFilters={query:string;player:string;hero:string;type:string};
export function filterNotes(notes:Note[],filter:DirectoryFilters,entities:Entity[]){
 return notes.filter(n=>(!filter.type||n.type===filter.type)&&matches(n,filter.query,entities)
  &&(!filter.player||n.meta?.players.includes(filter.player)||n.entities.includes(filter.player))
  &&(!filter.hero||lineupHeroes(n).includes(filter.hero)));
}
export function noteCounts(notes:Note[],filter:DirectoryFilters,entities:Entity[]){
 const all=filterNotes(notes,{...filter,type:''},entities);
 return {'':all.length,lineup:all.filter(n=>n.type==='lineup').length,player:all.filter(n=>n.type==='player').length,other:all.filter(n=>n.type==='other').length};
}
export function restoreNoteSelection(notes:Note[],selected:string){
 if(notes.some(n=>n.id===selected))return selected;
 const linked=notes.filter(n=>n.lineup_links?.some(link=>link.lineup===selected)||n.lineup_ids?.includes(selected));
 const primary=linked.filter(n=>n.lineup_links?.some(link=>link.lineup===selected&&link.role==='primary'));
 return (primary.length===1?primary[0]:linked.length===1?linked[0]:notes.find(n=>n.type==='lineup')??notes[0])?.id??'';
}
