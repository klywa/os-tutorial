import Markdown from './EntityMarkdown';
import type {Note,ReadingDocument} from './types';
import {variantAvailability} from './model';

export default function Reading({document,section,full,note,onNote,onSection,banned=[]}:{document:ReadingDocument;section:string;full:boolean;note:Note;onNote:(id:string,player?:string)=>void;onSection?:(title:string)=>void;banned?:string[]}){
 const sections=document.sections;
 return <div className="shared-reading">{sections.map(s=><section className="strategy reading-chapter" data-section={s.title} id={s.id} key={s.id}>
  <h2>{s.title}</h2>{!!banned.length&&['运营路线与后期组合','阵容概览与成员清单'].includes(s.title)&&note.meta?.late_variants?.map(v=>{const meta=note.meta!,status=variantAvailability(meta,v,banned);const blocked=banned.some(f=>[...meta.required_factions,...v.required_factions].includes(f));const joint=v.ban_combinations?.find(c=>c.factions.length===new Set(banned).size&&c.factions.every(f=>banned.includes(f)));const conditions=[...meta.ban_conditions,...v.ban_conditions].filter(c=>banned.includes(c.faction));return <div key={v.id} className={'availability '+status}><strong>{v.name}：{({playable:'可玩',unplayable:'不可玩',unknown:'待确认'})[status]}</strong><p>{blocked?'组合必需英雄无法获取。':joint?.reason||(status==='unknown'&&banned.length>1?'多个阵营同时禁用时，尚无已确认的完整路线。':conditions.map(c=>c.reason).filter(Boolean).join('；')||'当前禁用条件下的适用情况待确认。')}</p></div>;})}<div className="prose"><Markdown components={{
   table:({children})=><div className="reading-table" tabIndex={0} role="region" aria-label={`${s.title}表格，可横向滚动`}><table>{children}</table></div>,
   a:({href,children})=>{const link=note.guide_related?.find(x=>x.href===href);if(link)return <button className="link-button" onClick={()=>onNote(link.note,link.player)}>{children}</button>;const target=document.sections.find(s=>'#'+s.id===href);if(target)return <button className="link-button" onClick={()=>onSection?.(target.title)}>{children}</button>;const related=note.related.find(n=>n.title===children);return related?<button className="link-button" onClick={()=>onNote(related.id)}>{children}</button>:<a href={href} target="_blank" rel="noreferrer">{children}</a>;}
  }}>{s.markdown}</Markdown></div>
 </section>)}</div>;
}
