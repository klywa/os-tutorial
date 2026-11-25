export async function readNoteJson(file: File): Promise<unknown> {
 if(file.size>2_000_000)throw new Error('JSON 文件超过 2 MB');
 const raw=(await file.text()).replace(/^\uFEFF/,'');
 try{return JSON.parse(raw);}catch{throw new Error('无法读取 JSON，请检查文件格式');}
}

function object(value:unknown):value is Record<string,unknown>{
 return value!==null&&typeof value==='object'&&!Array.isArray(value);
}

export function describeNewNoteJson(value:unknown){
 if(!object(value))throw new Error('请选择知识笔记 JSON 对象');
 let item=value;
 if('notes' in item){
  if(!Array.isArray(item.notes)||item.notes.length!==1||!object(item.notes[0])||!('body' in item.notes[0]))
   throw new Error('上传包必须只含一篇知识笔记');
  item=item.notes[0];
 }
 const body='body' in item?item.body:item;
 const metadata='body' in item&&'metadata' in item?item.metadata:{};
 if(!object(metadata))throw new Error('笔记附件必须为对象');
 if(!object(body)||body.schema_version!==6||!Array.isArray(body.nodes))
  throw new Error('正文必须是版本 6 结构化 JSON');
 const titles:string[]=[],parts:string[]=[];
 for(const node of body.nodes){
  if(!object(node))throw new Error('正文节点格式无效');
  if(node.type==='heading'&&typeof node.title==='string'&&typeof node.level==='number'){
   if(node.level===1)titles.push(node.title);
   parts.push(node.title);
  }else if(node.type==='entry'&&typeof node.key==='string'&&typeof node.value==='string'){
   parts.push((node.show_key?node.key+'：':'')+node.value);
  }else throw new Error('正文节点格式无效');
 }
 if(titles.length!==1)throw new Error('正文必须包含唯一的一级标题');
 const text=parts.join('\n\n');
 return {metadata,title:typeof metadata.title==='string'?metadata.title:titles[0],
  preview:text.slice(0,20_000),truncated:text.length>20_000};
}
