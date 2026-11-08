import helpMarkdown from '../../docs/template-library.md?raw';
import minimal from '../../docs/examples/speech-template-library-minimal.json?raw';
import complete from '../../docs/examples/speech-template-library.json?raw';

export {helpMarkdown};
export const helpExamples=[
 {id:'minimal',title:'最小示例',filename:'speech-template-library-minimal.json',source:minimal},
 {id:'complete',title:'完整示例',filename:'speech-template-library.json',source:complete},
].map(example=>({...example,code:JSON.stringify(JSON.parse(example.source),null,2)}));
export const helpDocument=helpMarkdown.replace(/\[([^\]]+)\]\(examples\/speech-template-library(?:-minimal)?\.json\)/g,'$1（见文末示例）')
 +'\n\n## JSON 示例\n\n'+helpExamples.map(example=>'### '+example.title+'\n\n```json\n'+example.code+'\n```\n').join('\n');
export function helpExampleLink(href:string|undefined){
 const example=helpExamples.find(example=>href==='examples/'+example.filename);
 return example?'#template-help-'+example.id:href;
}
