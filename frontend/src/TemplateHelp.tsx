import {useRef,useState} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {TemplateDialog} from './TemplateEditor';
import {helpMarkdown,helpExamples,helpExampleLink,helpDocument} from './templateHelpContent';
import './templateHelp.css';

function HelpExample({example}:{example:typeof helpExamples[number]}){
 const field=useRef<HTMLTextAreaElement>(null),[message,setMessage]=useState(''),[copying,setCopying]=useState(false);
 async function copy(){
  setCopying(true);setMessage('');
  try{if(!navigator.clipboard?.writeText)throw Error('clipboard unavailable');await navigator.clipboard.writeText(example.code);setMessage('JSON 已复制');}
  catch{field.current?.focus();field.current?.select();setMessage('复制失败，已选中全部 JSON，请按 Ctrl+C 或 ⌘C 复制；手机可长按复制。');}
  finally{setCopying(false);}
 }
 function download(){
  const url=URL.createObjectURL(new Blob([example.code+'\n'],{type:'application/json;charset=utf-8'})),link=document.createElement('a');
  link.href=url;link.download=example.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 return <section id={'template-help-'+example.id} className="template-help-example" aria-label={example.title}>
  <h3>{example.title}</h3><label>{example.title} JSON<textarea ref={field} aria-label={example.title+' JSON'} readOnly spellCheck={false} value={example.code} rows={14}/></label>
  <div className="template-help-actions"><button disabled={copying} onClick={()=>void copy()}>一键复制{example.title}</button><button onClick={download}>下载{example.title}</button></div>
  {message&&<p role="status">{message}</p>}
 </section>;
}

export default function TemplateHelp({onClose}:{onClose:()=>void}){
 function exportDocument(){
  const url=URL.createObjectURL(new Blob([helpDocument],{type:'text/markdown;charset=utf-8'})),link=document.createElement('a');
  link.href=url;link.download='template-library-help.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 return <TemplateDialog title="话术模板库帮助" onClose={onClose} wide><div className="template-help">
  <div className="template-help-actions"><button onClick={exportDocument}>导出帮助文档</button><span className="muted">下载完整协议和两份 JSON 示例（Markdown）</span></div>
  <div className="template-help-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{a:({href,children})=><a href={helpExampleLink(href)} tabIndex={0}>{children}</a>,table:({children})=><div className="template-help-table" role="region" aria-label="协议字段表" tabIndex={0}><table>{children}</table></div>}}>{helpMarkdown}</ReactMarkdown></div>
  {helpExamples.map(example=><HelpExample key={example.id} example={example}/>)}
  <footer><button onClick={onClose}>关闭帮助</button></footer>
 </div></TemplateDialog>;
}
