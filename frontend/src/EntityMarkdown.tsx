import Markdown from 'react-markdown';
import type {Components} from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {EntityText} from './EntityCards';
export default function EntityMarkdown({children,components={}}:{children:string;components?:Components}){return <Markdown remarkPlugins={[remarkGfm]} components={{p:({children})=><p><EntityText>{children}</EntityText></p>,li:({children})=><li><EntityText>{children}</EntityText></li>,th:({children})=><th><EntityText>{children}</EntityText></th>,td:({children})=><td><EntityText>{children}</EntityText></td>,h2:({children})=><h2><EntityText>{children}</EntityText></h2>,h3:({children})=><h3><EntityText>{children}</EntityText></h3>,...components}}>{children}</Markdown>;}
