import {Children,cloneElement,createContext,isValidElement,useContext,useEffect,useRef,useState,useId,useMemo,useCallback,useSyncExternalStore} from 'react';
import type {ReactNode,ReactElement} from 'react';
import {createPortal} from 'react-dom';
import {api} from './model';
import {activeWorkspace,cachedEntry,cachedGet} from './readerCache';
import type {CardDetail,CardSummary} from './types';
import {splitEntities,resolveCandidates,selectedCandidate,heroVersions,cardIndex} from './entityText';
import {DockSelection} from './dockSelection';
const CardContext=createContext<CardSummary[]>([]),ReferenceContext=createContext<string[]>([]);
const details=new Map<string,Promise<CardDetail>>();
type Dock={wide:boolean;target:HTMLDivElement|null;selection:DockSelection};
const DockContext=createContext<Dock|null>(null);
function DockHeading({selection}:{selection:DockSelection}){
 const state=useSyncExternalStore(useCallback(run=>selection.subscribe('',run),[selection]),selection.snapshot,selection.snapshot);
 return <><div className="dock-heading"><strong>卡牌详情</strong>{state.active&&<button onClick={selection.toggle}>{state.pinned?'解锁':'锁定'}</button>}</div>{!state.active&&<p className="muted">悬浮或聚焦正文中的卡牌查看详情，点击可锁定。</p>}</>;
}
export function ReadingCards({children}:{children:ReactNode}){
 const container=useRef<HTMLDivElement>(null);const [wide,setWide]=useState(false),[target,setTarget]=useState<HTMLDivElement|null>(null);
 const [selection]=useState(()=>new DockSelection());
 useEffect(()=>{const el=container.current;if(!el)return;const observer=new ResizeObserver(([entry])=>setWide(entry.contentRect.width>=1160));observer.observe(el);return()=>observer.disconnect();},[]);
 useEffect(()=>selection.close(),[wide,selection]);
 const dock=useMemo(()=>({wide,target,selection}),[wide,target,selection]);
 return <DockContext.Provider value={dock}><div ref={container} className={'reading-body '+(wide?'with-card-dock':'')}>{children}{wide&&<aside className="card-dock" aria-label="卡牌详情栏"><DockHeading selection={selection}/><div ref={setTarget}/></aside>}</div></DockContext.Provider>;
}
export const categoryNames:Record<string,string>={heroes:'英雄',players:'棋手',equipment:'装备',talents:'天赋','effect-cards':'效果牌','player-skills':'棋手技能',derivatives:'衍生物'};
export function getCard(id:string){if(!details.has(id)){const request=api<CardDetail>('cards/'+encodeURIComponent(id)).catch(e=>{details.delete(id);throw e;});details.set(id,request);}return details.get(id)!;}
export function CardProvider({children}:{children:ReactNode}){const [cards,setCards]=useState<CardSummary[]>([]);useEffect(()=>{let alive=true,epoch=0;const refresh=()=>{const current=++epoch;let fresh=false;void cachedEntry<CardSummary[]>('cards').then(c=>{if(alive&&current===epoch&&!fresh&&c)setCards(c.value);});void cachedGet<CardSummary[]>('cards',{workspace:activeWorkspace()}).then(c=>{if(alive&&current===epoch){fresh=true;setCards(c);}}).catch(()=>{});};refresh();window.addEventListener('reader-workspace',refresh);return()=>{alive=false;window.removeEventListener('reader-workspace',refresh);};},[]);return <CardContext.Provider value={cards}>{children}</CardContext.Provider>;}
export function EntityScope({references,children}:{references:string[];children:ReactNode}){return <ReferenceContext.Provider value={references}>{children}</ReferenceContext.Provider>;}
export function useCards(){return useContext(CardContext);}
export function CardImage({card,large=false}:{card?:CardSummary;large?:boolean}){const [bad,setBad]=useState(false);const url=large?card?.image_url||card?.thumb_url:card?.thumb_url||card?.image_url;useEffect(()=>setBad(false),[url]);return url&&!bad?<img className={large?'official-card-image':'official-card-thumb'} src={url} alt={card?.name??'卡牌'} loading="lazy" onError={()=>setBad(true)}/>:<span className={large?'card-image-placeholder large':'card-image-placeholder'}>{card?.name??'未配置'}</span>;}
export function EntityChip({ids,label,portrait=false}:{ids:string[];label?:string;portrait?:boolean}){
 const dock=useContext(DockContext),token=useId();
 const cards=useCards(),references=useContext(ReferenceContext);const candidates=resolveCandidates(ids,references);
 const [localOpen,setOpen]=useState(false),[pinned,setPinned]=useState(false),[chosen,setChosen]=useState('');
 const subscribe=useCallback((run:()=>void)=>dock?.selection.subscribe(token,run)??(()=>{}),[dock?.selection,token]);
 const snapshot=useCallback(()=>dock?.selection.snapshot().active===token,[dock?.selection,token]);
 const selected=useSyncExternalStore(subscribe,snapshot,snapshot);
 const open=dock?.wide?selected:localOpen;
 const anchor=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const [position,setPosition]=useState({top:0,left:0});const id=selectedCandidate(candidates,chosen),versions=heroVersions(cards,id?[id]:candidates),card=cardIndex(cards).byId.get(id)||versions[0];
 function clear(){clearTimeout(timer.current);}function close(){clear();if(dock?.wide)dock.selection.close();setOpen(false);setPinned(false);setChosen('');}
 function show(pin=false){clear();if(dock?.wide){dock.selection.select(token,pin);return;}const rect=anchor.current?.getBoundingClientRect();if(rect)setPosition({top:Math.min(rect.bottom+6,window.innerHeight-280),left:Math.max(8,Math.min(rect.left,window.innerWidth-368))});setOpen(true);}
 function leave(){clear();if(dock?.wide)return;if(!pinned)timer.current=setTimeout(()=>{setOpen(false);setChosen('');},170);}
 useEffect(()=>()=>clear(),[]);
 useEffect(()=>{if(!open){setChosen('');return;}const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){close();anchor.current?.focus();clear();}};const outside=(e:PointerEvent)=>{if(!dock?.wide&&!anchor.current?.contains(e.target as Node)&&!panel.current?.contains(e.target as Node))close();};document.addEventListener('keydown',key);document.addEventListener('pointerdown',outside);return()=>{document.removeEventListener('keydown',key);document.removeEventListener('pointerdown',outside);};},[open,dock?.wide]);
 useEffect(()=>{if(!open)return;const resize=()=>close();window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[open]);
 return <><button type="button" ref={anchor} className={portrait?'entity-portrait':'entity-chip'} aria-haspopup="dialog" aria-expanded={open} onMouseEnter={()=>{clear();timer.current=setTimeout(show,200);}} onMouseLeave={leave} onFocus={()=>{clear();timer.current=setTimeout(show,200);}} onBlur={e=>{if(!panel.current?.contains(e.relatedTarget as Node))leave();}} onClick={()=>{if(!dock?.wide&&open&&pinned)close();else{show(true);setPinned(true);}}}>{portrait&&<CardImage card={card}/>}<span>{label||card?.name||ids[0]?.replace('pending:','')}{!label&&card?.awakened?'（觉醒）':''}</span></button>
 {open&&createPortal(<div ref={panel} className={'entity-popover '+(dock?.wide?'docked-card':'')} role="dialog" aria-label={`${label||card?.name||'实体'}卡牌详情`} style={dock?.wide?undefined:{top:Math.max(8,position.top),left:position.left,maxHeight:`calc(100dvh - ${Math.max(8,position.top)+8}px)`}} onMouseEnter={clear} onMouseLeave={leave} onFocus={clear} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node)&&e.relatedTarget!==anchor.current)leave();}}><div className="popover-heading"><strong>{card?.name||label}</strong><button onClick={close} aria-label="关闭卡牌详情">×</button></div>
 {!versions.length&&candidates.length>1&&<label>同名卡牌<select aria-label="同名卡牌" value={id} onChange={e=>setChosen(e.target.value)}><option value="">请选择要查看的同名卡牌</option>{candidates.map(cid=>{const c=cardIndex(cards).byId.get(cid);return <option key={cid} value={cid}>{categoryNames[c?.category??'']} · {c?.name}{c?.awakened?'（觉醒）':''} · {cid}</option>;})}</select></label>}
 {versions.length?versions.map(c=><CardVersion key={c.id} card={c} hero/>):id?<CardVersion key={id} card={card}/>:<p className="muted">此名称对应多张卡牌，请选择具体卡牌。</p>}
 </div>,dock?.wide&&dock.target?dock.target:document.body)}</>;
}
function CardVersion({card,hero=false}:{card?:CardSummary;hero?:boolean}){
 const [detail,setDetail]=useState<CardDetail|null>(null),[error,setError]=useState(''),[full,setFull]=useState(false);
 const id=card?.id;
 useEffect(()=>{if(!id)return;let alive=true;setDetail(null);setError('');void getCard(id).then(d=>{if(alive)setDetail(d);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[id]);
 return <section className="card-version" aria-label={hero?(card?.awakened?'觉醒':'未觉醒'):undefined}>
 {hero&&<h3 className="card-version-heading">{card?.awakened?'觉醒':'未觉醒'}</h3>}
 <div className="popover-card"><CardImage card={card} large/><div><p className="muted">{categoryNames[card?.category??'']}{card?.tier!=null?` · ${card.tier}品阶`:''}{card?.faction?.name?` · ${card.faction.name}`:''}</p><p>{card?.effect||'资料未提供'}</p></div></div>
 {error?<p className="error" role="alert">{error}</p>:!detail?<p className="muted">正在载入技能…</p>:<>{detail.skills_source&&detail.skills_source!==detail.id&&<p className="muted">官网未单列本卡技能，以下来自对应普通英雄。</p>}{detail.skills.slice(0,full?undefined:1).map(s=><section key={s.id}><strong>{s.name}</strong><p>{s.effect}</p>{full&&s.enhancements.map((e,i)=><p key={i}>{e.level}级：{e.effect}</p>)}</section>)}{full&&<dl>{Object.entries(detail.stats).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}<button className="link-button" onClick={()=>setFull(!full)}>{full?'收起完整详情':'查看完整卡牌详情'}</button></>}
 </section>;
}
export function EntityText({children}:{children:ReactNode}){const cards=useCards();function transform(node:ReactNode):ReactNode{return Children.map(node,child=>{if(typeof child==='string')return splitEntities(child,cards).map((t,i)=>t.ids?<EntityChip key={i} ids={t.ids} label={t.text}/>:t.text);if(isValidElement(child)&&typeof child.type==='string'&&!['a','code','pre','button','input','textarea'].includes(child.type)){const el=child as ReactElement<{children?:ReactNode}>;return cloneElement(el,{},transform(el.props.children));}return child;});}return <>{transform(children)}</>;}
