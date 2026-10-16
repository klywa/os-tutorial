import type {ReadingDocument} from './types';
export function resolveReadingSection(document:ReadingDocument,section:string){
 const title=document.section_aliases[section]??section;
 return document.sections.some(s=>s.title===title)?title:(document.sections[0]?.title??section);
}
