export const seasons=['S1','S2'] as const;
export type Season=typeof seasons[number];
let current:Season='S1';
export const currentSeason=()=>current;
export function setCurrentSeason(season:Season){current=season;}
export function seasonPath(path:string){
 if(current==='S1'||! /^(notes|options|cards|dashboard|templates)(?:[/?]|$)/.test(path))return path;
 const query=path.split('?')[1];
 if(new URLSearchParams(query).has('season'))return path;
 return path+(query===undefined?'?':'&')+'season='+current;
}
