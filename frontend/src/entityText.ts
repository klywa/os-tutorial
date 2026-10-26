import type {CardSummary} from './types';
export type EntityToken={text:string;ids?:string[]};
const indexes=new WeakMap<CardSummary[],{byId:Map<string,CardSummary>;heroes:Map<string,CardSummary[]>}>();
export function cardIndex(cards:CardSummary[]){
 let index=indexes.get(cards);if(index)return index;
 const byId=new Map(cards.map(c=>[c.id,c])),heroes=new Map<string,CardSummary[]>();
 for(const c of cards)if(c.category==='heroes'){const rows=heroes.get(c.name)??[];rows.push(c);heroes.set(c.name,rows);}
 for(const rows of heroes.values())rows.sort((a,b)=>Number(a.awakened)-Number(b.awakened)||a.id.localeCompare(b.id));
 index={byId,heroes};indexes.set(cards,index);return index;
}
export function resolveCandidates(ids:string[],references:string[]){const scoped=ids.filter(id=>references.includes(id));return scoped.length===1?scoped:ids;}
export function selectedCandidate(ids:string[],chosen:string){return ids.length===1?ids[0]:ids.includes(chosen)?chosen:'';}
export function heroVersions(cards:CardSummary[],ids:string[]){
 const index=cardIndex(cards),seeds=ids.map(id=>index.byId.get(id)),first=seeds[0];
 if(!first||seeds.some(c=>!c||c.category!=='heroes'||c.name!==first.name))return [];
 return index.heroes.get(first.name)??[];
}
const cache=new WeakMap<CardSummary[],{names:Map<string,string[]>;words:Map<string,string[]>;protected:Set<string>;tokens:Map<string,EntityToken[]>}>();
export function splitEntities(text:string,cards:CardSummary[]):EntityToken[]{
 let dict=cache.get(cards);
 if(!dict){const names=new Map<string,string[]>(),protectedNames=new Set(['瑶妹']);for(const c of cards){if(!c.name)continue;names.set(c.name,[...names.get(c.name)??[],c.id]);for(const alias of c.aliases??[])if(alias!==c.name)protectedNames.add(alias);}
  const words=new Map<string,string[]>();for(const word of [...new Set([...names.keys(),...protectedNames])].sort((a,b)=>b.length-a.length)){const list=words.get(word[0])??[];list.push(word);words.set(word[0],list);}
  dict={names,words,protected:protectedNames,tokens:new Map()};cache.set(cards,dict);}
 const cached=dict.tokens.get(text);if(cached)return cached;
 const tokens:EntityToken[]=[];let plain='';
 for(let i=0;i<text.length;){const word=dict.words.get(text[i])?.find(w=>text.startsWith(w,i));if(!word){plain+=text[i++];continue;}
  const ids=dict.names.get(word);const following=text[i+word.length]??'',prior=text[i-1]??'';
  const affixed=/[\p{L}\p{N}_]/u.test(word.at(-1)??'')&&/[A-Za-z0-9_]/.test(following)||/[A-Za-z0-9_]/.test(prior)||/[妹哥姐爷仔]/.test(following)&&!dict.names.has(word+following);
  if(dict.protected.has(word)||!ids||affixed){plain+=word;i+=word.length;continue;}
  if(plain){tokens.push({text:plain});plain='';}tokens.push({text:word,ids});i+=word.length;
 }
 if(plain)tokens.push({text:plain});
 // Bound retained text across notes; the whole cache expires with its card collection.
 if(text.length<=16000){if(dict.tokens.size>=512)dict.tokens.delete(dict.tokens.keys().next().value!);dict.tokens.set(text,tokens);}return tokens;
}
