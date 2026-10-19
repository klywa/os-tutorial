import type {Note,ReadingDocument} from './types';
type Props={note:Note;reading?:ReadingDocument|null;name:(id:string)=>string;dirty:boolean;editing:boolean;onAssociate?:()=>void;onEdit:()=>void;onPlayer:(player:string)=>void;onExport:()=>void};
export default function NoteHeading({note,reading,name,dirty,editing,onEdit,onPlayer,onExport}:Props){
 return <header className="note-heading compact-note-heading">
  <div className="note-title-row"><div className="note-title"><span className="note-kind">{note.type==='lineup'?'◈ 阵容战术':note.type==='player'?'♙ 棋手指南':'▤ 实用知识'}</span><h1>{note.title}</h1></div><div className="note-actions">
   <button className={editing?'selected':'edit-button'} onClick={onEdit}>{editing?'退出编辑':'编辑笔记'}</button>
   {!!reading?.player_options&&<button onClick={onExport}>导出当前棋手</button>}
  </div></div>
  {!!note.meta&&<div className="note-meta-row">
   {reading?.player_options?<label className="note-player">棋手<select aria-label="当前打法棋手" disabled={dirty} value={reading.player} onChange={e=>onPlayer(e.target.value)}>{reading.player_options.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>:<div className="chips">{note.meta.players.map(id=><span className="badge jade" key={id}>{name(id)}</span>)}</div>}
   <div className="chips note-core"><span className="muted">核心英雄：</span>{note.meta.core_heroes.map(id=><span className="badge" key={id}>{name(id)}</span>)}</div>
   <span className="muted note-factions">必须阵营：{note.meta.required_factions.map(name).join('、')||(note.meta.late_variants?.length?'随组合查看':'待确认')}</span>
  </div>}
 </header>;
}
