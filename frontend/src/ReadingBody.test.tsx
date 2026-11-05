import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import ReadingBody from './ReadingBody';
import type {Note,ReadingDocument} from './types';
import type {KnowledgeDocument} from './types';

it.each(['shared','json-v6'])('places play tips between principle and overview in %s',profile=>{
 const nodes:KnowledgeDocument['nodes']=[
  {id:'principle',type:'heading',level:2,title:'核心原理'},
  {id:'p',type:'entry',key:'正文',show_key:false,value:'核心内容'},
  {id:'tips',type:'heading',level:2,title:'打法要点'},
  {id:'t',type:'entry',key:'正文',show_key:true,value:'待补充'},
  {id:'heroes',type:'heading',level:2,title:'英雄'},
  {id:'h',type:'entry',key:'正文',show_key:false,value:'英雄内容'}
 ];
 const document:ReadingDocument={note_id:'test',revision:'r',profile,section_aliases:{},
  ...(profile==='json-v6'?{document:{schema_version:6,nodes} as KnowledgeDocument}:{}),
  sections:[
   {id:'principle',title:'核心原理',nodes:nodes.slice(0,2),markdown:'核心内容'},
   {id:'tips',title:'打法要点',nodes:nodes.slice(2,4),markdown:'正文：待补充'},
   {id:'heroes',title:'英雄',nodes:nodes.slice(4),markdown:'英雄内容'}
  ]};
 const html=renderToStaticMarkup(<ReadingBody document={document} section="打法要点" full note={{related:[]} as unknown as Note} onNote={()=>{}} overview={<div>图形阵容概览</div>}/>);
 expect(html.indexOf('核心内容')).toBeLessThan(html.indexOf('待补充'));
 expect(html.indexOf('待补充')).toBeLessThan(html.indexOf('图形阵容概览'));
 expect(html.indexOf('图形阵容概览')).toBeLessThan(html.indexOf('英雄内容'));
 expect(html.match(/待补充/g)).toHaveLength(1);
 expect(html).toContain('id="tips"');
});

it('places the principle before overview once and preserves section ids',()=>{
 const document={note_id:'any',revision:'r',profile:'shared',sections:[{id:'principle',title:'核心原理',markdown:'双输出共同成长'},{id:'heroes',title:'英雄',markdown:'购买条件'}]} as ReadingDocument;
 const html=renderToStaticMarkup(<ReadingBody document={document} section="英雄" full note={{related:[]} as unknown as Note} onNote={()=>{}} overview={<div>阵容概览</div>}/>);
 expect(html.indexOf('双输出共同成长')).toBeLessThan(html.indexOf('阵容概览'));
 expect(html.indexOf('阵容概览')).toBeLessThan(html.indexOf('购买条件'));
 expect(html.match(/双输出共同成长/g)).toHaveLength(1);
 expect(html).toContain('id="principle"');expect(html).toContain('id="heroes"');
});

it('keeps the overview between principle and remaining JSON chapters after loading',()=>{
 const body={schema_version:6,nodes:[{id:'title',type:'heading',level:1,title:'阵容'},{id:'principle',type:'heading',level:2,title:'核心原理'},{id:'p',type:'entry',key:'正文',show_key:false,value:'核心内容'},{id:'heroes',type:'heading',level:2,title:'英雄'},{id:'h',type:'entry',key:'正文',show_key:false,value:'英雄内容'}]} as KnowledgeDocument;
 const document={note_id:'json',revision:'r',profile:'json-v6',document:body,sections:[{id:'principle',title:'核心原理',nodes:body.nodes.slice(1,3),markdown:''},{id:'heroes',title:'英雄',nodes:body.nodes.slice(3),markdown:''}]} as ReadingDocument;
 const html=renderToStaticMarkup(<ReadingBody document={document} section="英雄" full note={{related:[]} as unknown as Note} onNote={()=>{}} overview={<div>图形阵容概览</div>}/>);
 expect(html).toContain('图形阵容概览');
 expect(html.match(/图形阵容概览/g)).toHaveLength(1);
 expect(html.indexOf('核心内容')).toBeLessThan(html.indexOf('图形阵容概览'));
 expect(html.indexOf('图形阵容概览')).toBeLessThan(html.indexOf('英雄内容'));
});
