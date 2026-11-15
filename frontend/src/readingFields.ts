import type {Element, Root, RootContent} from 'hast';

const selectionFields=[
 '必须阵营','关键成员','定阵条件',
 '满足以下条件中的一条或多条可以考虑使用该阵容','以下情况不适合使用该阵容',
 '主要英雄','核心机制','优势','短板','阶段强度','可能变阵',
];
const heroFields=['觉醒需求','等级投入','购买策略','上阵时机','出售时机','获得途径','其他作用'];
const boundary=/[\s。；;]/u;
const protectedTags=new Set(['a','code','pre','strong','b']);

function lastCharacter(node:RootContent):string|undefined{
 if(node.type==='text')return node.value.at(-1);
 if(node.type==='element'){
  for(let i=node.children.length-1;i>=0;i--){
   const last=lastCharacter(node.children[i]);
   if(last!==undefined)return last;
  }
 }
 return undefined;
}

function highlightFields(fields:string[]){
 const pattern=new RegExp(`(^|[\\s。；;])((?:${fields.join('|')})[：:])`,'gu');
 return function readingFields(){
  return (tree:Root)=>{
   function visit(parent:Root|Element,leadingBoundary:boolean){
    const children=parent.children.flatMap<RootContent>(node=>{
     const atBoundary=leadingBoundary;
     const last=lastCharacter(node);
     if(last!==undefined)leadingBoundary=boundary.test(last);
     if(node.type==='element'&&!protectedTags.has(node.tagName)){
      visit(node,node.tagName==='p'||node.tagName==='li'||node.tagName==='td'||node.tagName==='th'||atBoundary);
     }
     if(node.type!=='text')return [node];
     const result:RootContent[]=[];
     let end=0;
     for(const match of node.value.matchAll(pattern)){
      if(match.index===0&&!match[1]&&!atBoundary)continue;
      const start=match.index+match[1].length;
      if(start>end)result.push({type:'text',value:node.value.slice(end,start)});
      result.push({type:'element',tagName:'strong',properties:{},children:[{type:'text',value:match[2]}]});
      end=start+match[2].length;
     }
     if(!result.length)return [node];
     if(end<node.value.length)result.push({type:'text',value:node.value.slice(end)});
     return result;
    });
    if(parent.type==='root')parent.children=children;
    else parent.children=children as Element['children'];
   }
   visit(tree,true);
  };
 };
}

export const playerReadingFields=[highlightFields([...selectionFields,'前期','中期','后期'])];
export const lineupReadingFields=[highlightFields([...selectionFields,...heroFields])];
