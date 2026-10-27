import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import LineupOverview from './LineupOverview';
import {newPreset} from './overview';
import type {Note} from './types';
import {ReviewProvider} from './NoteReview';

it('uses the body node for overview actions and copies unlinked legacy rows',()=>{
 const node={id:'original',type:'entry' as const,key:'购买清单',show_key:true,value:'当前建议'};
 const note={id:'n',title:'笔记',revision:'r',related:[],claims:[],document:{schema_version:6,nodes:[node]},meta:{players:[],compositions:{early:[],middle:[],late:[]}}} as unknown as Note;
 const operations={early:[{node_id:'original',markdown:'过期投影',claim_refs:[],route_ids:[],route_names:[]}],middle:[{markdown:'旧格式建议',claim_refs:[],route_ids:[],route_names:[]}],late:[],improvement:[]};
 const html=renderToStaticMarkup(<ReviewProvider note={note} onSaved={()=>{}} onDirty={()=>{}}><LineupOverview note={note} operations={operations}/></ReviewProvider>);
 expect(html).toContain('当前建议');expect(html).not.toContain('过期投影');
 expect(html).toContain('编辑段落：购买清单');expect(html).toContain('批注：购买清单');
 expect(html).toContain('复制段落：购买清单');expect(html).toContain('复制概览段落');
 expect(html.match(/编辑段落：/g)).toHaveLength(1);
});

it('keeps each stage role attached to its hero, including optional members',()=>{
 const note={id:'subjects',claims:[],meta:{players:[],compositions:{
  early:[{hero:'弈星',necessity:'required',role:'速五开局可单挂'}],
  middle:[{hero:'花木兰',necessity:'required',role:'主要输出'},{hero:'上官婉儿',necessity:'required',role:'整备自动使用古币'},{hero:'盾山',necessity:'optional',role:'缺少程咬金时过渡'}],late:[],
 }}} as unknown as Note;
 const html=renderToStaticMarkup(<LineupOverview note={note}/>);
 expect(html).toMatch(/<li[^>]*>.*?弈星.*?：.*?速五开局可单挂.*?<\/li>/);
 expect(html).toMatch(/<li[^>]*>.*?花木兰.*?：.*?主要输出.*?<\/li>/);
 expect(html).toMatch(/<li[^>]*>.*?上官婉儿.*?：.*?整备自动使用古币.*?<\/li>/);
 expect(html).toMatch(/<li[^>]*>.*?盾山.*?备选.*?：.*?缺少程咬金时过渡.*?<\/li>/);
 expect(html).toContain('阶段操作未配置');
 const preset=newPreset('default','默认阵容');preset.stages.early.description='完整阶段建议';
 note.meta!.overview={version:1,presets:[preset]};
 const explicit=renderToStaticMarkup(<LineupOverview note={note}/>);
 expect(explicit).toContain('完整阶段建议');expect(explicit).not.toContain('速五开局可单挂');
});
