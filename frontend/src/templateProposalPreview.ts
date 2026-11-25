import {applyTemplateGroupFields,groupDiffKeys,type TemplateChange,type TemplateEvent,type TemplateGroup,type TemplateProposal} from './templates';

export type TemplateProposalPreview={
 proposal_id:string;author:string;created_at:string;source?:string|null;proposal_revision?:string;change_index?:number;
 change:TemplateChange;base:TemplateGroup|null;event?:TemplateEvent;review_status_changed?:boolean;inline_trigger?:boolean;
};

export function newestProposalFirst<T extends {created_at:string}>(a:T,b:T){
 return Date.parse(b.created_at)-Date.parse(a.created_at);
}

export function proposalCardPreview(proposal:TemplateProposal,id:string):TemplateProposalPreview|undefined{
 if(proposal.status!=='pending')return;
 const change_index=proposal.changes.findIndex(change=>change.kind==='group'&&change.id===id);
 const change=proposal.changes[change_index];
 if(!change)return;
 const base=proposal.base.groups.find(group=>group.id===id)??null;
 const next=change.value as TemplateGroup|undefined;
 const event=proposal.changes.find(change=>change.kind==='event'&&change.action==='put'&&change.id===(next??base)?.event_id)?.value as TemplateEvent|undefined;
 return {proposal_id:proposal.id,author:proposal.author,created_at:proposal.created_at,source:proposal.source,
  proposal_revision:proposal.proposal_revision,change_index,change,base,event,
  review_status_changed:Object.hasOwn(proposal.group_review_overrides??{},id),...(proposal.inline_trigger?{inline_trigger:true}:{})};
}

export function projectProposalCard(original:TemplateGroup,preview:TemplateProposalPreview){
 const next=preview.change.value as TemplateGroup|undefined;
 if(preview.change.action==='delete'||!next)return {group:original,fields:new Set<string>(),deleted:true,newGroup:false,removedUtterances:[] as string[],removedConditions:[] as string[]};
 if(!preview.base)return {group:next,fields:new Set<string>(),deleted:false,newGroup:true,removedUtterances:[] as string[],removedConditions:[] as string[]};
 const fields=preview.source==='review-status'?['review_status']:groupDiffKeys(preview.base,next);
 if(preview.review_status_changed&&!fields.includes('review_status'))fields.push('review_status');
 const group=applyTemplateGroupFields(original,next,fields);
 if(fields.includes('review_status'))group.review_status=next.review_status;
 const removedUtterances=original.utterances.filter(row=>fields.includes('utterance:'+row.id)&&!next.utterances.some(item=>item.id===row.id));
 const removedConditions=original.conditions.filter(row=>fields.includes('condition:'+row.id)&&!next.conditions.some(item=>item.id===row.id));
 const restoredRows=<T extends {id:string}>(rows:T[],removed:T[],before:T[])=>{
  const result=[...rows];
  for(const row of removed)result.splice(Math.min(before.findIndex(item=>item.id===row.id),result.length),0,row);
  return result;
 };
 return {group:{...group,utterances:restoredRows(group.utterances,removedUtterances,original.utterances),
  conditions:restoredRows(group.conditions,removedConditions,original.conditions)},fields:new Set(fields),deleted:false,newGroup:false,
  removedUtterances:removedUtterances.map(row=>row.id),removedConditions:removedConditions.map(row=>row.id)};
}

export function proposalLocationChanges(proposal:TemplateProposal){
 const byTarget=new Map<string,TemplateChange>();
 for(const change of [...proposal.changes,...proposal.history_targets??[],...proposal.submission?.changes??[],...(proposal.reviews??[]).flatMap(review=>review.changes??[])]){
  const key=change.kind+':'+change.id;
  if(!byTarget.has(key))byTarget.set(key,change);
 }
 return [...byTarget.values()];
}
