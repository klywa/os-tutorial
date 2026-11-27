import type {LocalDirectoryHandle,LocalFileHandle} from './templateFile';

export type RecentTemplateFile={id:string;handle:LocalFileHandle;directory?:LocalDirectoryHandle;openedAt:number};
const storeName='history';
let database:Promise<IDBDatabase|null>|undefined;
let memory:RecentTemplateFile[]=[];
let writes=Promise.resolve();

function openHistory(){
 return database??=new Promise(resolve=>{
  try{
   const request=indexedDB.open('wxq.template-files',1);
   request.onupgradeneeded=()=>request.result.createObjectStore(storeName);
   request.onsuccess=()=>resolve(request.result);
   request.onerror=request.onblocked=()=>resolve(null);
  }catch{resolve(null);}
 });
}

export async function sameTemplateFile(first:LocalFileHandle,second:LocalFileHandle){
 if(first===second)return true;
 try{return await first.isSameEntry?.(second)??false;}catch{return false;}
}

export async function recentTemplateFiles(){
 const db=await openHistory();
 if(!db)return memory;
 return new Promise<RecentTemplateFile[]>(resolve=>{
  try{
   const request=db.transaction(storeName).objectStore(storeName).get('recent');
   request.onsuccess=()=>resolve(memory.length?memory:request.result??[]);
   request.onerror=()=>resolve(memory);
  }catch{resolve(memory);}
 });
}

export async function addRecentTemplateFile(entries:RecentTemplateFile[],entry:RecentTemplateFile){
 const same=await Promise.all(entries.map(row=>sameTemplateFile(row.handle,entry.handle)));
 return [{...entry,id:entries[same.indexOf(true)]?.id??entry.id},...entries.filter((_,i)=>!same[i])].slice(0,10);
}

export function rememberRecentTemplateFile(entry:RecentTemplateFile){
 const save=writes.then(async()=>{
  memory=await addRecentTemplateFile(await recentTemplateFiles(),entry);
  const db=await openHistory();
  if(db)await new Promise<void>(resolve=>{
   try{
    const transaction=db.transaction(storeName,'readwrite');
    transaction.oncomplete=transaction.onabort=transaction.onerror=()=>resolve();
    transaction.objectStore(storeName).put(memory,'recent');
   }catch{resolve();}
  });
  return memory;
 });
 writes=save.then(()=>undefined,()=>undefined);
 return save;
}
