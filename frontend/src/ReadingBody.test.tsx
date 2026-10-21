import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import ReadingBody from './ReadingBody';
import type {Note,ReadingDocument} from './types';

it('places the principle before overview once and preserves section ids',()=>{
 const document={note_id:'any',revision:'r',profile:'shared',sections:[{id:'principle',title:'核心原理',markdown:'双输出共同成长'},{id:'heroes',title:'英雄',markdown:'购买条件'}]} as ReadingDocument;
 const html=renderToStaticMarkup(<ReadingBody document={document} section="英雄" full note={{related:[]} as unknown as Note} onNote={()=>{}} overview={<div>阵容概览</div>}/>);
 expect(html.indexOf('双输出共同成长')).toBeLessThan(html.indexOf('阵容概览'));
 expect(html.indexOf('阵容概览')).toBeLessThan(html.indexOf('购买条件'));
 expect(html.match(/双输出共同成长/g)).toHaveLength(1);
 expect(html).toContain('id="principle"');expect(html).toContain('id="heroes"');
});
