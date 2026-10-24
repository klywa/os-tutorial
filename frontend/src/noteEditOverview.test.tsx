import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import BranchEditor from './BranchEditor';
import LineupOverview from './LineupOverview';
import {newPreset,stageOperations} from './overview';
import type {Note,ReadingDocument} from './types';

const note={id:'n',title:'测试打法',type:'lineup',revision:'r',claims:[{id:'early',section:'前期运营',text:'前期正文'}],meta:{players:[],compositions:{early:[{hero:'甲英雄',necessity:'required',role:''}],middle:[],late:[]}}} as unknown as Note;
const document={note_id:'n',revision:'r',player:'p',branch:'one',scope_sections:{common:{},branch:{}},player_options:[{id:'p',name:'昭君'}],overview_operations:{early:[{markdown:'前期正文',claim_refs:['early'],route_ids:[],route_names:[]}],middle:[],late:[{markdown:'后期操作',claim_refs:['late'],route_ids:[],route_names:[]}],improvement:[{markdown:'培养优先级',claim_refs:['improve'],route_ids:[],route_names:[]}]}} as unknown as ReadingDocument;
it('offers the shared title above the branch editing scope',()=>{
 const html=renderToStaticMarkup(<BranchEditor note={note} document={document} onSaved={()=>{}} onCancel={()=>{}} onDirty={()=>{}}/>);
 expect(html).toContain('aria-label="笔记标题"');expect(html).toContain('测试打法');expect(html).toContain('整篇笔记');
 expect(html.indexOf('笔记标题')).toBeLessThan(html.indexOf('编辑范围'));
});
it('renders projected operation below heroes and improvement after late operation',()=>{
 const preset=newPreset('default','默认阵容');preset.stages.early.claim_refs=['early'];
 const html=renderToStaticMarkup(<LineupOverview note={{...note,meta:{...note.meta!,overview:{version:1,presets:[preset]}}}} operations={document.overview_operations}/>);
 expect(html.indexOf('甲英雄')).toBeLessThan(html.indexOf('前期正文'));
 expect(html.match(/前期正文/g)).toHaveLength(1);
 expect(html.indexOf('后期操作')).toBeLessThan(html.indexOf('后期提升思路'));
 expect(html.indexOf('后期提升思路')).toBeLessThan(html.indexOf('培养优先级'));
});
it('keeps route restrictions and deduplicates configured descriptions and references',()=>{
 const preset=newPreset('p','方案','v');preset.stages.early.description='前期正文';preset.stages.early.claim_refs=['early'];
 const configured={...note,meta:{...note.meta!,operation_routes:[{id:'r',name:'速升',condition:'',advantages:'',risks:'',transition:'',claim_refs:[],variant_ids:['v'],phases:{early:['early'],middle:[],late:[]}}]}};
 expect(stageOperations(configured,preset,'early',document.overview_operations,'r').advice).toEqual([]);
 preset.stages.early.description='';preset.stages.early.claim_refs=[];
 const operations={...document.overview_operations!,early:[{markdown:'路线专属',claim_refs:['early'],route_ids:['r'],route_names:['速升']},{markdown:'共用操作',claim_refs:['c'],route_ids:[],route_names:[]}]};
 expect(stageOperations(configured,preset,'early',operations,'r').advice).toHaveLength(2);
 expect(stageOperations(configured,preset,'early',operations).advice.map(r=>r.markdown)).toEqual(['共用操作']);
 preset.variant_id='unconfirmed';
 expect(stageOperations(configured,preset,'early',operations,'r').advice.map(r=>r.markdown)).toEqual(['共用操作']);
});

it('uses only current visible JSON operations instead of legacy claim fallbacks',()=>{
 const preset=newPreset('p','方案');preset.stages.early.claim_refs=['early'];
 const current={...note,document:{schema_version:6,nodes:[]}} as Note;
 const operations={...document.overview_operations!,early:[{markdown:'当前正文',claim_refs:[],route_ids:[],route_names:[]}]};
 expect(stageOperations(current,preset,'early',operations).advice.map(r=>r.markdown)).toEqual(['当前正文']);
});
