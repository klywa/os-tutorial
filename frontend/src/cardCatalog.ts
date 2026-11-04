import {activeWorkspace,cachedGet} from './readerCache';
import {onSessionReset,requestGeneration,assertRequestGeneration} from './sessionRequest';
import {api} from './model';
import type {CardSummary} from './types';

const pending=new Map<string,Promise<CardSummary[]>>();
const versions=new Map<string,string>();
const statusRequests=new Map<string,Promise<CardStatus>>();
export type CardStatus={version:string;state:string;last_check?:string;last_success?:string;next_check?:string;error?:string|null};
onSessionReset(()=>{pending.clear();versions.clear();statusRequests.clear();});
export function cardVersion(workspace=activeWorkspace()){return versions.get(workspace)||'';}
export function cardPath(id:string,version=cardVersion()){return 'cards/'+encodeURIComponent(id)+(version?'?version='+encodeURIComponent(version):'');}
export function checkCardVersion(){
 const epoch=requestGeneration(),workspace=activeWorkspace(),key=epoch+'|'+workspace;
 const old=statusRequests.get(key);if(old)return old;
 const request=api<CardStatus>('cards/status').then(value=>{assertRequestGeneration(epoch);versions.set(workspace,value.version);return value;});
 statusRequests.set(key,request);
 const clear=()=>{if(statusRequests.get(key)===request)statusRequests.delete(key);};void request.then(clear,clear);return request;
}
/** Coalesce card enhancement reads without sharing knowledge across identities/workspaces. */
export function loadCardCatalog(workspace=activeWorkspace()){
 const epoch=requestGeneration(),version=cardVersion(workspace),key=epoch+'|'+workspace+'|'+version;
 let request=pending.get(key);
 if(!request){
  request=cachedGet<CardSummary[]>('cards'+(version?'?version='+encodeURIComponent(version):''),{workspace}).then(cards=>{
   assertRequestGeneration(epoch);if(cardVersion(workspace)!==version)throw new Error('卡牌版本已更新，请重新载入');
   const result=version?cards.map(card=>({...card,catalog_version:version})):cards;
   if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('cards-catalog',{detail:{cards:result,workspace,epoch,version}}));return result;
  });pending.set(key,request);
  const clear=()=>{if(pending.get(key)===request)pending.delete(key);};
  void request.then(clear,clear);
 }
 return request;
}
