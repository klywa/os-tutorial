import type {CardSummary} from './types';
export type EntityToken={text:string;ids?:string[]};
export function resolveCandidates(ids:string[],references:string[]){const scoped=ids.filter(id=>references.includes(id));return scoped.length===1?scoped:ids;}
export function selectedCandidate(ids:string[],chosen:string){return ids.length===1?ids[0]:ids.includes(chosen)?chosen:'';}
const cache=new WeakMap<CardSummary[],{names:Map<string,string[]>;words:string[];protected:Set<string>}>();
export function splitEntities(text:string,cards:CardSummary[]):EntityToken[]{
 let dict=cache.get(cards);
 if(!dict){const names=new Map<string,string[]>(),protectedNames=new Set(['瑶妹']);for(const c of cards){if(!c.name)continue;names.set(c.name,[...names.get(c.name)??[],c.id]);for(const alias of c.aliases??[])if(alias!==c.name)protectedNames.add(alias);}
  dict={names,words:[...new Set([...names.keys(),...protectedNames])].sort((a,b)=>b.length-a.length),protected:protectedNames};cache.set(cards,dict);}
 const tokens:EntityToken[]=[];let plain='';
 for(let i=0;i<text.length;){const word=dict.words.find(w=>text.startsWith(w,i));if(!word){plain+=text[i++];continue;}
  const ids=dict.names.get(word);const following=text[i+word.length]??'',prior=text[i-1]??'';
  const affixed=/[\p{L}\p{N}_]/u.test(word.at(-1)??'')&&/[A-Za-z0-9_]/.test(following)||/[A-Za-z0-9_]/.test(prior)||/[妹哥姐爷仔]/.test(following)&&!dict.names.has(word+following);
  if(dict.protected.has(word)||!ids||affixed){plain+=word;i+=word.length;continue;}
  if(plain){tokens.push({text:plain});plain='';}tokens.push({text:word,ids});i+=word.length;
 }
 if(plain)tokens.push({text:plain});return tokens;
}
