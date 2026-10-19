import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import SearchConditions,{searchKeywords,pasteConditions} from './SearchConditions';
it('deduplicates OR clauses without breaking words inside each clause',()=>{
 expect(searchKeywords([' 姜导 韩信 ','','大河龙蛇','姜导 韩信'])).toEqual(['姜导 韩信','大河龙蛇']);
 expect(pasteConditions(['旧条件','保留'],0,'姜导 韩信\r\n大河龙蛇\n姜导 韩信')).toEqual(['姜导 韩信','大河龙蛇','保留']);
});
it('exposes labelled OR rows and strict matching toggle with touch controls',()=>{
 const html=renderToStaticMarkup(createElement(SearchConditions,{rows:['甲','乙'],strict:true,onRows:()=>{},onStrict:()=>{}}));
 expect(html).toContain('添加或条件');expect(html).toContain('严格匹配');expect(html).toContain('checked');
 expect(html).toContain('搜索条件 2');expect(html).toContain('删除条件 1');expect(html).toContain('>或<');
});
