import type {Source} from './types';
export type SourceChanges=Record<string,unknown>;
export type SaveSource=(source:Source,changes:SourceChanges)=>Promise<Source>;
export function normalizeTags(tags:string[]){return [...new Set(tags.map(t=>t.trim()).filter(Boolean))];}

export class SourceSaveQueue {
 private tails=new Map<string,Promise<unknown>>();
 private revisions=new Map<string,Map<string,string>>();
 constructor(private request:(source:Source,changes:SourceChanges,revision:string)=>Promise<Source>,private accepted:(saved:Source)=>void){}
 save:SaveSource=(source,changes)=>{
  const run=async()=>{
   const revisions=this.revisions.get(source.id)??new Map<string,string>();
   let revision=source.revision??'';const visited=new Set<string>();
   while(revisions.has(revision)&&!visited.has(revision)){visited.add(revision);revision=revisions.get(revision)!;}
   const saved=await this.request(source,changes,revision);
   if(saved.revision!==revision)revisions.set(revision,saved.revision??'');
   this.revisions.set(source.id,revisions);this.accepted(saved);return saved;
  };
  const previous=this.tails.get(source.id)??Promise.resolve();
  const next=previous.then(run,run);this.tails.set(source.id,next);
  void next.finally(()=>{if(this.tails.get(source.id)===next)this.tails.delete(source.id);}).catch(()=>{});
  return next;
 };
}
