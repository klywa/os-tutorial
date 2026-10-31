import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {CardImage,getCard} from './EntityCards';
import type {CardDetail} from './types';
afterEach(()=>{vi.unstubAllGlobals();vi.unstubAllEnvs();});
it('loads published card details with skills, enhancements, stats and sanitized sources intact',async()=>{
 const card:CardDetail={id:'public-card-contract',name:'测试英雄',category:'heroes',aliases:[],effect:'技能效果',tier:2,awakened:false,faction:{id:'f',name:'阵营'},skills:[{id:1,name:'测试技能',effect:'造成伤害',enhancements:[{level:2,effect:'额外伤害'}]}],skills_source:null,stats:{生命:100},attributes:{},sources:[],retrieved_at:null,version:null};
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(card),{status:200})));
 const result=await getCard(card.id);
 expect(result.skills[0].enhancements[0].effect).toBe('额外伤害');expect(Object.entries(result.stats)).toEqual([['生命',100]]);expect(result.sources).toEqual([]);
});
it('renders thumb and full card images under the published site base path',()=>{
 vi.stubEnv('BASE_URL','/os-tutorial/');
 const card={id:'image',name:'测试卡',thumb_url:'/api/card-images/image/thumb',image_url:'/api/card-images/image/image'} as CardDetail;
 expect(renderToStaticMarkup(<CardImage card={card}/>)).toContain('src="/os-tutorial/api/card-images/image/thumb"');
 expect(renderToStaticMarkup(<CardImage card={card} large/>)).toContain('src="/os-tutorial/api/card-images/image/image"');
});
