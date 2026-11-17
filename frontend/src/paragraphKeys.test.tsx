import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {paragraphKeyRanges} from './paragraphKeys';
import {ParagraphTextarea} from './ParagraphTextarea';

it('finds known labels and long free-form conditions inside a paragraph',()=>{
 const first='场上有4名供级英雄，手中有双传承加1张遗志，目标主C至少有1张：';
 const value=first+'对供级英雄用传承。 核心机制:说明；觉醒需求：一张。\n另一种条件：操作。';
 expect(paragraphKeyRanges(value).map(({start,end})=>value.slice(start,end)))
  .toEqual([first,'核心机制:','觉醒需求：','另一种条件：']);
});

it('leaves URLs, times, Markdown links and code outside custom labels',()=>{
 const value='看 https://example.com/标签：路径。时间 12:35。\n`核心机制：示例`。\n[觉醒需求：链接](https://example.com)。\n```\n测试：不匹配\n```\n条件：操作。';
 expect(paragraphKeyRanges(value).map(({start,end})=>value.slice(start,end))).toEqual(['条件：']);
});

it('keeps the editable textarea value unchanged and hides the painted copy from accessibility',()=>{
 const html=renderToStaticMarkup(<ParagraphTextarea aria-label="正文" value={'条件：操作。\n'} readOnly/>);
 expect(html).toContain('<mark>条件：</mark>');
 expect(html).toContain('aria-hidden="true"');
 expect(html).toMatch(/<textarea[^>]*aria-label="正文"[^>]*>条件：操作。\n<\/textarea>/);
});
