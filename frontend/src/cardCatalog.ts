import {activeWorkspace,cachedGet} from './readerCache';
import {onSessionReset,requestGeneration} from './sessionRequest';
import type {CardSummary} from './types';

const pending=new Map<string,Promise<CardSummary[]>>();
onSessionReset(()=>pending.clear());
/** Coalesce card enhancement reads without sharing knowledge across identities/workspaces. */
export function loadCardCatalog(workspace=activeWorkspace()){
 const key=requestGeneration()+'|'+workspace;
 let request=pending.get(key);
 if(!request){
  request=cachedGet<CardSummary[]>('cards',{workspace});pending.set(key,request);
  const clear=()=>{if(pending.get(key)===request)pending.delete(key);};
  void request.then(clear,clear);
 }
 return request;
}
