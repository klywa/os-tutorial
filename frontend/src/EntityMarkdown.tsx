import {memo} from 'react';
import Markdown,{defaultUrlTransform} from 'react-markdown';
import {appUrl} from './urls';
import type {Components} from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {EntityText} from './EntityCards';
const EntityMarkdown=memo(function EntityMarkdown({children,components={}}:{children:string;components?:Components}){return <Markdown urlTransform={url=>{const safe=defaultUrlTransform(url);return safe?appUrl(safe):safe;}} remarkPlugins={[remarkGfm]} components={{p:({children})=><p><EntityText>{children}</EntityText></p>,li:({children})=><li><EntityText>{children}</EntityText></li>,th:({children})=><th><EntityText>{children}</EntityText></th>,td:({children})=><td><EntityText>{children}</EntityText></td>,h2:({children})=><h2><EntityText>{children}</EntityText></h2>,h3:({children})=><h3><EntityText>{children}</EntityText></h3>,...components}}>{children}</Markdown>;});
export default EntityMarkdown;
