import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {Note,ReadingDocument} from './types';

export default function Reading({document,section,full,note,onNote}:{document:ReadingDocument;section:string;full:boolean;note:Note;onNote:(id:string)=>void}){
 const sections=full?document.sections:document.sections.filter(s=>s.title===section);
 return <div className="shared-reading">{sections.map(s=><section className="strategy reading-chapter" data-section={s.title} id={s.id} key={s.id}>
  <h2>{s.title}</h2><div className="prose"><Markdown remarkPlugins={[remarkGfm]} components={{
   table:({children})=><div className="reading-table" tabIndex={0} role="region" aria-label={`${s.title}表格，可横向滚动`}><table>{children}</table></div>,
   a:({href,children})=>{const related=note.related.find(n=>n.title===children);return related?<button className="link-button" onClick={()=>onNote(related.id)}>{children}</button>:<a href={href} target="_blank" rel="noreferrer">{children}</a>;}
  }}>{s.markdown}</Markdown></div>
 </section>)}</div>;
}
