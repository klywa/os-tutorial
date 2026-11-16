/** A reading instance owns this store; only affected anchors receive updates. */
export class DockSelection {
 private value={active:'',pinned:false};
 private searching=false;
 private searchEpoch=0;
 private listeners=new Map<string,Set<()=>void>>();
 snapshot=()=>this.value;
 subscribe=(token:string,listener:()=>void)=>{
  const group=this.listeners.get(token)??new Set();group.add(listener);this.listeners.set(token,group);
  return ()=>{group.delete(listener);if(!group.size)this.listeners.delete(token);};
 };
 private update(active:string,pinned:boolean){
  const previous=this.value;if(previous.active===active&&previous.pinned===pinned)return;
  this.value={active,pinned};
  for(const token of new Set(['',previous.active,active]))this.listeners.get(token)?.forEach(run=>run());
 }
 setSearching=(searching:boolean)=>{
  if(this.searching===searching)return;
  this.searching=searching;
  this.searchEpoch++;
  if(searching)this.close();
 };
 preview=(token:string)=>{
  const epoch=this.searchEpoch;
  return ()=>{if(epoch===this.searchEpoch)this.select(token,false);};
 };
 select=(token:string,pin:boolean)=>{if(this.searching||(this.value.pinned&&!pin))return;this.update(token,pin);};
 close=()=>this.update('',false);
 toggle=()=>this.update(this.value.active,!this.value.pinned);
}
