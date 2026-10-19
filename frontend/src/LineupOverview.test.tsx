import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import LineupOverview from './LineupOverview';
import {newPreset} from './overview';
import type {Note} from './types';

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
