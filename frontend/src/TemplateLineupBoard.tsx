import {templateReviewLabels,type TemplateFilters,type TemplateGroup} from './templates';
import {parseFileConditionText} from './templateConditionText';
import {lineupName,namedConditionValues,readV04Condition,type ConditionNodeV04} from './templateV04';
import type {TemplateEntityEntry} from './templateEntityIndex';
import {TemplateFilterPopup} from './TemplateFilters';

type Scope={lineups?:string[];players?:string[];playerRestricted?:boolean};
export type LineupTabs=Map<string,Map<string,Set<string>>>;
export const unscopedLineup='未限定阵容';
export type LineupDrill={kind:'entity'|'event';key:string;event?:string};
type BoardFilters=Pick<TemplateFilters,'review_status'|'onlyFixed'|'hideIgnored'>;

function intersect(left?:string[],right?:string[]){
 return left&&right?left.filter(value=>right.includes(value)):left??right;
}

function mentionsPlayer(node:ConditionNodeV04):boolean{
 if(node.kind==='path')return node.parts.join('.')==='我方.棋手名称';
 if(node.kind==='binary')return mentionsPlayer(node.left)||mentionsPlayer(node.right);
 if(node.kind==='negation')return mentionsPlayer(node.child);
 return node.kind==='call'&&node.args.some(mentionsPlayer);
}

function alternatives(node:ConditionNodeV04):Scope[]|undefined{
 if(node.kind==='binary'&&(node.op==='and'||node.op==='or')){
  const left=alternatives(node.left),right=alternatives(node.right);
  if(!left||!right)return;
  if(node.op==='or')return left.length+right.length<=128?[...left,...right]:undefined;
  if(left.length*right.length>128)return;
  return left.flatMap(a=>right.map(b=>({
   lineups:intersect(a.lineups,b.lineups),players:intersect(a.players,b.players),
   playerRestricted:a.playerRestricted||b.playerRestricted,
  })).filter(scope=>scope.lineups?.length!==0&&scope.players?.length!==0));
 }
 const binding=namedConditionValues(node);
 if(binding?.path.join('.')==='我方.阵容名称')return [{lineups:binding.values.map(lineupName)}];
 if(binding?.path.join('.')==='我方.棋手名称')return [{players:binding.values,playerRestricted:true}];
 return [{playerRestricted:mentionsPlayer(node)}];
}

export function buildLineupTabs(groups:TemplateGroup[],scopeName:(id:string)=>string,includeUnscoped=false):LineupTabs{
 const result:LineupTabs=new Map();
 for(const group of groups){
  const lineup=group.scope.lineup_note_id,player=group.scope.player_id;
  const boundLineup=lineup?[lineupName(scopeName(lineup))]:undefined;
  const boundPlayer=player?[scopeName(player)]:undefined;
  const expression=readV04Condition(group.expression);
  const legacy=group.syntax_version==='0.4'?undefined:parseFileConditionText(group.expression??'');
  const clauses:Scope[]|undefined=legacy?[{lineups:legacy.lineup?[lineupName(legacy.lineup)]:undefined,
   players:legacy.player?[legacy.player]:undefined,playerRestricted:!!legacy.player||/玩家\s*\.\s*使用棋手/u.test(legacy.expression)}]
   :expression?alternatives(expression):[{}];
  if(!clauses)continue;
  const scopes=clauses.map(clause=>({
   lineups:intersect(boundLineup,clause.lineups),players:intersect(boundPlayer,clause.players),
   playerRestricted:clause.playerRestricted||!!boundPlayer,
  })).filter(scope=>scope.lineups?.length!==0&&scope.players?.length!==0);
  if(scopes.some(scope=>!scope.lineups)){
   if(!includeUnscoped||scopes.some(scope=>scope.lineups))continue;
   for(const scope of scopes)scope.lineups=[unscopedLineup];
  }
  for(const name of new Set(scopes.flatMap(scope=>scope.lineups??[]))){
   const applicable=scopes.filter(scope=>scope.lineups?.includes(name));
   const tabs=applicable.every(scope=>!scope.playerRestricted)?['']:
    applicable.every(scope=>scope.players?.length)?[...new Set(applicable.flatMap(scope=>scope.players??[]))]:[];
   for(const tab of tabs){
    const lineupTabs=result.get(name)??new Map<string,Set<string>>();
    const ids=lineupTabs.get(tab)??new Set<string>();
    ids.add(group.id);lineupTabs.set(tab,ids);result.set(name,lineupTabs);
   }
  }
 }
 return result;
}

const columns=[['heroes','英雄'],['talents','天赋'],['equipment','装备'],['effect-cards','效果牌']] as const;
export function lineupBoardRows(groups:TemplateGroup[],entries:TemplateEntityEntry[]){
 const byId=new Map(groups.map(group=>[group.id,group.event_id]));
 const covered=new Set<string>();
 const cards=entries.flatMap(entity=>{
  if(!columns.some(([category])=>category===entity.category))return [];
  const events=new Map<string,Set<string>>(),ids=new Set<string>();
  for(const id of entity.groupIds){
   const event=byId.get(id);
   if(event===undefined)continue;
   ids.add(id);covered.add(id);
   const members=events.get(event)??new Set<string>();
   members.add(id);events.set(event,members);
  }
  return ids.size?[{entity,events,ids}]:[];
 });
 const other=new Map<string,Set<string>>();
 for(const [id,event] of byId){
  if(covered.has(id))continue;
  const ids=other.get(event)??new Set<string>();
  ids.add(id);other.set(event,ids);
 }
 return {cards,other,reviews:new Map(groups.map(group=>[group.id,group.review_status]))};
}

export function TemplateLineupSidebar({names,tabs,query,selected,player,onQuery,onSelect}:{names:string[];tabs:LineupTabs;query:string;
 selected:string;player:string;onQuery:(query:string)=>void;onSelect:(name:string,player:string)=>void}){
 const terms=query.trim().toLocaleLowerCase().split(/\s+/u);
 const match=(name:string)=>terms.every(term=>name.toLocaleLowerCase().includes(term));
 const matches=names.flatMap(name=>{
  const branches=[...(tabs.get(name)?.keys()??[])].filter(Boolean).sort((a,b)=>a.localeCompare(b,'zh-CN'));
  return ['',...branches].flatMap(branch=>{
   const label=branch?name+'-'+branch:name;
   return match(label)?[{name,branch,label}]:[];
  });
 });
 const unscoped=tabs.has(unscopedLineup);
 return <aside className="template-events template-lineup-sidebar" aria-label="阵容列表">
  <label className="template-entity-search">搜索阵容<input type="search" value={query} onChange={e=>onQuery(e.target.value)}/></label>
  {unscoped&&<button type="button" className={'template-lineup-unscoped'+(selected===unscopedLineup?' selected':'')}
   aria-pressed={selected===unscopedLineup} onClick={()=>onSelect(unscopedLineup,'')}>{unscopedLineup}</button>}
  {matches.map(({name,branch,label})=>{
   const active=selected===name&&player===branch;
   return <button key={label} type="button" aria-pressed={active}
    className={(branch?'template-lineup-branch ':'')+(active?'selected':'')} onClick={()=>onSelect(name,branch)}>{label}</button>;
  })}
  {!matches.length&&<p className="muted">没有符合条件的阵容。</p>}
 </aside>;
}

export default function TemplateLineupBoard({name,players,player,filters,rows,eventNames,onPlayer,onFilter,onDrill}:{
 name:string;players:string[];player:string;filters:BoardFilters;rows:ReturnType<typeof lineupBoardRows>;
 eventNames:ReadonlyMap<string,string>;onPlayer:(player:string)=>void;onFilter:(filters:BoardFilters)=>void;onDrill:(drill:LineupDrill)=>void;
}){
 if(!name)return <p className="empty">当前没有明确归属阵容的模板组。</p>;
 const eventName=(id:string)=>(eventNames.get(id)??id).replace(/^解释为何\s*/u,'');
 const activeFilters=Number(!!filters.review_status)+Number(!!filters.onlyFixed)+Number(filters.hideIgnored===false);
 function counts(ids:Set<string>){
  let initial=0,final=0;
  for(const id of ids){
   const status=rows.reviews.get(id);
   if(status==='initial_reviewed')initial++;
   if(status==='final_reviewed')final++;
  }
  return <span className="template-lineup-counts">
   <span title="总数" aria-label={'总数 '+ids.size}>{ids.size}</span>
   <span title="初核完成" aria-label={'初核完成 '+initial}>{initial}</span>
   <span title="复核完成" aria-label={'复核完成 '+final}>{final}</span>
  </span>;
 }
 return <>
  <div className="template-lineup-heading"><h2>{name}</h2>
   <div role="group" aria-label="阵容棋手">{['',...players].map(tab=>
    <button key={tab} type="button" aria-pressed={tab===player} onClick={()=>onPlayer(tab)}>{tab||'通用'}</button>)}</div>
   <div className="template-lineup-filters"><TemplateFilterPopup active={activeFilters}>
    <label className="template-lineup-review">审核状态 <select value={filters.review_status??''} onChange={e=>onFilter({review_status:e.target.value as BoardFilters['review_status']})}>
     <option value="">全部状态</option><option value="unmarked">未标记</option>
     {Object.entries(templateReviewLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}
    </select></label>
    <label className="template-filter-toggle"><input type="checkbox" checked={!!filters.onlyFixed}
     onChange={e=>onFilter({onlyFixed:e.target.checked})}/>只显示固定话术</label>
    <label className="template-filter-toggle"><input type="checkbox" checked={filters.hideIgnored??true}
     onChange={e=>onFilter({hideIgnored:e.target.checked})}/>隐藏忽略内容</label>
   </TemplateFilterPopup></div>
  </div>
  <div className="template-lineup-columns" data-lineup-scroll="columns">
   {columns.map(([category,label])=>{
    const cards=rows.cards.filter(card=>card.entity.category===category);
    return <section key={category} aria-label={label}><h3>{label}</h3><div className="template-lineup-column-cards" data-lineup-scroll={category} tabIndex={0} aria-label={label+'模板'}>
     {cards.map(({entity,ids,events})=><article className="template-lineup-card" key={entity.key}>
      <button type="button" onClick={()=>onDrill({kind:'entity',key:entity.key})}><strong>{entity.name}</strong>
       {category==='talents'&&counts(ids)}</button>
      {category!=='talents'&&[...events].map(([event,members])=><button key={event} type="button"
       onClick={()=>onDrill({kind:'entity',key:entity.key,event})}><span>{eventName(event)}</span>{counts(members)}</button>)}
     </article>)}
     {!cards.length&&<p className="muted">暂无模板</p>}
    </div></section>;
   })}
   <section aria-label="其他"><h3>其他</h3><div className="template-lineup-column-cards" data-lineup-scroll="other" tabIndex={0} aria-label="其他模板">
    {[...rows.other].map(([event,ids])=><article className="template-lineup-card" key={event}>
     <button type="button" onClick={()=>onDrill({kind:'event',key:event})}><strong>{eventName(event)}</strong>{counts(ids)}</button>
    </article>)}
    {!rows.other.size&&<p className="muted">暂无模板</p>}
   </div></section>
  </div>
 </>;
}
