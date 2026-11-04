import {sessionFetch} from './sessionRequest';
import {useEffect,useRef,useState} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {apiUrl} from './urls';
import type {KnowledgeNode} from './types';
export type Resource={kind:'entry';id:string}|{kind:'slot';section_id:string;left_id:string};
export type Lease={id:string;token:string;resource:Resource;baseline:{node?:KnowledgeNode;section:KnowledgeNode[];left_id?:string;right_id?:string|null};expires_at:number};
type Presence={id:string;resource:Resource;owner:string;role:string;mine:boolean};
type View={epoch:string;leases:Presence[];revoked:{id:string;reason:string;resource:Resource}[]};
export const resourceKey=(target:Resource)=>JSON.stringify(target.kind==='entry'?['entry',target.id]:['slot',target.section_id,target.left_id]);
// A new document gets a fresh identity, including duplicated tabs with copied sessionStorage.
export const editClientId=crypto.randomUUID();
export const leaseRef=(lease:Lease)=>({id:lease.id,token:lease.token});
export function useEditLocks(noteId?:string,onLost?:(lease:Lease,reason:string)=>void){
 const clientId=useRef(editClientId+'_'+crypto.randomUUID()).current;
 const {session}=useAuth(),own=useRef(new Map<string,Lease>()),lost=useRef(onLost);lost.current=onLost;
 const [presence,setPresence]=useState<Presence[]>([]),[online,setOnline]=useState(true),[version,setVersion]=useState(0);
 const alive=useRef(true),generation=useRef(0),connected=useRef(true);
 function connectivity(value:boolean){connected.current=value;setOnline(value);}
 const bump=()=>{if(alive.current)setVersion(v=>v+1);};
 function invalidate(lease:Lease,reason:string){own.current.delete(resourceKey(lease.resource));lost.current?.(lease,reason);bump();}
 async function release(target?:Resource){const leases=target?[own.current.get(resourceKey(target))].filter((x):x is Lease=>!!x):[...own.current.values()];for(const lease of leases)own.current.delete(resourceKey(lease.resource));bump();if(leases.length)await api('edit-locks/release','POST',{client_id:clientId,leases:leases.map(leaseRef)}).catch(()=>{});}
 async function acquire(target:Resource,takeover=false){
  const epoch=generation.current;
  const lease=await api<Lease>('edit-locks/acquire','POST',{note_id:noteId,client_id:clientId,resource:target,takeover});
  if(epoch!==generation.current||!alive.current){void api('edit-locks/release','POST',{client_id:clientId,leases:[leaseRef(lease)]});throw new Error('编辑窗口已关闭');}
  own.current.set(resourceKey(target),lease);connectivity(true);bump();return lease;
 }
 useEffect(()=>{
  alive.current=true;generation.current++;let live=true,polling=false,renewing=false;
  if(!noteId||!['admin','annotator'].includes(session.role))return;
  async function poll(){if(polling)return;polling=true;const observed=new Set([...own.current.values()].map(l=>l.id));try{const view=await api<View>('edit-locks?note_id='+encodeURIComponent(noteId!)+'&client_id='+clientId);if(!live)return;setPresence(view.leases);if(!own.current.size)connectivity(true);else if(!connected.current)await renew();for(const lease of [...own.current.values()]){if(!observed.has(lease.id))continue;const revoked=view.revoked.find(r=>r.id===lease.id);if(revoked)invalidate(lease,revoked.reason);else if(!view.leases.some(p=>p.id===lease.id))invalidate(lease,'expired');}}catch{if(live)connectivity(false);}finally{polling=false;}}
  async function renew(){if(renewing||!own.current.size)return;renewing=true;try{const result=await api<{leases:Lease[];lost:{id:string;reason:string}[]}>('edit-locks/renew','POST',{client_id:clientId,leases:[...own.current.values()].map(leaseRef)});if(!live)return;for(const item of result.lost){const lease=[...own.current.values()].find(l=>l.id===item.id);if(lease)invalidate(lease,item.reason);}for(const lease of result.leases)if(own.current.get(resourceKey(lease.resource))?.id===lease.id)own.current.set(resourceKey(lease.resource),lease);connectivity(true);bump();}catch{if(live)connectivity(false);}finally{renewing=false;}}
  void poll();const p=setInterval(()=>{if(document.visibilityState==='visible')void poll();},2000),r=setInterval(()=>void renew(),15000);
  const pagehide=()=>{const leases=[...own.current.values()].map(leaseRef);if(leases.length)void sessionFetch(apiUrl('edit-locks/release'),{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:clientId,leases})});};
  window.addEventListener('pagehide',pagehide);
  return()=>{live=false;alive.current=false;generation.current++;clearInterval(p);clearInterval(r);window.removeEventListener('pagehide',pagehide);void release();};
 },[noteId,session.role,session.username]);
 return {clientId,presence,online,version,acquire,release,get:(target:Resource)=>{const l=own.current.get(resourceKey(target));return online&&l&&l.expires_at*1000>Date.now()?l:undefined;},owner:(target:Resource)=>presence.find(p=>resourceKey(p.resource)===resourceKey(target)&&!p.mine)};
}
