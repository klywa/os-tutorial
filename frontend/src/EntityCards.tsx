import {appUrl} from './urls';
import {onSessionReset,requestGeneration} from './sessionRequest';
import {useAuth} from './auth';
import {Children,cloneElement,createContext,isValidElement,useContext,useEffect,useRef,useState,useId,useMemo,useCallback,useSyncExternalStore} from 'react';
import type {ClipboardEvent, ReactNode,ReactElement} from 'react';
import {createPortal} from 'react-dom';
import {api} from './model';
import {activeWorkspace,cachedEntry} from './readerCache';
import {loadCardCatalog,cardPath,cardVersion,checkCardVersion,cardCategories as categoryNames} from './cardCatalog';
import type {CardDetail,CardSummary} from './types';
import {splitEntities,resolveCandidates,selectedCandidate,heroVersions,cardIndex} from './entityText';
import {DockSelection} from './dockSelection';
import {rankCards} from './cardCompletionSearch';
const CardContext=createContext<CardSummary[]>([]),ReferenceContext=createContext<string[]>([]);
const details=new Map<string,Promise<CardDetail>>();
onSessionReset(()=>details.clear());
type Dock={wide:boolean;noteTools:boolean;target:HTMLDivElement|null;selection:DockSelection};
const DockContext=createContext<Dock|null>(null);
function DockHeading({selection}:{selection:DockSelection}){
 const state=useSyncExternalStore(useCallback(run=>selection.subscribe('',run),[selection]),selection.snapshot,selection.snapshot);
 return <><div className="dock-heading"><strong>卡牌详情</strong>{state.active&&<button onClick={selection.toggle}>{state.pinned?'解锁':'锁定'}</button>}</div>{!state.active&&<p className="muted">悬浮或聚焦正文中的卡牌查看详情，点击可锁定。</p>}</>;
}
function DockSearch({selection,children}:{selection:DockSelection;children:ReactNode}){
 const cards=useCards();
 const input=useRef<HTMLInputElement>(null);
 const composing=useRef(false);
 const [query,setQuery]=useState('');
 const [selectedId,setSelectedId]=useState('');
 const text=query.trim();
 const matches=useMemo(()=>text?rankCards(cards,text).slice(0,8):[],[cards,text]);
 const selected=matches.find(card=>card.id===selectedId);
 function change(value:string){
  selection.setSearching(Boolean(value));
  setQuery(value);
  setSelectedId('');
 }
 useEffect(()=>()=>selection.setSearching(false),[selection]);
 return <>
  <form className="dock-search" role="search" aria-label="在笔记中查找卡牌" onSubmit={e=>{
   e.preventDefault();
   if(!composing.current&&matches[0])setSelectedId(matches[0].id);
  }}>
   <div className="dock-search-input">
    <input ref={input} value={query} aria-label="搜索卡牌" placeholder="搜索卡牌"
     onChange={e=>change(e.target.value)}
     onCompositionStart={()=>{composing.current=true;}}
     onCompositionEnd={()=>{composing.current=false;}}
     onKeyDown={e=>{if(e.key==='Enter'&&(composing.current||e.nativeEvent.isComposing||e.keyCode===229))e.preventDefault();}}/>
    {query&&<button type="button" aria-label="清空卡牌搜索" onClick={()=>{change('');input.current?.focus();}}>×</button>}
   </div>
   <button type="submit" disabled={!matches.length}>确定</button>
  </form>
  {!query?children:<>
   {text&&!matches.length&&<p className="muted" role="status">未找到卡牌</p>}
   {matches.length>0&&<ul className="dock-matches" aria-label="卡牌候选">{matches.map(card=><li key={card.id}>
    <button type="button" aria-pressed={card.id===selectedId} onClick={()=>setSelectedId(card.id)}>
     <span>{card.name}</span><small>{categoryNames[card.category]}{card.category==='heroes'&&(card.awakened?' · 觉醒':' · 普通')}</small>
    </button>
   </li>)}</ul>}
   {selected&&<div className="entity-popover docked-card" aria-label="搜索到的卡牌详情">
    <div className="popover-heading"><strong>{selected.name}{selected.awakened?'（觉醒）':''}</strong></div>
    <CardVersion key={selected.id} card={selected}/>
   </div>}
  </>}
 </>;
}
function copyNoteEntities(event:ClipboardEvent<HTMLDivElement>){
 const selection=event.currentTarget.ownerDocument.getSelection();
 if(!selection||selection.isCollapsed||!selection.rangeCount)return;
 const range=selection.getRangeAt(0);
 const node=range.commonAncestorContainer;
 const element=node.nodeType===Node.ELEMENT_NODE?node as Element:node.parentElement;
 if(!element?.closest('.content-scroll'))return;
 const entity=element.closest('.entity-inline');
 if(!entity&&![...element.querySelectorAll('.entity-inline')].some(chip=>range.intersectsNode(chip)))return;
 event.clipboardData.setData('text/plain',selection.toString());
 event.preventDefault();
}
export function ReadingCards({children,noteTools=false}:{children:ReactNode;noteTools?:boolean}){
 const container=useRef<HTMLDivElement>(null);const [wide,setWide]=useState(false),[target,setTarget]=useState<HTMLDivElement|null>(null);
 const [selection]=useState(()=>new DockSelection());
 useEffect(()=>{const el=container.current;if(!el)return;const observer=new ResizeObserver(([entry])=>setWide(entry.contentRect.width>=1160));observer.observe(el);return()=>observer.disconnect();},[]);
 useEffect(()=>selection.close(),[wide,selection]);
 const dock=useMemo(()=>({wide,noteTools,target,selection}),[wide,noteTools,target,selection]);
 const detail=<div ref={setTarget}/>;
 return <DockContext.Provider value={dock}>
  <div ref={container} className={'reading-body '+(wide?'with-card-dock':'')} onCopy={noteTools?copyNoteEntities:undefined}>
   {children}
   {wide&&<aside className="card-dock" aria-label="卡牌详情栏">
    <DockHeading selection={selection}/>
    {noteTools?<DockSearch selection={selection}>{detail}</DockSearch>:detail}
   </aside>}
  </div>
 </DockContext.Provider>;
}
export {categoryNames};
export function getCard(id:string,version=cardVersion()){const key=cardPath(id,version);if(!details.has(key)){const request=api<CardDetail>(key).catch(e=>{if(details.get(key)===request)details.delete(key);throw e;});details.set(key,request);}return details.get(key)!;}
export function CardProvider({children,enabled=true}:{children:ReactNode;enabled?:boolean}){
 const publicMode=useAuth().session.mode==='public';
 const [cards,setCards]=useState<CardSummary[]>([]),[active,setActive]=useState(enabled);
 useEffect(()=>{if(enabled)setActive(true);},[enabled]);
 useEffect(()=>{
  if(!active)return;let alive=true,epoch=0;
  const refresh=()=>{const current=++epoch,workspace=activeWorkspace();let fresh=false;
   if(!publicMode)void cachedEntry<CardSummary[]>('cards',workspace).then(c=>{if(alive&&current===epoch&&!fresh&&c)setCards(c.value);});
   void (publicMode?checkCardVersion().then(()=>loadCardCatalog(workspace)):loadCardCatalog(workspace)).then(c=>{if(alive&&current===epoch&&c.every(card=>(card.catalog_version??'')===cardVersion(workspace))){fresh=true;setCards(c);}}).catch(()=>{});
  };
  const catalog=(event:Event)=>{const value=(event as CustomEvent<{cards:CardSummary[];workspace:string;epoch:number;version:string}>).detail;if(alive&&value.workspace===activeWorkspace()&&value.epoch===requestGeneration()&&value.version===cardVersion(value.workspace))setCards(value.cards);};
  window.addEventListener('cards-catalog',catalog);
  window.addEventListener('cards-version-changed',refresh);
  refresh();window.addEventListener('reader-workspace',refresh);
  return()=>{alive=false;window.removeEventListener('reader-workspace',refresh);window.removeEventListener('cards-catalog',catalog);window.removeEventListener('cards-version-changed',refresh);};
 },[active,publicMode]);
 return <CardContext.Provider value={cards}>{children}</CardContext.Provider>;
}
export function EntityScope({references,children}:{references:string[];children:ReactNode}){return <ReferenceContext.Provider value={references}>{children}</ReferenceContext.Provider>;}
export function useCards(){return useContext(CardContext);}
export function CardImage({card,large=false}:{card?:CardSummary;large?:boolean}){const [bad,setBad]=useState(false);const url=large?card?.image_url||card?.thumb_url:card?.thumb_url||card?.image_url;useEffect(()=>setBad(false),[url]);return url&&!bad?<img className={large?'official-card-image':'official-card-thumb'} src={appUrl(url)} alt={card?.name??'卡牌'} loading="lazy" onError={()=>{setBad(true);const version=card?.catalog_version;if(version)void checkCardVersion().then(state=>{if(state.version!==version)window.dispatchEvent(new Event("cards-version-changed"));}).catch(()=>{});}}/>:<span className={large?'card-image-placeholder large':'card-image-placeholder'}>{card?.name??'未配置'}</span>;}
export function EntityChip({ids,label,portrait=false,inline=false}:{ids:string[];label?:string;portrait?:boolean;inline?:boolean}){
 const dock=useContext(DockContext),token=useId();
 const cards=useCards(),references=useContext(ReferenceContext);const candidates=resolveCandidates(ids,references);
 const [localOpen,setOpen]=useState(false),[pinned,setPinned]=useState(false),[chosen,setChosen]=useState('');
 const subscribe=useCallback((run:()=>void)=>dock?.selection.subscribe(token,run)??(()=>{}),[dock?.selection,token]);
 const snapshot=useCallback(()=>dock?.selection.snapshot().active===token,[dock?.selection,token]);
 const selected=useSyncExternalStore(subscribe,snapshot,snapshot);
 const open=dock?.wide?selected:localOpen;
 const anchor=useRef<HTMLElement|null>(null),panel=useRef<HTMLDivElement>(null),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const setAnchor=useCallback((el:HTMLElement|null)=>{anchor.current=el;},[]);
 const [position,setPosition]=useState({top:0,left:0});const id=selectedCandidate(candidates,chosen),versions=heroVersions(cards,id?[id]:candidates),card=cardIndex(cards).byId.get(id)||versions[0];
 function clear(){clearTimeout(timer.current);}function close(){clear();if(dock?.wide)dock.selection.close();setOpen(false);setPinned(false);setChosen('');}
 function show(pin=false){clear();if(dock?.wide){dock.selection.select(token,pin);return;}const rect=anchor.current?.getBoundingClientRect();if(rect)setPosition({top:Math.min(rect.bottom+6,window.innerHeight-280),left:Math.max(8,Math.min(rect.left,window.innerWidth-368))});setOpen(true);}
 function leave(){clear();if(dock?.wide)return;if(!pinned)timer.current=setTimeout(()=>{setOpen(false);setChosen('');},170);}
 useEffect(()=>()=>clear(),[]);
 useEffect(()=>{if(!open){setChosen('');return;}const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){close();anchor.current?.focus();clear();}};const outside=(e:PointerEvent)=>{if(!dock?.wide&&!anchor.current?.contains(e.target as Node)&&!panel.current?.contains(e.target as Node))close();};document.addEventListener('keydown',key);document.addEventListener('pointerdown',outside);return()=>{document.removeEventListener('keydown',key);document.removeEventListener('pointerdown',outside);};},[open,dock?.wide]);
 useEffect(()=>{if(!open)return;const resize=()=>close();window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[open]);
 function schedule(){clear();timer.current=setTimeout(dock?.wide?dock.selection.preview(token):show,200);}
 function activate(){if(!dock?.wide&&open&&pinned)close();else{show(true);if(!dock?.wide)setPinned(true);}}
 const title=(label||card?.name||ids[0]?.replace('pending:','')||'')+(!label&&card?.awakened?'（觉醒）':'');
 const anchorEvents={
  'aria-haspopup':'dialog' as const,'aria-expanded':open,onMouseEnter:schedule,onMouseLeave:leave,onFocus:schedule,
  onBlur:(event:React.FocusEvent<HTMLElement>)=>{if(!panel.current?.contains(event.relatedTarget as Node))leave();},
  onClick:activate,
 };
 return <>{(inline||dock?.noteTools)&&!portrait?
  <span ref={setAnchor} className="entity-chip entity-inline" role="button" tabIndex={0} {...anchorEvents}
    onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}}}>{title}</span>:
  <button type="button" ref={setAnchor} className={portrait?'entity-portrait':'entity-chip'} {...anchorEvents}>{portrait&&<CardImage card={card}/>}<span>{title}</span></button>}
 {open&&createPortal(<div ref={panel} className={'entity-popover '+(dock?.wide?'docked-card':'')} role="dialog" aria-label={`${label||card?.name||'实体'}卡牌详情`} style={dock?.wide?undefined:{top:Math.max(8,position.top),left:position.left,maxHeight:`calc(100dvh - ${Math.max(8,position.top)+8}px)`}} onMouseEnter={clear} onMouseLeave={leave} onFocus={clear} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node)&&e.relatedTarget!==anchor.current)leave();}}><div className="popover-heading"><strong>{card?.name||label}</strong><button onClick={close} aria-label="关闭卡牌详情">×</button></div>
 {!versions.length&&candidates.length>1&&<label>同名卡牌<select aria-label="同名卡牌" value={id} onChange={e=>setChosen(e.target.value)}><option value="">请选择要查看的同名卡牌</option>{candidates.map(cid=>{const c=cardIndex(cards).byId.get(cid);return <option key={cid} value={cid}>{categoryNames[c?.category??'']} · {c?.name}{c?.awakened?'（觉醒）':''} · {cid}</option>;})}</select></label>}
 {versions.length?versions.map(c=><CardVersion key={c.id} card={c} hero/>):id?<CardVersion key={id} card={card}/>:<p className="muted">此名称对应多张卡牌，请选择具体卡牌。</p>}
 </div>,dock?.wide&&dock.target?dock.target:document.body)}</>;
}
function CardVersion({card,hero=false}:{card?:CardSummary;hero?:boolean}){
 const [detail,setDetail]=useState<CardDetail|null>(null),[error,setError]=useState(''),[full,setFull]=useState(false);
 const id=card?.id,version=card?.catalog_version??'',key=id?cardPath(id,version):'';
 useEffect(()=>{if(!id)return;let alive=true;setDetail(null);setError('');void getCard(id,version).then(d=>{if(alive)setDetail(d);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[id,key,version]);
 return <section className="card-version" aria-label={hero?(card?.awakened?'觉醒':'未觉醒'):undefined}>
 {hero&&<h3 className="card-version-heading">{card?.awakened?'觉醒':'未觉醒'}</h3>}
 <div className="popover-card"><CardImage card={card} large/><div><p className="muted">{categoryNames[card?.category??'']}{card?.tier!=null?` · ${card.tier}品阶`:''}{card?.faction?.name?` · ${card.faction.name}`:''}</p><p>{card?.effect||'资料未提供'}</p></div></div>
 {error?<p className="error" role="alert">{error}</p>:!detail?<p className="muted">正在载入技能…</p>:<>{detail.skills_source&&detail.skills_source!==detail.id&&<p className="muted">官网未单列本卡技能，以下来自对应普通英雄。</p>}{detail.skills.slice(0,full?undefined:1).map(s=><section key={s.id}><strong>{s.name}</strong><p>{s.effect}</p>{full&&s.enhancements.map((e,i)=><p key={i}>{e.level}级：{e.effect}</p>)}</section>)}{full&&<dl>{Object.entries(detail.stats).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}<button className="link-button" onClick={()=>setFull(!full)}>{full?'收起完整详情':'查看完整卡牌详情'}</button></>}
 </section>;
}
export function EntityText({children,inline=false}:{children:ReactNode;inline?:boolean}){const cards=useCards();function transform(node:ReactNode):ReactNode{return Children.map(node,child=>{if(typeof child==='string')return splitEntities(child,cards).map((t,i)=>t.ids?<EntityChip key={i} ids={t.ids} label={t.text} inline={inline}/>:t.text);if(isValidElement(child)&&typeof child.type==='string'&&!['a','code','pre','button','input','textarea'].includes(child.type)){const el=child as ReactElement<{children?:ReactNode}>;return cloneElement(el,{},transform(el.props.children));}return child;});}return <>{transform(children)}</>;}
