import legacyMarkdown from '../../docs/template-library.md?raw';
import currentMarkdown from '../../docs/template-library-v04.md?raw';
import minimal from '../../docs/examples/speech-template-library-minimal.json?raw';
import complete from '../../docs/examples/speech-template-library.json?raw';

export const helpMarkdown=currentMarkdown+'\n\n## 旧版语法参考\n\n'+legacyMarkdown;
export const helpExamples=[
 {id:'minimal',title:'最小示例',filename:'speech-template-library-minimal.json',source:minimal},
 {id:'complete',title:'完整示例',filename:'speech-template-library.json',source:complete},
].map(example=>({...example,code:JSON.stringify(JSON.parse(example.source),null,2)}));
export const helpDocument=helpMarkdown;
export function helpExampleLink(href:string|undefined){
 const example=helpExamples.find(example=>href==='examples/'+example.filename);
 return example?'#template-help-'+example.id:href;
}
