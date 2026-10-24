import type {ComponentProps,ReactNode} from 'react';
import Reading from './KnowledgeReader';

/** Keep chapter content, links and anchors in the shared reader. */
export default function ReadingBody({overview,...props}:ComponentProps<typeof Reading>&{overview?:ReactNode}){
 if(props.document.document)return <Reading {...props}/>;
 const principle=props.document.sections.filter(s=>s.title==='核心原理');
 const rest=props.document.sections.filter(s=>s.title!=='核心原理');
 return <>{!!principle.length&&<Reading {...props} sections={principle}/>} {overview}<Reading {...props} sections={rest}/></>;
}
