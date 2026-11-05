import {useEffect,useMemo,useState,useRef} from 'react';
import {api,cardMatches} from './model';
import {CardImage,useCards} from './EntityCards';
import {loadCardCatalog,checkCardVersion,cardPath,cardVersion,cardCategories as categories} from './cardCatalog';
import type {CardStatus} from './cardCatalog';
import {useAuth,useCapabilities} from './auth';
import OfficialSync from './OfficialSync';
import type {CardDetail,CardSummary,CardFilters} from './types';
const initial:CardFilters={query:'',category:'',faction:'',tier:'',awakened:''};
export default function Cards(){
  const {session}=useAuth(),capabilities=useCapabilities(),isPublic=session.mode==='public';
  const loadEpoch=useRef(0);
  const [status,setStatus]=useState<CardStatus|null>(null),[version,setVersion]=useState(cardVersion);
  const shared=useCards();
  const [cards,setCards]=useState<CardSummary[]>(shared),[filters,setFilters]=useState(initial);
  const [selected,setSelected]=useState(''),[detail,setDetail]=useState<CardDetail|null>(null);
  const [error,setError]=useState(''),[loading,setLoading]=useState(!shared.length),[detailLoading,setDetailLoading]=useState(false);
  async function load(){const epoch=++loadEpoch.current;setLoading(true);setError('');try{const state=isPublic?await checkCardVersion():null;const result=await loadCardCatalog();if(epoch!==loadEpoch.current)return;setStatus(state);setVersion(result[0]?.catalog_version??cardVersion());setCards(result);}catch(e){if(epoch===loadEpoch.current)setError((e as Error).message);}finally{if(epoch===loadEpoch.current)setLoading(false);}}
  useEffect(()=>{void load();const refresh=()=>void load();if(isPublic)window.addEventListener('cards-version-changed',refresh);return()=>{loadEpoch.current++;window.removeEventListener('cards-version-changed',refresh);};},[]);
  useEffect(()=>{if(!isPublic&&shared.length)setCards(shared);},[shared,isPublic]);
  const visible=useMemo(()=>cards.filter(c=>cardMatches(c,filters)),[cards,filters]);
  const active=loading?'':visible.find(c=>c.id===selected)?.id??visible[0]?.id??'';
  const factions=useMemo(()=>Array.from(new Map(cards.map(c=>[c.faction.id||'none',c.faction.name])).entries()),[cards]);
  useEffect(()=>{let current=true;setDetail(null);if(!active){setDetailLoading(false);return;}
    setDetailLoading(true);setError('');void api<CardDetail>(cardPath(active,version)).then(c=>{if(current)setDetail({...c,catalog_version:version});}).catch(e=>{if(current)setError((e as Error).message);}).finally(()=>{if(current)setDetailLoading(false);});
    return()=>{current=false;};},[active,cards,version]);
  const patch=(p:Partial<CardFilters>)=>setFilters(f=>({...f,...p}));
  return <div className="cards-page"><div className="page-heading"><div><h1>卡牌库</h1><p>查询卡牌效果、英雄技能与成长节点。</p></div><span className="count">{visible.length} / {cards.length} 项</span></div>
    {capabilities.localTools&&<OfficialSync onUpdated={()=>void load()}/>}
    {isPublic&&status&&<p className="muted" role="status">官网资料：{status.state==='running'?'正在检查':status.state==='failed'?'更新暂未完成':status.last_success?'已更新':'使用已发布快照'} · 上次成功：{status.last_success?new Date(status.last_success).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'尚未自动同步'}{status.error&&<> · {status.error}</>}</p>}
    {error&&<div className="error" role="alert">{error}<button onClick={()=>void load()}>重试</button></div>}
    <div className="card-filters"><input aria-label="搜索卡牌" placeholder="搜索名称、别名或效果" value={filters.query} onChange={e=>patch({query:e.target.value})}/>
      <select aria-label="卡牌类别" value={filters.category} onChange={e=>patch({category:e.target.value})}><option value="">全部类别</option>{Object.entries(categories).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select>
      <select aria-label="卡牌阵营" value={filters.faction} onChange={e=>patch({faction:e.target.value})}><option value="">全部阵营</option>{factions.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select>
      <select aria-label="英雄品阶" value={filters.tier} onChange={e=>patch({tier:e.target.value})}><option value="">全部品阶</option>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}品阶英雄</option>)}</select>
      <select aria-label="觉醒状态" value={filters.awakened} onChange={e=>patch({awakened:e.target.value})}><option value="">全部状态</option><option value="normal">普通英雄</option><option value="awakened">觉醒英雄</option></select>
      <button className="quiet" onClick={()=>setFilters(initial)}>清除筛选</button></div>
    {loading?<p className="empty">正在载入卡牌…</p>:<div className="card-layout"><aside className="card-list" aria-label="卡牌列表">{visible.map(c=><button key={c.id} className={'card-option '+(c.id===active?'selected':'')} onClick={()=>setSelected(c.id)}><CardImage card={c}/><strong>{c.name}{c.awakened?'（觉醒）':''}</strong><small>{categories[c.category]} · {c.faction.name}{c.tier!==null?` · ${c.tier}品阶`:''}</small></button>)}{!visible.length&&<p className="empty">没有符合条件的卡牌。</p>}</aside>
      <main className="card-detail">{detailLoading?<p className="empty">正在载入详情…</p>:detail?<><div className="chips"><span className="badge jade">{categories[detail.category]}</span><span className="badge">{detail.faction.name}</span>{detail.tier!==null&&<span className="badge">{detail.tier}品阶</span>}</div><CardImage card={detail} large/><h2>{detail.name}{detail.awakened?'（觉醒）':''}</h2><section><h3>卡牌效果</h3><p>{detail.effect}</p></section>
        <section><h3>技能与等级强化</h3>{detail.skills_source&&detail.skills_source!==detail.id&&<p className="muted">官网未单独提供本觉醒卡技能；以下为对应普通英雄技能，不代表额外觉醒强化。</p>}{detail.skills.length?detail.skills.map(s=><div className="card-skill" key={s.id}><h4>{s.name}</h4><p>{s.effect||'未提供'}</p>{s.enhancements.map((e,i)=><p className="card-enhancement" key={i}><strong>{e.level}级</strong> {e.effect}</p>)}</div>):<p className="muted">未提供</p>}</section>
        <section><h3>基础属性</h3>{Object.keys(detail.stats).length?<dl className="card-stats">{Object.entries(detail.stats).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>:<p className="muted">未提供</p>}</section>
        <section><h3>其他官方属性</h3>{Object.keys(detail.attributes).length?<dl>{Object.entries(detail.attributes).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{typeof v==='object'?JSON.stringify(v):String(v)}</dd></div>)}</dl>:<p className="muted">未提供</p>}</section>
        <footer className="muted">同步日期：{detail.retrieved_at?.slice(0,10)||'未提供'} · 游戏版本：{detail.version||'官网未标明'}<div>{detail.sources.map((s,i)=><a key={s} href={s} target="_blank" rel="noreferrer">官网数据 {i+1}　</a>)}</div></footer>
      </>:<p className="empty">选择卡牌查看详情。</p>}</main></div>}
  </div>;
}
