import {SourceSaveQueue} from './annotationSaving';
import NoteHeading from './NoteHeading';
import {useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import Markdown from './EntityMarkdown';
import Editor from './Editor';
import BranchEditor from './BranchEditor';
import MarkdownSyncPanel from './MarkdownSyncPanel';
import Tactics from './Tactics';
import Reading from './ReadingBody';
import {resolveReadingSection,loadReaderData} from './reading';
import Sources from './Sources';
import Crawler from './Crawler';
import GlobalActivity from './GlobalActivity';
import Cards from './Cards';
import {CardProvider,EntityScope,EntityText,EntityChip,ReadingCards} from './EntityCards';
import LineupOverview from './LineupOverview';
import NoteDirectory from './NoteDirectory';
import LibraryTools from './LibraryTools';
import NewNoteDialog from './NewNoteDialog';
import {filterNotes,noteCounts,restoreNoteSelection} from './directoryModel';
import './entities.css';
import {api,availability,entityLabel} from './model';
import type {Note,Options,Source,ReadingDocument,Creator} from './types';
import './style.css';
import './acquisition.css';
import './directory.css';

type Prefs={branchPlayers?:Record<string,string>;mode:'sidebar'|'full';view:'play'|'notes'|'sources'|'cards'|'crawler';selected:string;section:string;query:string;banned:string[];unknown:boolean;player:string;hero:string;type:string};
const initial:Prefs={mode:window.innerWidth<760?'sidebar':'full',view:'play',selected:'',section:'前期运营及应变',query:'',banned:[],unknown:false,player:'',hero:'',type:''};
function preferences(){try{return {...initial,...JSON.parse(localStorage.getItem('wxq.preferences')??'{}')};}catch{return initial;}}
const quick=['运营节奏','后期运营及应变','终局技巧','克制手段','站位技巧','推荐装备','推荐天赋及原因','成型后提升思路'];
const phaseLabels:Record<string,string>={'运营节奏':'运营节奏','阵容组成':'阵容','禁用阵营适用情况':'禁用条件','核心机制':'机制','前期运营及应变':'前期','中期运营及应变':'中期','后期运营及应变':'后期','成型后提升思路':'成型提升','第一轮拍卖':'首轮拍卖','第二轮拍卖':'二轮拍卖','第三轮拍卖':'三轮拍卖','推荐天赋及原因':'天赋','站位技巧':'站位','推荐装备':'装备','终局技巧':'终局','克制手段':'克制本阵容','制敌手段':'制敌手段'};
function App(){
  const [prefs,setPrefs]=useState<Prefs>(preferences),[notes,setNotes]=useState<Note[]>([]),[options,setOptions]=useState<Options>({entities:[],factions:[],sections:{}}),[sources,setSources]=useState<Source[]>([]);
  const [error,setError]=useState(''),[loading,setLoading]=useState(true),[editing,setEditing]=useState(false),[dirty,setDirty]=useState(false),[toast,setToast]=useState(''),[opponent,setOpponent]=useState('');
  const [creatorSeed,setCreatorSeed]=useState<Partial<Creator>|undefined>(undefined);
  const [reader,setReader]=useState<ReadingDocument|null>(null),[readerError,setReaderError]=useState(''),[readingReload,setReadingReload]=useState(0);
  const [newNote,setNewNote]=useState(false);
  const content=useRef<HTMLDivElement>(null),scroll=useRef<Record<string,number>>({});
  const patch=(p:Partial<Prefs>)=>setPrefs(current=>({...current,...p}));
  const sourceEpoch=useRef(0);
  const sourceQueue=useRef<SourceSaveQueue|null>(null);
  if(!sourceQueue.current)sourceQueue.current=new SourceSaveQueue(
    (source,changes,revision)=>api<Source>('sources/'+encodeURIComponent(source.id),'PUT',{...changes,revision}),
    saved=>{sourceEpoch.current++;setSources(rows=>rows.map(row=>row.id===saved.id?saved:row));});
  async function refreshSources(){const epoch=sourceEpoch.current;const rows=await api<Source[]>('sources');if(epoch===sourceEpoch.current)setSources(rows);}
  async function load(){setLoading(true);setError('');try{const [n,o]=await loadReaderData(api);setNotes(n);setOptions(o);void refreshSources().catch(()=>{});setReadingReload(v=>v+1);const selected=restoreNoteSelection(n,prefs.selected);if(selected!==prefs.selected)patch({selected});}catch(e){setError((e as Error).message);}finally{setLoading(false);}}
  useEffect(()=>{void load();void api('crawler/creators/resume','POST',{}).catch(e=>setToast('UP监听恢复失败：'+e.message));},[]);
  useEffect(()=>localStorage.setItem('wxq.preferences',JSON.stringify(prefs)),[prefs]);
  useEffect(()=>{const handler=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[dirty]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),3500);return()=>clearTimeout(timer);},[toast]);
  const family=notes.find(n=>n.id===prefs.selected);
  const rememberedPlayer=family?prefs.branchPlayers?.[family.id]:undefined;
  const branchPlayer=rememberedPlayer&&family?.meta?.players.includes(rememberedPlayer)?rememberedPlayer:undefined;
  const active=reader&&reader.note_id===family?.id&&reader.revision===family?.revision&&(!branchPlayer||reader.player===branchPlayer)?reader.projected_note??family:family?.meta?.player_branches?.length?undefined:family;
  const reading=reader?.note_id===active?.id&&reader?.revision===active?.revision?reader:null;
  useEffect(()=>{if(!family||dirty)return;let live=true;const timer=setInterval(()=>{void api<{revision:string}>('notes/'+encodeURIComponent(family.id)+'/revision').then(async row=>{if(row.revision!==family.revision){const latest=await api<Note>('notes/'+encodeURIComponent(family.id));if(live)setNotes(rows=>rows.map(n=>n.id===latest.id?latest:n));}}).catch(()=>{});},3000);return()=>{live=false;clearInterval(timer);};},[family?.id,family?.revision,dirty]);
  useEffect(()=>{
    if(!family)return;
    let cancelled=false;setReader(null);setReaderError('');
    void api<ReadingDocument>('notes/'+encodeURIComponent(family.id)+'/reading'+(branchPlayer?'?player='+encodeURIComponent(branchPlayer):'')).then(async doc=>{if(cancelled)return;if(doc.revision!==family.revision){const latest=await api<Note>('notes/'+encodeURIComponent(family.id));if(!cancelled)setNotes(rows=>rows.map(n=>n.id===latest.id?latest:n));}if(!cancelled)setReader(doc);}).catch(e=>{if(!cancelled)setReaderError((e as Error).message);});
    return()=>{cancelled=true;};
  },[family?.id,family?.revision,branchPlayer,readingReload]);
  useEffect(()=>{
    if(!reading?.profile)return;
    const next=resolveReadingSection(reading,prefs.section);
    if(next!==prefs.section)patch({section:next});
  },[reading,prefs.section]);
  const allEntities=useMemo(()=>[...options.entities,...notes.filter(n=>n.type==='lineup').map(n=>({id:n.id,name:n.title,category:'lineup'}))],[options,notes]);
  const displayOptions={...options,entities:allEntities};
  const name=(id:string)=>{const entity=[...allEntities,...options.factions].find(e=>e.id===id);return entity?entityLabel(entity):id.replace('pending:','');};
  const counts=noteCounts(notes,prefs,allEntities);
  const visible=filterNotes(notes,{...prefs,type:prefs.view==='play'?'lineup':prefs.type},allEntities).map(n=>({note:n,status:availability(n,prefs.view==='play'?prefs.banned:[])}));
  const playable=visible.filter(n=>n.status==='playable'),unknown=visible.filter(n=>n.status==='unknown');
  function leave(){if(dirty&&!confirm('有未保存修改，确定放弃这些修改吗？'))return false;setEditing(false);setDirty(false);return true;}
  function select(id:string,view=prefs.view){if(!leave())return;patch({selected:id,view});setOpponent('');}
  function changeView(view:Prefs['view']){if(leave())patch({view,...(view==='play'&&!notes.some(n=>n.id===prefs.selected&&n.type==='lineup')?{selected:notes.find(n=>n.type==='lineup')?.id??''}:{})});}
  function changeSection(section:string){patch({section});requestAnimationFrame(()=>content.current?.querySelector(`[data-section="${CSS.escape(section)}"]`)?.scrollIntoView({block:'start'}));}
  const readingKey=(active?.id??'')+'|'+(reading?.player??'');
  useEffect(()=>{
    const element=content.current;if(!element||editing)return;
    const restore=requestAnimationFrame(()=>{element.scrollTop=scroll.current[readingKey]??0;});
    function track(){
      scroll.current[readingKey]=element!.scrollTop;
      const top=element!.getBoundingClientRect().top+35;
      const chapters=Array.from(element!.querySelectorAll<HTMLElement>('[data-section]'));
      const current=chapters.filter(x=>x.getBoundingClientRect().top<=top).at(-1);
      if(current?.dataset.section)setPrefs(p=>p.section===current.dataset.section?p:{...p,section:current.dataset.section!});
    }
    element.addEventListener('scroll',track,{passive:true});
    return()=>{cancelAnimationFrame(restore);element.removeEventListener('scroll',track);};
  },[readingKey,reading?.revision,editing]);
  const section=reading?.profile?resolveReadingSection(reading,prefs.section):prefs.section;
  const sectionNames=reading?.profile?reading.sections.map(s=>s.title):active?[...new Set([...(options.sections[active.type]??[]),...active.claims.map(c=>c.section),...(active.meta?.operation_routes?.length?['运营节奏']:[])])]:[];
  function scopedClaims(claims:Note['claims']){return claims.map(c=>({...c,route_names:(active?.meta?.operation_routes??[]).filter(r=>Object.values(r.phases).flat().includes(c.id??'')).map(r=>r.name)}));}
  const rows=scopedClaims(active?.claims.filter(c=>c.section===section)??[]);
  const stage=section.startsWith('前期')?'early':section.startsWith('中期')?'middle':section.startsWith('后期')?'late':undefined;
  function saved(note:Note){setNotes(rows=>rows.map(n=>n.id===note.id?note:n));setEditing(false);setDirty(false);setToast('笔记与存档已同步保存');void api<Options>('options').then(setOptions).catch(e=>setError((e as Error).message));}
  function created(note:Note){setNotes(rows=>[...rows.filter(n=>n.id!==note.id),note]);setNewNote(false);patch({selected:note.id,view:'notes',type:note.type,query:'',player:'',hero:''});setEditing(true);setDirty(false);setToast('空白笔记已创建');}
  function noteList(entries:typeof visible){return entries.map(({note,status})=><button key={note.id} className={'note-option '+(active?.id===note.id?'active':'')} onClick={()=>select(note.id)}><span className="note-icon">{note.type==='lineup'?'◈':note.type==='player'?'♙':'▤'}</span><span><strong>{note.title}</strong><small>{note.meta?.core_heroes.map(name).join('、')||({lineup:'阵容攻略',player:'棋手笔记',other:'知识笔记'}[note.type])}</small></span>{status==='unknown'&&<span className="badge gold">待确认</span>}</button>);}
  return <EntityScope references={active?.entities??[]}><div className={'app '+prefs.mode}><header className="app-header"><div className="brand"><span className="brand-mark">象</span><div><strong>万象棋</strong><small>战术手册</small></div></div><nav aria-label="主要导航">{(['play','notes','sources','crawler','cards'] as const).map((v,i)=><button key={v} className={prefs.view===v?'selected':''} onClick={()=>changeView(v)}>{['对局助手','全部笔记','外部内容','爬取','卡牌库'][i]}</button>)}</nav><div className="header-actions"><button aria-label="切换阅读模式" title="切换侧栏与完整窗口" onClick={()=>patch({mode:prefs.mode==='full'?'sidebar':'full'})}>{prefs.mode==='full'?'▥ 侧栏模式':'▣ 完整模式'}</button><button className="refresh" aria-label="重新载入知识" onClick={()=>{if(leave())void load();}}>↻</button></div></header>
    <GlobalActivity/>
    {newNote&&<NewNoteDialog entities={options.entities} notes={notes} onOpen={id=>select(id)} defaultType={prefs.view==='play'?'lineup':prefs.type} onClose={()=>setNewNote(false)} onCreated={created}/>}
    {toast&&<div className="toast" role="status">✓ {toast}</div>}{error&&<div className="error" role="alert">{error}<button onClick={()=>void load()}>重试</button></div>}
    {loading?<div className="empty">正在载入战术手册…</div>:prefs.view==='crawler'?<Crawler seed={creatorSeed} onSeedUsed={()=>setCreatorSeed(undefined)}/>:prefs.view==='cards'?<Cards/>:prefs.view==='sources'?<Sources sources={sources} onRefresh={refreshSources} onSave={sourceQueue.current.save} onNote={id=>select(id,'notes')} onCreator={seed=>{setCreatorSeed(seed);changeView('crawler');}}/>:<div className="workspace"><aside className="library"><LibraryTools mode={prefs.view==='play'?'play':'notes'} filters={prefs} options={options} counts={counts} total={prefs.view==='notes'?notes.length:notes.filter(n=>n.type==='lineup').length} resultCount={prefs.view==='notes'?visible.length:playable.length+(prefs.unknown?unknown.length:0)} onChange={patch} onNew={()=>{if(leave())setNewNote(true);}}/><div className="note-list">{prefs.view==='notes'?<NoteDirectory notes={visible.map(x=>x.note)} active={prefs.selected} onSelect={id=>select(id)}/>:<>{noteList(playable)}{prefs.unknown&&unknown.length>0&&<><h3 className="unknown-label">适用情况待确认</h3>{noteList(unknown)}</>}{!playable.length&&<p className="empty">没有已确认符合条件的笔记。</p>}</>}</div><div className="library-foot">知识会随着新的攻略持续更新</div></aside>
      <main className="reading">{active?<><NoteHeading note={active} reading={reading} name={name} dirty={dirty} editing={editing} onEdit={()=>{if(editing){if(leave())setEditing(false);}else setEditing(true);}} onPlayer={player=>patch({branchPlayers:{...prefs.branchPlayers,[active.id]:player}})} onExport={()=>{const text='# '+active.title+'-'+name(reading!.player!)+'\n\n'+(reading?.opening?reading.opening+'\n\n':'')+reading!.sections.map(s=>'## '+s.title+'\n\n'+s.markdown).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));a.download=active.title+'-'+name(reading!.player!)+'.md';a.click();URL.revokeObjectURL(a.href);}}/><MarkdownSyncPanel note={family!} onResolved={()=>void load()}/>{prefs.view==='play'&&prefs.banned.length>0&&<div className={'availability '+availability(active,prefs.banned)}>{({playable:'当前禁用条件下已确认可玩',unplayable:'当前禁用条件下不可玩',unknown:'当前禁用条件下是否可玩待确认'})[availability(active,prefs.banned)]}</div>}
      {editing?<div className="content-scroll" ref={content}>{reading?.scope_sections?<BranchEditor key={active.id+active.revision+reading.player} note={family!} document={reading} onSaved={saved} onCancel={()=>{if(leave())setEditing(false);}} onDirty={setDirty}/>:<Editor key={active.id+active.revision} note={active} options={displayOptions} onSaved={saved} onCancel={()=>{if(leave())setEditing(false);}} onDirty={setDirty}/>}</div>:<><div className="phase-nav" aria-label="攻略章节">{sectionNames.map(s=><button key={s} className={s===section?'selected':''} onClick={()=>changeSection(s)}>{phaseLabels[s]??s}</button>)}</div><ReadingCards key={active.id}><div className="content-scroll" ref={content}>{reading?.opening&&<div className="guide-opening prose"><Markdown>{reading.opening}</Markdown></div>}{!reading?.profile&&active.meta&&<LineupOverview key={readingKey} note={active}/>} {!reading?<p className={readerError?'error':'empty'}>{readerError||'正在载入阅读内容…'}{readerError&&<button onClick={()=>setReadingReload(v=>v+1)}>重试</button>}</p>:reading.profile?<Reading overview={active.meta&&<LineupOverview key={readingKey} note={active}/>} document={reading} section={section} full={prefs.view==='notes'} note={active} onNote={(id,player)=>{if(!leave())return;patch({selected:id,view:'notes',...(player?{branchPlayers:{...prefs.branchPlayers,[id]:player}}:{})});}} onSection={changeSection} banned={prefs.view==='play'?prefs.banned:[]}/>:prefs.view==='notes'?<>{active.meta&&<MetaView note={active} name={name}/>}<Tactics note={active} name={name} routes variants/> {sectionNames.map(s=><Strategy key={s} title={s} claims={scopedClaims(active.claims.filter(c=>c.section===s))}/>)}</>:<><div className="stage-heading"><span className="stage-marker">{stage?'◉':'◇'}</span><h2>{section}</h2><span className="muted">{section==='运营节奏'?`${active.meta?.operation_routes?.length??0} 种节奏`:rows.length?`${rows.length} 条建议`:'待补充'}</span></div>{stage&&active.meta&&!(stage==='late'&&active.meta.late_variants?.length)&&<div className="formation"><h3>本阶段英雄组成</h3>{active.meta.compositions[stage].length?active.meta.compositions[stage].map((m,i)=><div className="formation-member" key={i}><EntityChip ids={[m.hero]} label={name(m.hero)}/><span className={'badge '+(m.necessity==='required'?'jade':'')}>{m.necessity==='required'?'必需':'可选'}</span><p><EntityText>{m.role}</EntityText>{m.replaces&&<>；替换 <EntityChip ids={[m.replaces]} label={name(m.replaces)}/></>}{m.replacement_note&&`：${m.replacement_note}`}</p></div>):<p className="muted">暂无已确认的本阶段英雄组成</p>}</div>}<Tactics note={active} name={name} banned={prefs.banned} routes={section==='运营节奏'} variants={section==='阵容组成'||stage==='late'}/>{section!=='运营节奏'&&<Strategy title="" claims={rows}/>} {section==='禁用阵营适用情况'&&active.meta?.ban_conditions.map(c=><div className="advice" key={c.faction}><strong>{name(c.faction)}被禁：{({playable:'可玩',unplayable:'不可玩',unknown:'待确认'})[c.status]}</strong><p>{c.reason}</p></div>)}</>}
      {!!active.conflicts?.length&&<div className="conflict">有 {active.conflicts.length} 项新证据与人工修订冲突，编辑笔记时可查看。</div>}{!reading?.profile&&<div className="related"><h3>关联知识</h3>{active.related.map(n=><button key={n.id} className="link-button" onClick={()=>select(n.id,'notes')}>{n.title}</button>)}</div>}</div></ReadingCards></>}
      </>:<div className="empty"><span className="symbol">◈</span><h2>{family?'正在载入打法':'载入一套打法'}</h2><p>{readerError||(family?'正在载入当前棋手内容…':'从目录选择攻略，开始阶段速查。')}</p>{family&&readerError&&<button onClick={()=>setReadingReload(v=>v+1)}>重新载入</button>}</div>}</main>
      {active&&!editing&&<aside className="quick-panel"><div className="quick-heading"><span>✦</span><h2>对局速查</h2></div><p className="muted">关键回合，直接找到需要的建议。</p><div className="quick-buttons">{(reading?.profile?reading.sections.map(s=>s.title).filter(s=>s!=='阵容概览与成员清单'&&s!=='关联知识'):quick.filter(s=>s!=='运营节奏'||active.meta?.operation_routes?.length)).map(s=><button key={s} className={section===s?'selected':''} onClick={()=>changeSection(s)}>{phaseLabels[s]??s}</button>)}</div><div className="opponent"><h3>对手针对</h3><select aria-label="选择对手" value={opponent} onChange={e=>setOpponent(e.target.value)}><option value="">选择对手阵容或英雄</option>{allEntities.filter(e=>e.category==='heroes'||e.category==='lineup').map(e=><option value={e.id} key={e.id}>{entityLabel(e)}</option>)}</select>{opponent?(active.meta?.matchups.filter(m=>m.target===opponent).length?active.meta.matchups.filter(m=>m.target===opponent).map((m,i)=><div key={i} className="matchup"><strong>{m.condition||'针对建议'}</strong><Markdown>{m.text}</Markdown></div>):<p className="empty">暂无针对该对手的已确认策略。可查看通用针对策略。</p>):<p className="muted">选择目标查看已整理的针对建议。</p>}<button className="link-button" onClick={()=>changeSection(reading?.profile?resolveReadingSection(reading,[2,3,4].includes(reading.layout_version??0)?'制敌手段':'克制手段'):'克制手段')}>查看通用针对策略</button></div><div className="quick-hint"><span>◇</span><p>阶段建议与针对策略均来自已保存知识；缺失内容保持待确认。</p></div></aside>}
    </div>}
  </div></EntityScope>;
}
function Strategy({title,claims}:{title:string;claims:Note['claims']}){return <section className="strategy" data-section={title}>{title&&<h2>{title}</h2>}{claims.length?claims.map((c,i)=><article className="advice" key={i}>{!!c.route_names?.length&&<span className="badge jade">{c.route_names.join('、')}</span>}<div className="prose"><Markdown components={{a:({href,children})=><a href={href} target="_blank" rel="noreferrer">{children}</a>}}>{(c.inference?'推测：':'')+(c.condition&&!c.text.includes(c.condition)?`当${c.condition}${c.condition.endsWith('时')?'':'时'}，`:'')+c.text}</Markdown></div></article>):<p className="empty">暂无已确认的通用策略</p>}</section>;}
function MetaView({note,name}:{note:Note;name:(id:string)=>string}){
 const meta=note.meta!;
 const chips=(ids:string[],empty='待确认')=>ids.length?ids.map(id=><EntityChip key={id} ids={[id]} label={name(id)}/>):empty;
 return <section className="meta-view"><EntityText><h2>阵容信息</h2><p>必须阵营：{meta.required_factions.map(name).join('、')||(meta.late_variants?.length?'随组合查看':'待确认')}</p><p>适用棋手：{chips(meta.players)}</p><p>{meta.late_variants?.length?'共用核心英雄':'核心英雄'}：{chips(meta.core_heroes,meta.late_variants?.length?'随组合查看':'待确认')}</p>{(['early','middle','late'] as const).map((stage,i)=><div key={stage}><h3>{['前期','中期','后期'][i]}组成</h3>{meta.compositions[stage].length?meta.compositions[stage].map((m,j)=><p key={j}><EntityChip ids={[m.hero]} label={name(m.hero)}/>（{m.necessity==='required'?'必需':'可选'}）：{m.role}{m.replaces&&<>；替换 <EntityChip ids={[m.replaces]} label={name(m.replaces)}/></>} <EntityText>{m.replacement_note}</EntityText></p>):<p className="muted">待确认</p>}</div>)}{meta.ban_conditions.map(c=><p key={c.faction}>{name(c.faction)}被禁：{({playable:'可玩',unplayable:'不可玩',unknown:'待确认'})[c.status]} {c.reason}</p>)}</EntityText></section>;
}
createRoot(document.getElementById('root')!).render(<CardProvider><App/></CardProvider>);
