import type {KnowledgeDocument,KnowledgeNode,Note} from './types';

export function renderNode(n:KnowledgeNode){
 const text=n.type==='heading'?'#'.repeat(n.level)+(n.space??' ')+n.title:
  (n.show_key?(n.prefix??'**')+n.key+(n.key_suffix??'：** '):'')+n.value;
 return text+(n.separator??'\n\n');
}
export function documentMarkdown(body:KnowledgeDocument){return (body.leading??'')+body.nodes.map(renderNode).join('');}
export function copyLabel(value:string){
 const text=value.replace(/\*\*/g,'').trim().replace(/[：:]+$/,'').trim();
 return /^(?:【[^【】]+】|\[[^\[\]]+\])$/.test(text)?text.slice(1,-1).trim():text;
}
export function copyEntry(n:KnowledgeNode,body?:KnowledgeDocument,noteTitle='正文'){
 if(n.type!=='entry')throw new Error('请选择知识条目');
 const index=body?.nodes.findIndex(row=>row.id===n.id)??-1;
 const heading=body?.nodes.slice(0,index<0?0:index).reverse().find(row=>row.type==='heading');
 const key=copyLabel(n.show_key?n.key:heading?.type==='heading'?heading.title:noteTitle);
 return `${key}：${n.value}`;
}
function clipboardNode(n:KnowledgeNode){
 if(n.type==='heading')return renderNode({...n,title:copyLabel(n.title)});
 return (n.show_key?(n.prefix??'').replace(/\*\*/g,'')+copyLabel(n.key)+'：':'')+n.value+(n.separator??'\n\n');
}
export function documentClipboard(body:KnowledgeDocument){return (body.leading??'')+body.nodes.map(clipboardNode).join('');}
export function sectionClipboard(body:KnowledgeDocument,id:string){
 const start=body.nodes.findIndex(n=>n.id===id);if(start<0)return '';
 const block=body.nodes.slice(start,blockEnd(body.nodes,start)),[heading,entry]=block;
 if(block.length===2&&heading.type==='heading'&&entry.type==='entry'&&
  !/\n\s*\n|^\s*(?:[-*+]\s|\d+[.)]\s|[>|#]|`{3}|~{3}| {4})/m.test(entry.value)&&
  !/^[^\n]*\|[^\n]*\n\s*\|?\s*:?-+\s*:?\s*\|/m.test(entry.value)){
  return copyLabel(heading.title)+'：'+(entry.show_key?copyEntry(entry,body):entry.value).trim();
 }
 return block.map(clipboardNode).join('');
}
export function sectionMarkdown(body:KnowledgeDocument,id:string){
 const start=body.nodes.findIndex(n=>n.id===id);if(start<0)return '';
 const n=body.nodes[start];const level=n.type==='heading'?n.level:7;
 let end=start+1;while(end<body.nodes.length){const row=body.nodes[end];if(row.type==='heading'&&row.level<=level)break;end++;}
 return body.nodes.slice(start,end).map(renderNode).join('');
}
export function blockEnd(nodes:KnowledgeNode[],index:number){
 const node=nodes[index];if(node.type!=='heading')return index+1;
 let end=index+1;while(end<nodes.length){const n=nodes[end];if(n.type==='heading'&&n.level<=node.level)break;end++;}return end;
}
export function removeNode(nodes:KnowledgeNode[],index:number){return [...nodes.slice(0,index),...nodes.slice(blockEnd(nodes,index))];}
export function moveNode(nodes:KnowledgeNode[],index:number,offset:number){
 const node=nodes[index];if(node.type!=='heading'){
  const target=index+offset;if(target<1||target>=nodes.length)return nodes;
  const next=[...nodes];[next[index],next[target]]=[next[target],next[index]];return next;
 }
 if(node.level===1)return nodes;
 const end=blockEnd(nodes,index);
 if(offset>0){const next=nodes[end];if(!next||next.type!=='heading'||next.level!==node.level)return nodes;const nextEnd=blockEnd(nodes,end);return [...nodes.slice(0,index),...nodes.slice(end,nextEnd),...nodes.slice(index,end),...nodes.slice(nextEnd)];}
 for(let i=index-1;i>=0;i--){const previous=nodes[i];if(previous.type!=='heading')continue;if(previous.level<node.level)break;if(previous.level===node.level)return [...nodes.slice(0,i),...nodes.slice(index,end),...nodes.slice(i,index),...nodes.slice(end)];}
 return nodes;
}
export function playerGroups(notes:Note[]){
 const names=new Map(notes.filter(n=>n.type==='player'&&n.player_id).map(n=>[n.player_id!,n.title]));
 const groups=new Map<string,{id:string;name:string;notes:Note[]}>();
 for(const n of notes){
  const players=n.player_id?[n.player_id]:(n.meta?.players??[]);
  for(const id of players){
   const name=names.get(id)??n.title.split('-').at(-1)??id;
   if(!groups.has(id))groups.set(id,{id,name,notes:[]});groups.get(id)!.notes.push(n);
  }
 }
 return [...groups.values()].map(g=>({...g,notes:g.notes.sort((a,b)=>Number(b.type==='player')-Number(a.type==='player'))}));
}
