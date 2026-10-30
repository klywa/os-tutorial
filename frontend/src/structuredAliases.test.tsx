import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import StructuredEditor from './StructuredEditor';
import {parseNoteAliases} from './noteAliases';
import type {Note} from './types';

it('keeps each complete website name as one alias entry',()=>{
 expect(parseNoteAliases(' 旧名 \n大河流域 · 公孙离 · 虞姬\n旧名\n\n')).toEqual(['旧名','大河流域 · 公孙离 · 虞姬']);
});
it('exposes existing aliases in the canonical lineup editor',()=>{
 const note={id:'n',type:'lineup',aliases:['旧名','网站名'],document:{schema_version:6,nodes:[]}} as unknown as Note;
 const html=renderToStaticMarkup(<StructuredEditor note={note} onSaved={()=>{}} onCancel={()=>{}} onDirty={()=>{}}/>);
 expect(html).toContain('搜索别名');expect(html).toContain('旧名\n网站名');expect(html).toContain('每行一个别名');
});
