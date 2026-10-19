import {useCards,CardImage} from './EntityCards';
import {lineupHeroes} from './model';
import type {Note} from './types';
export default function NoteDirectory({notes,active,onSelect}:{notes:Note[];active:string;onSelect:(id:string)=>void}){
 const cards=useCards();
 if(!notes.length)return <p className="empty directory-empty">没有符合条件的笔记</p>;
 return <div className="note-directory" aria-label="笔记列表">{notes.map(n=><button key={n.id} aria-label={n.title} aria-current={active===n.id?'page':undefined} className={'note-option directory-note '+(active===n.id?'active':'')} onClick={()=>onSelect(n.id)}><span className="note-icon" aria-hidden="true">{({lineup:'◈',player:'♙',other:'▤'})[n.type]}</span><span className="directory-note-body"><strong>{n.title}</strong>{n.type==='lineup'&&<span className="directory-portraits">{[...new Set(lineupHeroes(n))].map(id=>cards.find(c=>c.id===id)).filter(c=>!!c).map(card=><CardImage key={card.id} card={card}/>)}</span>}</span></button>)}</div>;
}
