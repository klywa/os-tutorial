import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import TopicPicker from './TopicPicker';
it('allows filtering retained historical lineups after disabling, but hides them for new edits',()=>{
 const props={label:'主题阵容',choices:[{id:'lineup:1',name:'历史阵容',enabled:false}],value:[],onChange:()=>{}};
 expect(renderToStaticMarkup(<TopicPicker {...props} includeInactive/>)).toContain('历史阵容');
 expect(renderToStaticMarkup(<TopicPicker {...props}/>)).not.toContain('历史阵容');
});
it('shows the common lineup name while retaining the original identity',()=>{
 const html=renderToStaticMarkup(<TopicPicker label="主题阵容" choices={[{id:'l',name:'网站原名',common_name:'大河龙蛇',display_name:'大河龙蛇'}]} value={['l']} onChange={()=>{}}/>);
 expect(html).toContain('大河龙蛇');expect(html).toContain('网站原名');
});
