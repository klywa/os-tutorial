import {CardImage,useCards} from './EntityCards';
import {lineupLabel} from './lineupNames';
import type {Lineup} from './types';
export default function WebsiteVariants({lineups}:{lineups:Lineup[]}){
 const cards=useCards();const label=(id:string)=>cards.find(c=>c.id===id)?.name||id;
 return <>{lineups.filter(r=>r.variants?.length).map(r=><details className="website-variants" key={r.id}><summary>{lineupLabel(r)} · 网站相似组合（统计参考） ({r.variants!.length})</summary><p className="muted">网站统计参考，非已核对攻略；使用条件与操作说明以笔记正文为准。</p><div className="website-variant-list">{r.variants!.map(v=><article key={v.id}><div className="variant-heroes">{v.heroes.map(id=><span key={id}><CardImage card={cards.find(c=>c.id===id)}/>{label(id)}</span>)}</div><small>移除：{r.heroes.filter(id=>!v.heroes.includes(id)).map(label).join('、')||'无'}；加入：{v.heroes.filter(id=>!r.heroes.includes(id)).map(label).join('、')||'无'}{v.sources?.[0]?.games!=null&&` · ${v.sources[0].games}场`}</small></article>)}</div><a href="https://www.datawxq.com/lineups" target="_blank" rel="noreferrer">查看统计来源</a></details>)}</>;
}
