type Query = {start:number;end:number;text:string};

export function cardQuery(value:string,start:number,end:number):Query|null {
 if(start!==end)return null;
 const hash=value.lastIndexOf('#',start-1);
 if(hash<0||hash>=start)return null;
 const text=value.slice(hash+1,start);
 if(/[\s，。！？；：、,.!?;:()[\]{}（）【】<>《》“”‘’"']/u.test(text))return null;
 return {start:hash,end:start,text};
}

export function completeCardName(value:string,query:Query,name:string) {
 return {value:value.slice(0,query.start)+name+value.slice(query.end),caret:query.start+name.length};
}

function normalize(text:string) {
 return text.normalize('NFKC').toLowerCase();
}

function containsInOrder(text:string,query:string) {
 let offset=0;
 for(const character of query){
  const next=text.indexOf(character,offset);
  if(next<0)return false;
  offset=next+character.length;
 }
 return true;
}

export function rankCards<T extends {name:string;aliases:string[];effect:string}>(cards:T[],text:string):T[] {
 const query=normalize(text);
 if(!query)return cards;
 const buckets:T[][]=[[],[],[],[],[],[]];
 for(const card of cards){
  const name=normalize(card.name);
  if(name===query)buckets[0].push(card);
  else if(name.startsWith(query))buckets[1].push(card);
  else if(name.includes(query))buckets[2].push(card);
  else if(containsInOrder(name,query))buckets[3].push(card);
  else if(card.aliases.some(alias=>containsInOrder(normalize(alias),query)))buckets[4].push(card);
  else if(normalize(card.effect).includes(query))buckets[5].push(card);
 }
 return buckets.flat();
}
