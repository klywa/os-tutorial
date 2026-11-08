import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import TemplateHelp from './TemplateHelp';
import TemplateLibrary from './TemplateLibrary';
import {AuthContext,type Role} from './auth';
import {helpExamples,helpMarkdown,helpExampleLink} from './templateHelpContent';

describe('template protocol help',()=>{
 it('makes help available to every reading role',()=>{
  for(const role of ['viewer','annotator','admin'] as Role[]){
   const html=renderToStaticMarkup(<AuthContext.Provider value={{session:{mode:'local',role,username:null,base_path:'/'},refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><TemplateLibrary notes={[]} options={{entities:[],tags:[],types:[]} as never}/></AuthContext.Provider>);
   expect(html).toContain('>帮助</button>');
  }
 });
 it('renders canonical Markdown tables and exact formatted examples as read-only code',()=>{
  const html=renderToStaticMarkup(<TemplateHelp onClose={()=>{}}/>);
  expect(html).toContain('aria-label="话术模板库帮助"');
  expect(html).toContain('<table>');expect(html).toContain('schema_version');
  expect(helpMarkdown).toContain('闭区间');
  for(const example of helpExamples){expect(html).toContain('aria-label="'+example.title+' JSON"');const document=JSON.parse(example.code);expect(document.kind).toBe('speech-template-library');expect(document.schema_version).toBe(2);expect(document.groups.every((g:{utterances:unknown[];conditions:Record<string,unknown>[]})=>g.utterances.every(u=>typeof u==='string')&&g.conditions.every(c=>!('id' in c))&&!('related_entities' in g))).toBe(true);}
  expect(html.match(/readOnly=""/g)).toHaveLength(2);
  expect(html).not.toContain('entity-chip');expect(html).not.toContain('href="examples/');
  expect(helpExampleLink('examples/speech-template-library.json')).toBe('#template-help-complete');
 });
});
