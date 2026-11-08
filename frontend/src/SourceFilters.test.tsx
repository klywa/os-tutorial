import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import SourceFilters from './SourceFilters';

it('offers five searchable single-choice filters while retaining saved selections',()=>{
 const html=renderToStaticMarkup(<SourceFilters sources={[]} filters={{author:'历史UP主',stage:'failed'}} catalog={{topic_players:[],topic_lineups:[],topic_heroes:[],topic_cards:[]}} onChange={()=>{}} onReset={()=>{}}/>);
 expect(html.match(/role="combobox"/g)).toHaveLength(5);
 expect(html).toContain('value="历史UP主"');
 expect(html).toContain('value="失败"');
 for(const label of ['关键词','UP主','批次','处理状态','沉淀状态'])expect(html).toContain(`aria-label="${label}"`);
});
