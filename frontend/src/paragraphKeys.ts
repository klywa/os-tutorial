import {customParagraphKeyRanges,knownReadingFields} from './readingFields';

type Range={start:number;end:number};
const known=new RegExp(`(?:^|(?<=[\\s。！？；;]))(?:${knownReadingFields.join('|')})[：:]`,'gu');
const fenced=/^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^ {0,3}\1[ \t]*(?=\n|$)|(?![\s\S]))/gm;
const inline=/(`+)[^\n]*?\1|!?\[[^\]\n]*\](?:\([^\n)]*\)|\[[^\]\n]*\])|(?:https?:\/\/|www\.)[^\s。！？<>]+/g;

export function paragraphKeyRanges(value:string):Range[]{
 // Mask Markdown and URLs without moving any character offsets.
 const mask=(text:string)=>text.replace(/[^\n]/g,'\0');
 const source=value.replace(fenced,mask).replace(inline,mask);
 const ranges=customParagraphKeyRanges(source);
 for(const match of source.matchAll(known))
  ranges.push({start:match.index,end:match.index+match[0].length});
 ranges.sort((a,b)=>a.start-b.start||b.end-a.end);
 const result:Range[]=[];
 for(const range of ranges){
  const last=result.at(-1);
  if(last&&range.start<last.end)last.end=Math.max(last.end,range.end);
  else result.push(range);
 }
 return result;
}

export function paragraphKeyParts(value:string,ranges:Range[],offset=0){
 const parts:{text:string;highlight:boolean}[]=[];
 let start=0;
 for(const range of ranges){
  const from=Math.max(range.start-offset,0),end=Math.min(range.end-offset,value.length);
  if(from>=end)continue;
  if(start<from)parts.push({text:value.slice(start,from),highlight:false});
  parts.push({text:value.slice(from,end),highlight:true});
  start=end;
 }
 if(start<value.length)parts.push({text:value.slice(start),highlight:false});
 return parts;
}
