import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import QuickCreateRows,{pasteLineupRows,advancesRow} from './QuickCreateRows';
it('parses two spreadsheet columns and ignores blank lines',()=>{expect(pasteLineupRows('河洛木兰\t木兰、复生\r\n李信\t牺牲信\n\n')).toEqual([{common_name:'河洛木兰',aliases:'木兰、复生'},{common_name:'李信',aliases:'牺牲信'}]);expect(pasteLineupRows('\t只有别名')).toEqual([{common_name:'',aliases:'只有别名'}]);});
it('shows only two editable fields and preserves row-specific failures',()=>{const html=renderToStaticMarkup(createElement(QuickCreateRows,{rows:[{client_id:'a',common_name:'草稿',aliases:'别名'}],onChange:()=>{},busy:false,errors:{a:'同名阵容已存在'}}));expect(html.match(/<input/g)).toHaveLength(2);expect(html).toContain('草稿');expect(html).toContain('同名阵容已存在');expect(html).not.toContain('英雄成员');});

it('does not advance on IME confirmation or composing key code',()=>{expect(advancesRow('Enter',true,13)).toBe(false);expect(advancesRow('Enter',false,229)).toBe(false);expect(advancesRow('Enter',false,13)).toBe(true);expect(advancesRow('Tab',false,9)).toBe(false);});
