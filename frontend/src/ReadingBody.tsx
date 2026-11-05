import type {ComponentProps,ReactNode} from 'react';
import Reading from './KnowledgeReader';

/** Keep chapter content, links and anchors in the shared reader. */
export default function ReadingBody({overview,...props}:ComponentProps<typeof Reading>&{overview?:ReactNode}){
 const principle=props.document.sections.filter(s=>s.title==='核心原理');
 const tips=props.document.sections.filter(s=>s.title==='打法要点');
 const rest=props.document.sections.filter(s=>!['核心原理','打法要点'].includes(s.title));
 return <>{!!principle.length&&<Reading {...props} sections={principle}/>} {!!tips.length&&<Reading {...props} sections={tips}/>} {overview}<Reading {...props} sections={rest}/></>;
}
