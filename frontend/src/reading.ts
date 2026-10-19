import type {ReadingDocument} from './types';
import type {Note,Options} from './types';
export function claimMarkdown(c:{text:string;condition?:string;inference?:boolean}){
 return (c.inference?'推测：':'')+(c.condition?'**'+c.condition.replace(/[。；：]+$/,'')+'：** ':'')+c.text.replace(/(\*\*[^*\n]+：\*\*)(?=\S)/g,'$1 ');
}
export function loadReaderData(request:<T>(path:string)=>Promise<T>){
 return Promise.all([request<Note[]>('notes'),request<Options>('options')]);
}
export function resolveReadingSection(document:ReadingDocument,section:string){
 const title=document.section_aliases[section]??section;
 return document.sections.some(s=>s.title===title)?title:(document.sections[0]?.title??section);
}
