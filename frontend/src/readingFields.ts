import type {Element, Root, RootContent} from 'hast';

const selectionFields=[
 '必须阵营','关键成员','定阵条件',
 '满足以下条件中的一条或多条可以考虑使用该阵容','以下情况不适合使用该阵容',
 '主要英雄','核心机制','优势','短板','阶段强度','可能变阵',
];
const heroFields=['觉醒需求','等级投入','购买策略','上阵时机','出售时机','获得途径','其他作用'];
const boundary=/[\s。；;]/u;
const sentenceBoundary=/[\n。！？]/u;
const protectedTags=new Set(['a','code','pre','strong','b']);
const custom=/(?:^|(?<=[\n。！？]))[ \t]*([^\s：:\n。！？；;\x00][^：:\n。！？；;\x00]*：)/gu;

export function customParagraphKeyRanges(value:string,startsSentence=true){
 const result:{start:number;end:number}[]=[];
 for(const match of value.matchAll(custom)){
  if((match.index===0&&!startsSentence)||!/[\p{L}\p{N}]/u.test(match[1]))continue;
  const end=match.index+match[0].length;
  result.push({start:end-match[1].length,end});
 }
 return result;
}

function lastCharacter(node:RootContent,ignoreSpaces=false):string|undefined{
 if(node.type==='text')return (ignoreSpaces?node.value.replace(/[ \t]+$/u,''):node.value).at(-1);
 if(node.type==='element'){
  if(node.tagName==='br')return '\n';
  for(let i=node.children.length-1;i>=0;i--){
   const last=lastCharacter(node.children[i],ignoreSpaces);
   if(last!==undefined)return last;
  }
 }
 return undefined;
}

function highlightFields(fields:string[]){
 const pattern=fields.length?new RegExp(`(^|[\\s。；;])((?:${fields.join('|')})[：:])`,'gu'):null;
 return function readingFields(){
  return (tree:Root)=>{
   function visit(parent:Root|Element,leadingBoundary:boolean,leadingSentence:boolean){
    const children=parent.children.flatMap<RootContent>(node=>{
     const atBoundary=leadingBoundary;
     const atSentence=leadingSentence;
     const last=lastCharacter(node);
     if(last!==undefined)leadingBoundary=boundary.test(last);
     const lastNonSpace=lastCharacter(node,true);
     if(lastNonSpace!==undefined)leadingSentence=sentenceBoundary.test(lastNonSpace);
     if(node.type==='element'&&!protectedTags.has(node.tagName)){
      const block=['p','li','td','th'].includes(node.tagName);
      visit(node,block||atBoundary,block||atSentence);
     }
     if(node.type!=='text')return [node];
     const ranges=customParagraphKeyRanges(node.value,atSentence);
     for(const match of pattern?node.value.matchAll(pattern):[]){
      if(match.index===0&&!match[1]&&!atBoundary)continue;
      const start=match.index+match[1].length;
      ranges.push({start,end:start+match[2].length});
     }
     ranges.sort((a,b)=>a.start-b.start||b.end-a.end);
     const result:RootContent[]=[];
     let end=0;
     for(const {start,end:stop} of ranges){
      if(start<end)continue;
      if(start>end)result.push({type:'text',value:node.value.slice(end,start)});
      result.push({type:'element',tagName:'strong',properties:{},children:[{type:'text',value:node.value.slice(start,stop)}]});
      end=stop;
     }
     if(!result.length)return [node];
     if(end<node.value.length)result.push({type:'text',value:node.value.slice(end)});
     return result;
    });
    if(parent.type==='root')parent.children=children;
    else parent.children=children as Element['children'];
   }
   visit(tree,true,true);
  };
 };
}

const playerFields=[...selectionFields,'前期','中期','后期'];
const lineupFields=[...selectionFields,...heroFields];
export const knownReadingFields=[...new Set([...playerFields,...lineupFields])];
export const playerReadingFields=[highlightFields(playerFields)];
export const lineupReadingFields=[highlightFields(lineupFields)];
export const otherReadingFields=[highlightFields([])];
