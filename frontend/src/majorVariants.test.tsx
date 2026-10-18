import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import MajorVariantsEditor from './MajorVariantsEditor';
import {majorRemovalBlocked} from './majorVariants';
import type {Meta,Note,ReadingDocument} from './types';
import Reading from './KnowledgeReader';
it('edits all six evidence-backed dimensions without duplicating member lists',()=>{
 const meta={major_variants:[{id:'skill',name:'技能循环',condition_refs:[],baseline_refs:[],claim_refs:[],late_variant_ids:['a'],operation_route_ids:['r'],differences:Object.fromEntries(['heroes','mechanism','tempo','equipment','talents','skills'].map(k=>[k,{status:'unknown',claim_refs:[]}]))}],late_variants:[{id:'a',name:'组合甲'}],operation_routes:[{id:'r',name:'路线甲'}]} as unknown as Meta;
 const html=renderToStaticMarkup(createElement(MajorVariantsEditor,{meta,note:{claims:[]} as unknown as Note,onChange:()=>{}}));
 for(const name of ['英雄组成','成长／输出机制','运营节奏','装备','天赋','技能'])expect(html).toContain(name);
 expect(html).toContain('比较主干依据');expect(html).toContain('采用条件与转入限制');
 expect(majorRemovalBlocked(meta,'late_variant_ids','a')).toBe(true);expect(majorRemovalBlocked(meta,'operation_route_ids','absent')).toBe(false);
});
it('keeps internal references in the reader rather than opening a new tab',()=>{
 const document={sections:[{id:'chapter-1',title:'主要变阵',markdown:'参见[核心机制](#chapter-2)'},{id:'chapter-2',title:'核心机制',markdown:'主干'}]} as ReadingDocument;
 const html=renderToStaticMarkup(createElement(Reading,{document,section:'主要变阵',full:false,note:{related:[]} as unknown as Note,onNote:()=>{},onSection:()=>{}}));
 expect(html).not.toContain('target="_blank"');expect(html).toContain('核心机制');
});
it('retains current ban warnings alongside shared composition reading',()=>{
 const note={related:[],meta:{required_factions:[],ban_conditions:[],late_variants:[{id:'a',name:'组合甲',required_factions:['blocked'],ban_conditions:[]},{id:'b',name:'组合乙',required_factions:[],ban_conditions:[]}]}} as unknown as Note;
 const document={sections:[{id:'chapter-1',title:'运营路线与后期组合',markdown:'组合说明'}]} as ReadingDocument;
 const html=renderToStaticMarkup(createElement(Reading,{document,section:'运营路线与后期组合',full:false,note,onNote:()=>{},banned:['blocked','other']}));
 expect(html).toContain('组合必需英雄无法获取');expect(html).toContain('多个阵营同时禁用');
});
