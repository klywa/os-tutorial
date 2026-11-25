import {templateReviewLabels,type TemplateEvent,type TemplateFilters,type TemplateGroup} from './templates';
import {parseFileConditionText} from './templateConditionText';
import {catalogV04,lineupName,namedConditionValues,readV04Condition,type ConditionNodeV04} from './templateV04';
import type {TemplateEntityEntry} from './templateEntityIndex';
import {TemplateFilterPopup} from './TemplateFilters';

type Scope={lineups?:string[];players?:string[];playerRestricted?:boolean;lineupRestricted?:boolean};
export type LineupTabs=Map<string,Map<string,Set<string>>>;
export const unscopedLineup='未限定阵容';
export type LineupDrill={kind:'entity'|'event'|'column'|'generalHero';key:string;event?:string};
export const generalHeroLabel='通用英雄事件';
type BoardFilters=Pick<TemplateFilters,'review_status'|'onlyFixed'|'hideIgnored'>;
type ReviewCounts=readonly [total:number,initial:number,final:number];
const countLabels=['总数','初核完成','复核完成'];

export function lineupTemplateCounts(ids:ReadonlySet<string>,reviews:ReadonlyMap<string,TemplateGroup['review_status']>):ReviewCounts{
 let initial=0,final=0;
 for(const id of ids){
  const status=reviews.get(id);
  if(status==='initial_reviewed')initial++;
  if(status==='final_reviewed')final++;
 }
 return [ids.size,initial,final];
}

function LineupCounts({counts}:{counts:ReviewCounts}){
 return <span className="template-lineup-counts">{counts.map((count,index)=><span key={countLabels[index]}
  title={countLabels[index]} aria-label={countLabels[index]+' '+count}>{count}</span>)}</span>;
}

const describeCounts=(counts:ReviewCounts)=>counts.map((count,index)=>countLabels[index]+' '+count).join('，');

function intersect(left?:string[],right?:string[]){
 return left&&right?left.filter(value=>right.includes(value)):left??right;
}

function mentionsScope(node:ConditionNodeV04,path:string):boolean{
 if(node.kind==='path')return node.parts.join('.')===path;
 if(node.kind==='binary')return mentionsScope(node.left,path)||mentionsScope(node.right,path);
 if(node.kind==='negation')return mentionsScope(node.child,path);
 return node.kind==='call'&&node.args.some(child=>mentionsScope(child,path));
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
   lineupRestricted:a.lineupRestricted||b.lineupRestricted,
  })).filter(scope=>scope.lineups?.length!==0&&scope.players?.length!==0));
 }
 const binding=namedConditionValues(node);
 if(binding?.path.join('.')==='我方.阵容名称')return [{lineups:binding.values.map(lineupName)}];
 if(binding?.path.join('.')==='我方.棋手名称')return [{players:binding.values,playerRestricted:true}];
 return [{playerRestricted:mentionsScope(node,'我方.棋手名称'),lineupRestricted:mentionsScope(node,'我方.阵容名称')}];
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
   players:legacy.player?[legacy.player]:undefined,playerRestricted:!!legacy.player||/玩家\s*\.\s*使用棋手/u.test(legacy.expression),
   lineupRestricted:/玩家\s*\.\s*使用阵容/u.test(legacy.expression)}]
   :expression?alternatives(expression):[{}];
  if(!clauses)continue;
  const scopes=clauses.map(clause=>({
   lineups:intersect(boundLineup,clause.lineups),players:intersect(boundPlayer,clause.players),
   playerRestricted:clause.playerRestricted||!!boundPlayer,lineupRestricted:clause.lineupRestricted,
  })).filter(scope=>scope.lineups?.length!==0&&scope.players?.length!==0);
  if(scopes.some(scope=>!scope.lineups)){
   if(!includeUnscoped||scopes.some(scope=>scope.lineups||scope.lineupRestricted))continue;
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

type LineupRosterNote={title:string;lineup_name?:string;player_id?:string;lineup_heroes?:string[]};
export function lineupRosterName(note:LineupRosterNote,playerName:(id:string)=>string){
 if(note.lineup_name)return lineupName(note.lineup_name);
 const name=lineupName(note.title);
 const suffix=note.player_id?'-'+playerName(note.player_id):'';
 return suffix&&name.endsWith(suffix)?lineupName(name.slice(0,-suffix.length)):name;
}
export function addLineupRosters(tabs:LineupTabs,notes:LineupRosterNote[],playerName:(id:string)=>string,includeNoteTabs=true){
 const rosters=new Map<string,Map<string,Set<string>>>();
 for(const note of notes){
  const name=lineupRosterName(note,playerName);
  const player=note.player_id?playerName(note.player_id):'';
  const lineup=tabs.get(name);
  if(!includeNoteTabs&&(!lineup||player&&[...lineup.keys()].some(Boolean)&&!lineup.has(player)))continue;
  const branches=rosters.get(name)??new Map<string,Set<string>>();
  const heroes=branches.get(player)??new Set<string>();
  for(const hero of note.lineup_heroes??[])heroes.add(hero);
  branches.set(player,heroes);rosters.set(name,branches);
  if(includeNoteTabs){
   const noteTabs=lineup??new Map<string,Set<string>>();
   if(!noteTabs.has(player))noteTabs.set(player,new Set());
   tabs.set(name,noteTabs);
  }
 }
 return rosters;
}

export function lineupRosterNames(rosters:ReturnType<typeof addLineupRosters>,name:string,player:string){
 const branches=rosters.get(name);
 const shared=branches?.get('');
 return new Set(player?[...(shared??[]),...(branches?.get(player)??[])]:shared??[...(branches?.values()??[])].flatMap(values=>[...values]));
}

const columns=[['heroes','英雄'],['talents','天赋'],['equipment','装备'],['effect-cards','效果牌']] as const;
export function lineupBoardRows(groups:TemplateGroup[],entries:TemplateEntityEntry[],heroNames:ReadonlySet<string>=new Set(),fallback:TemplateGroup[]=[],events:TemplateEvent[]=[]){
 const byId=new Map(groups.map(group=>[group.id,group.event_id]));
 const fallbackEvents=new Map(fallback.map(group=>[group.id,group.event_id]));
 const covered=new Set<string>();
 const cards=entries.flatMap(entity=>{
  if(!columns.some(([category])=>category===entity.category))return [];
  const lineupHero=entity.category==='heroes'&&heroNames.has(entity.name);
  const events=new Map<string,Set<string>>(),ids=new Set<string>();
  for(const id of entity.groupIds){
   const event=byId.get(id)??(lineupHero?fallbackEvents.get(id):undefined);
   if(event===undefined)continue;
   ids.add(id);covered.add(id);
   const members=events.get(event)??new Set<string>();
   members.add(id);events.set(event,members);
  }
  return ids.size||lineupHero?[{entity,events,ids}]:[];
 });
 const heroEvents=new Set(events.filter(({name})=>{
  const action=catalogV04.events[name]?.action;
  return action==='上阵英雄'||action==='合成英雄'||action==='出售英雄'||action==='移动站位'||
   (action==='购买'||action==='拍卖'||action==='选择')&&name.includes('英雄');
 }).map(event=>event.id));
 const other=new Map<string,Set<string>>(),generalHeroEvents=new Map<string,Set<string>>();
 const generalHeroIds=new Set<string>();
 for(const [id,event] of byId){
  if(covered.has(id))continue;
  const target=heroEvents.has(event)?generalHeroEvents:other;
  const ids=target.get(event)??new Set<string>();
  ids.add(id);target.set(event,ids);
  if(target===generalHeroEvents)generalHeroIds.add(id);
 }
 const columnIds=new Map<string,Set<string>>(columns.map(([category])=>[category,
  new Set(cards.filter(row=>row.entity.category===category).flatMap(row=>[...row.ids]))]));
 columnIds.set('other',new Set([...other.values()].flatMap(ids=>[...ids])));
 for(const id of generalHeroIds)columnIds.get('heroes')!.add(id);
 return {cards,other,generalHeroEvents,generalHeroIds,columnIds,reviews:new Map([...groups,...fallback].map(group=>[group.id,group.review_status]))};
}

export function TemplateLineupSidebar({names,tabs,query,selected,player,counts,onQuery,onSelect}:{names:string[];tabs:LineupTabs;query:string;
 selected:string;player:string;counts:(name:string,player:string)=>ReviewCounts;onQuery:(query:string)=>void;onSelect:(name:string,player:string)=>void}){
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
 function item(name:string,branch:string,label:string){
  const active=selected===name&&player===branch,values=counts(name,branch);
  const className=(name===unscopedLineup?'template-lineup-unscoped ':branch?'template-lineup-branch ':'')+(active?'selected':'');
  return <button key={label} type="button" aria-pressed={active} className={className} aria-label={label}
   aria-description={describeCounts(values)} onClick={()=>onSelect(name,branch)}><span>{label}</span><LineupCounts counts={values}/></button>;
 }
 return <aside className="template-events template-lineup-sidebar" aria-label="阵容列表">
  <label className="template-entity-search">搜索阵容<input type="search" value={query} onChange={e=>onQuery(e.target.value)}/></label>
  {unscoped&&item(unscopedLineup,'',unscopedLineup)}
  {matches.map(({name,branch,label})=>item(name,branch,label))}
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
 const columnHeading=(key:string,label:string)=><h3><button type="button" className="template-lineup-column-heading"
  disabled={!rows.columnIds.get(key)?.size} onClick={()=>onDrill({kind:'column',key})}>{label}</button></h3>;
 const counts=(ids:Set<string>)=><LineupCounts counts={lineupTemplateCounts(ids,rows.reviews)}/>;
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
    const showGeneral=category==='heroes'&&rows.generalHeroIds.size>0;
    return <section key={category} aria-label={label}>{columnHeading(category,label)}<div className="template-lineup-column-cards" data-lineup-scroll={category} tabIndex={0} aria-label={label+'模板'}>
     {showGeneral&&<article className="template-lineup-card" aria-label={generalHeroLabel}>
      <button type="button" onClick={()=>onDrill({kind:'generalHero',key:generalHeroLabel})}><strong>{generalHeroLabel}</strong>{counts(rows.generalHeroIds)}</button>
      {[...rows.generalHeroEvents].map(([event,ids])=><button key={event} type="button" onClick={()=>onDrill({kind:'generalHero',key:generalHeroLabel,event})}>
       <span>{eventName(event)}</span>{counts(ids)}
      </button>)}
     </article>}
     {cards.map(({entity,ids,events})=><article className="template-lineup-card" key={entity.key}>
      <button type="button" disabled={!ids.size} aria-label={entity.name} aria-description={describeCounts(lineupTemplateCounts(ids,rows.reviews))}
       onClick={()=>onDrill({kind:'entity',key:entity.key})}><strong>{entity.name}</strong>{counts(ids)}</button>
      {category!=='talents'&&[...events].map(([event,members])=><button key={event} type="button"
       onClick={()=>onDrill({kind:'entity',key:entity.key,event})}><span>{eventName(event)}</span>{counts(members)}</button>)}
     </article>)}
     {!cards.length&&!showGeneral&&<p className="muted">暂无模板</p>}
    </div></section>;
   })}
   <section aria-label="其他">{columnHeading('other','其他')}<div className="template-lineup-column-cards" data-lineup-scroll="other" tabIndex={0} aria-label="其他模板">
    {[...rows.other].map(([event,ids])=><article className="template-lineup-card" key={event}>
     <button type="button" onClick={()=>onDrill({kind:'event',key:event})}><strong>{eventName(event)}</strong>{counts(ids)}</button>
    </article>)}
    {!rows.other.size&&<p className="muted">暂无模板</p>}
   </div></section>
  </div>
 </>;
}
