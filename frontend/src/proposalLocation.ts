import {api} from './model';
import {detailPath,readingPath} from './useReaderLoader';
import type {Note,ReadingDocument} from './types';
import type {Proposal} from './Proposals';

export function locationCandidates(item:Proposal){
 return [...new Set([item.node_id,...(item.kind==='insert'?[item.after_id]:[]),item.section_id].filter((id):id is string=>!!id))];
}
export async function loadProposalLocation(item:Proposal,player?:string){
 for(let attempt=0;attempt<2;attempt++){
  const [note,reading]=await Promise.all([api<Note>(detailPath(item.note_id,player)),api<ReadingDocument>(readingPath(item.note_id,player))]);
  if(note.id===item.note_id&&reading.note_id===note.id&&note.revision===reading.revision&&Array.isArray(reading.sections))return {note,reading};
 }
 throw new Error('笔记正在更新，请稍后重试定位');
}
export function findReadingNode(root:HTMLElement,id:string){
 return root.querySelector<HTMLElement>(`[data-node="${CSS.escape(id)}"],#${CSS.escape(id)}`);
}
export function revealReadingNode(target:HTMLElement){
 const previous=target.getAttribute('tabindex');target.setAttribute('tabindex','-1');target.classList.add('proposal-location-target');
 target.scrollIntoView({block:'center',behavior:'instant'});target.focus({preventScroll:true});
 const clear=()=>{target.classList.remove('proposal-location-target');if(previous===null)target.removeAttribute('tabindex');else target.setAttribute('tabindex',previous);};
 const timer=setTimeout(clear,2500);return()=>{clearTimeout(timer);clear();};
}
