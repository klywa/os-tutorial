import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {splitAliases,changeNameDraft,namePayload,filterManagedLineups,detailAfterSave,prefillDetail} from './lineupEditing';
import LineupQuickList from './LineupQuickList';
import {LineupConfirm} from './LineupConfirm';
import type {Lineup} from './types';
const a={id:'a',name:'原名',common_name:'旧常用',aliases:['旧别名'],heroes:['h'],note_ids:[],enabled:true,revision:3,description:'司空震'} as Lineup;
it('uses an accessible in-page confirmation for recoverable operations',()=>{
 const html=renderToStaticMarkup(createElement(LineupConfirm,{message:'移入已删除，历史内容保留',onAnswer:()=>{}}));expect(html).toContain('确认阵容操作');expect(html).toContain('历史内容保留');expect(html).toContain('取消');expect(html).toContain('确认');
});
it('prefilled quick names remain pending when a related section saves first',()=>{
 const drafts=changeNameDraft(changeNameDraft({},a,{common_name:'列表新名'}),a,{aliases:['列表别名']});
 const prepared=prefillDetail(a,drafts.a);const base=JSON.parse(prepared.base);
 const related=detailAfterSave(prepared.edit,prepared.aliases,base.edit,base.aliases,{...a,revision:4},['note_ids']);
 expect(related.edit.common_name).toBe('列表新名');expect(related.aliases).toBe('列表别名');
 expect(base.edit.common_name).toBe('旧常用');
});
it('saving a related subsection preserves other pending detail fields',()=>{
 const edited={...a,common_name:'待保存名',note_ids:['n']};
 const next=detailAfterSave(edited,'待保存别名',a,'旧别名',{...a,note_ids:['n'],revision:4},['note_ids']);
 expect(next.edit.common_name).toBe('待保存名');expect(next.aliases).toBe('待保存别名');expect(next.edit.note_ids).toEqual(['n']);expect(next.edit.revision).toBe(4);
 const metadata=detailAfterSave(edited,'旧别名',a,'旧别名',{...a,common_name:'待保存名',revision:4},['common_name','aliases']);expect(metadata.edit.note_ids).toEqual(['n']);
});
it('keeps independent drafts and base revisions through filtering and raw alias input',()=>{
 let drafts=changeNameDraft({},a,{common_name:''});drafts=changeNameDraft(drafts,{...a,id:'b'},{text:'海陆空， 龙蛇\n海陆空'});
 expect(Object.keys(drafts)).toHaveLength(2);expect(namePayload(drafts)).toEqual([{id:'a',revision:3,common_name:'',aliases:['旧别名']},{id:'b',revision:3,common_name:'旧常用',aliases:['旧别名','海陆空','龙蛇']}]);
 expect(filterManagedLineups([a],'司空震','all',drafts)).toHaveLength(1);expect(Object.keys(drafts)).toHaveLength(2);
 expect(Object.keys(changeNameDraft(drafts,a,{common_name:'旧常用'}))).toEqual(['b']);
 expect(splitAliases('甲,甲；乙\n 丙，')).toEqual(['甲','乙','丙']);
});
it('separates deleted records and searches edited names without including merged rows',()=>{
 const deleted={...a,id:'d',deleted_at:'today',enabled:false};const merged={...a,id:'m',merged_into:'a'};
 expect(filterManagedLineups([a,deleted,merged],'','all',{}).map(r=>r.id)).toEqual(['a']);
 expect(filterManagedLineups([a,deleted],'','deleted',{}).map(r=>r.id)).toEqual(['d']);
 const drafts=changeNameDraft({},a,{common_name:'新常用'});expect(filterManagedLineups([a],'新常用','all',drafts)).toHaveLength(1);
});
it('renders compact editable names, alias removal, and restore-only deleted rows',()=>{
 const props={rows:[a],drafts:{},conflicts:[],busy:false,onDraft:()=>{},onEdit:()=>{},onDelete:()=>{},onRestore:()=>{}};
 const html=renderToStaticMarkup(createElement(LineupQuickList,props));expect(html).toContain('常用名：原名');expect(html).toContain('移除别名：旧别名');expect(html).toContain('详细编辑');
 const trash=renderToStaticMarkup(createElement(LineupQuickList,{...props,rows:[{...a,deleted_at:'today'}]}));expect(trash).toContain('恢复阵容');expect(trash).not.toContain('详细编辑');
});
