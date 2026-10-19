import {useState} from 'react';
import {EntityChip,EntityText} from './EntityCards';
import Markdown from './EntityMarkdown';
import type {Note,OverviewPreset} from './types';
import {overviewFor,membersFor,stages,compatibleRoute} from './overview';
import {claimMarkdown} from './reading';
function Cards({ids}:{ids:string[]}){return <div className="overview-cards">{[...new Set(ids)].map(id=><EntityChip key={id} ids={[id]} portrait/>)}{!ids.length&&<span className="muted">未配置</span>}</div>;}
export default function LineupOverview({note}:{note:Note}){
 const meta=note.meta!,data=overviewFor(meta);
 const key='wxq.overview.'+note.id+'.'+meta.players.join(',');
 const [selection,setSelection]=useState<{preset:string;route:string}>(()=>{try{return JSON.parse(localStorage.getItem(key)??'null')??{preset:data.presets[0]?.id,route:''};}catch{return {preset:data.presets[0]?.id,route:''};}});
 const p=data.presets.find(p=>p.id===selection.preset)??data.presets[0];if(!p)return null;
 const route=meta.operation_routes?.find(r=>r.id===selection.route),compatible=compatibleRoute(meta,p,selection.route);
 function choose(next:{preset:string;route:string}){setSelection(next);localStorage.setItem(key,JSON.stringify(next));}
 function preset(next:OverviewPreset){choose({preset:next.id,route:compatibleRoute(meta,next,selection.route)?selection.route:''});}
 const late=membersFor(meta,p,'late'),variant=meta.late_variants?.find(v=>v.id===p.variant_id);
 return <section className="lineup-overview" aria-label="阵容概览"><div className="overview-heading"><h2>阵容概览</h2><div>{data.presets.length>1&&<label>阵容方案<select aria-label="阵容方案" value={p.id} onChange={e=>preset(data.presets.find(p=>p.id===e.target.value)!)}>{data.presets.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}{!!meta.operation_routes?.length&&<label>运营路线<select aria-label="概览运营路线" value={selection.route} onChange={e=>choose({...selection,preset:p.id,route:e.target.value})}><option value="">未选择路线</option>{meta.operation_routes.map(r=><option key={r.id} value={r.id}>{r.name}{!compatibleRoute(meta,p,r.id)?'（适配未确认）':''}</option>)}</select></label>}</div></div>
 <div className="overview-opening"><div><h3>后期站位</h3>{p.placements.length?<div className="lineup-board" role="group" aria-label="四行七列站位棋盘">{Array.from({length:28},(_,i)=>{const cell=p.placements.find(c=>c.row===Math.floor(i/7)&&c.col===i%7);return <div className="board-cell" key={i} aria-label={`第${Math.floor(i/7)+1}行第${i%7+1}列`}>{cell&&<><EntityChip ids={[cell.hero]} portrait/><div className="equipment-markers">{cell.equipment.map(id=><EntityChip key={id} ids={[id]} portrait/>)}</div></>}</div>;})}</div>:<><p className="muted">站位未配置，以下为已确认的组合成员。</p><Cards ids={late.filter(m=>m.necessity==='required').map(m=>m.hero)}/></>}
 <div className="overview-reserves"><strong>备选</strong><Cards ids={[...p.reserves,...late.filter(m=>m.necessity==='optional').map(m=>m.hero)]}/></div></div>
 <div className="overview-description"><h3>{p.name}</h3><EntityText><p>{p.description||variant?.condition||'阵容说明未配置'}</p></EntityText>{route&&<><h4>{route.name}</h4><EntityText><p>{route.condition}</p></EntityText>{!compatible&&<p className="muted">该路线与当前组合的适配尚未确认，阶段建议不合并展示。</p>}</>}<p className="muted">图片取自官网；点击英雄、装备或文字 chip 查看详情。</p></div></div>
 {stages.map((stage,index)=>{const config=p.stages[stage],members=membersFor(meta,p,stage),refs=[...config.claim_refs,...compatible&&route?route.phases[stage]:[]];return <section className="overview-stage" key={stage}><div className="overview-stage-label"><h3>{['前期','中期','后期'][index]}</h3>{config.rounds&&<small>{config.rounds}</small>}</div><div><Cards ids={members.filter(m=>m.necessity==='required').map(m=>m.hero)}/>{config.description&&<Markdown>{config.description}</Markdown>}{[...new Set(refs)].map(id=>{const c=note.claims.find(c=>c.id===id);return c?<Markdown key={id}>{claimMarkdown(c)}</Markdown>:null;})}{!config.description&&!refs.length&&<p className="muted"><EntityText>{members.map(m=>m.role).filter(Boolean).join('；')||'阶段操作未配置'}</EntityText></p>}</div><div className="overview-stage-reserves"><strong>备选</strong><Cards ids={[...config.reserves,...members.filter(m=>m.necessity==='optional').map(m=>m.hero)]}/></div></section>;})}
 <section className="overview-recommendation"><h3>推荐天赋</h3><Cards ids={p.talents}/><Markdown>{p.talent_note||'推荐说明未配置'}</Markdown></section>
 <section className="overview-recommendation"><h3>推荐效果牌</h3><Cards ids={p.effect_cards}/><Markdown>{p.effect_note||'推荐说明未配置'}</Markdown></section>
 <section className="overview-player"><h3>棋手与能力</h3>{p.players.length?p.players.map((player,index)=><div className="overview-player-row" key={index}><EntityChip ids={[player.player]} portrait/>{(['skills','secret','exclusive'] as const).map((field,i)=><div key={field}><strong>{['技能','秘技','专属'][i]}</strong><Cards ids={player[field]}/></div>)}{player.description&&<Markdown>{player.description}</Markdown>}</div>):<p className="muted">未配置</p>}</section>
 </section>;
}
