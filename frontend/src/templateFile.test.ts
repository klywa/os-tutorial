import {describe,expect,it,vi} from 'vitest';
import {fileImportDocument,parseTemplateFile,previewTemplateFileExport,reviewLocalGroup,saveTemplateFile,templateGroupSeason,withLocalEntitySnapshot,writeLocalReviewStatus,writeTemplateDocument} from './templateFile';

const input={
 kind:'speech-template-library',schema_version:3,
 events:[{name:'购买',signature:'购买(目标: 英雄)',parameters:[{key:'target',name:'目标',type:'entity'}]},{name:'独立事件',parameters:[]}],
 groups:[{name:'选中组',event_name:'购买',expression:'',utterances:['买这张。'],batch:['试验批次']},{name:'未选中组',event_name:'独立事件',expression:'',utterances:['只留在文件。']}],
};

describe('export to a template file',()=>{
 const group={...input.groups[0],id:'group_source'};
 const source={...input,groups:[group]};
 it('creates a v3 document and rejects a nonempty new destination',()=>{
  expect(previewTemplateFileExport(source,'','new').document).toEqual(source);
  expect(()=>previewTemplateFileExport(source,JSON.stringify(input),'new')).toThrow('已有内容');
 });
 it('replaces only identical IDs in place and preserves legacy rows and extensions',()=>{
  const sameName={...group,id:'group_other'};
  const original={...input,extension:true,groups:[input.groups[0],{...group,name:'原名称',extra:1},sameName]};
  const added={...input.groups[1],id:'group_add'};
  const preview=previewTemplateFileExport({...source,groups:[group,added]},JSON.stringify(original),'merge');
  expect(preview.changes.map(row=>row.action)).toEqual(['replace','add']);
  expect(preview.document.groups).toEqual([input.groups[0],group,sameName,added]);
  expect(preview.document.extension).toBe(true);
  expect(previewTemplateFileExport(source,JSON.stringify(preview.document),'merge').changed).toBe(false);
 });
 it('blocks event signature changes when other groups use the old event',()=>{
  const updated={...source,events:[{name:'购买',signature:'购买()',parameters:[]}]};
  const original={...source,groups:[group,input.groups[0]]};
  expect(()=>previewTemplateFileExport(updated,JSON.stringify(original),'merge')).toThrow('仍有其他模板组');
  expect(previewTemplateFileExport(updated,JSON.stringify(source),'merge').document.events[0]).toEqual(updated.events[0]);
 });
 it('rejects ambiguous legacy duplicates and invalid destinations',()=>{
  expect(()=>previewTemplateFileExport(input,JSON.stringify(input),'merge')).toThrow(/重复/);
  expect(()=>previewTemplateFileExport(source,'{}','merge')).toThrow('v3');
 });
 it('keeps target catalog extensions and adds a definition only for the needed event',()=>{
  const catalog={types:{},aliases:{},roots:{},operations:{},events:{购买:{parameters:{target:'英雄'},extra:true}}};
  const added={...input.groups[1],id:'group_add'};
  const preview=previewTemplateFileExport({...input,groups:[added]},JSON.stringify({...source,
   events:[input.events[0]],condition_catalog:catalog}),'merge');
  expect(preview.document.condition_catalog).toEqual({...catalog,events:{...catalog.events,独立事件:{category:'未分类',parameters:{}}}});
 });
 it('rejects an unknown target catalog and conflicting shared condition schemas',()=>{
  const original={...source,condition_catalog:{futureCatalog:true}};
  expect(()=>previewTemplateFileExport(source,JSON.stringify(original),'merge')).toThrow('无法识别的条件目录');
  const catalog={types:{},aliases:{},roots:{},operations:{},events:{}};
  const edited={...source,groups:[{...group,name:'新名称'}],condition_catalog:{...catalog,roots:{玩家:'玩家'}}};
  expect(()=>previewTemplateFileExport(edited,JSON.stringify({...source,condition_catalog:catalog}),'merge')).toThrow('条件目录不兼容');
 });
});

describe('browser template files',()=>{
 it('changes review metadata without rewriting the portable content or assigning an ID',()=>{
  const row={...input.groups[0],review_status:'final_reviewed',reviewed_by:'复核人',reviewed_at:'time',extra:'保留'};
  const file=parseTemplateFile(JSON.stringify({...input,groups:[row,input.groups[1]]}));
  const output=writeLocalReviewStatus(file,{...file.snapshot.groups[0],review_status:'ai_generated',reviewed_by:undefined,reviewed_at:undefined});
  expect(output.groups).toEqual([{...input.groups[0],review_status:'ai_generated',extra:'保留'},input.groups[1]]);
 });
 it('keeps nonselected events and groups out of the import payload',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const document=fileImportDocument(file,[file.snapshot.groups[0].id]);
  expect(document.groups).toEqual([input.groups[0]]);
  expect(document.events).toEqual([input.events[0]]);
  expect(JSON.stringify(document)).not.toContain('只留在文件。');
 });
 it('separates identical names in different seasons and imports only the selected version',()=>{
  const s2={...input.groups[0],version:'s2'};
  const file=parseTemplateFile(JSON.stringify({...input,groups:[input.groups[0],s2]}));
  expect(file.snapshot.groups[0].id).not.toBe(file.snapshot.groups[1].id);
  expect(fileImportDocument(file,[file.snapshot.groups[1].id]).groups).toEqual([s2]);
 });
 it('keeps custom versions visible in S1 and preserves their original label',()=>{
  const file=parseTemplateFile(JSON.stringify({...input,groups:[{...input.groups[0],version:'历史版本'}]}));
  expect(file.snapshot.groups[0].version).toBe('历史版本');
  expect(templateGroupSeason(file.snapshot.groups[0])).toBe('S1');
 });
 it('round-trips untouched rows while saving edited name-based data',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const group={...file.snapshot.groups[0],name:'已改名',utterances:[{id:'new',text:'已改话术'}]};
  const changed=writeTemplateDocument(file,[{kind:'group',action:'put',id:group.id,value:group}]);
  expect(changed.groups[0]).toMatchObject({name:'已改名',utterances:['已改话术'],event_name:'购买',batch:['试验批次']});
  expect(changed.groups[0]).not.toHaveProperty('id');
  expect(changed.groups[1]).toEqual(input.groups[1]);
  expect(changed.events).toEqual(input.events);
 });
 it('rewrites the names of existing groups when an event is renamed',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const event={...file.snapshot.events[0],name:'换个事件名'};
  const changed=writeTemplateDocument(file,[{kind:'event',action:'put',id:event.id,value:event}]);
  expect(changed.groups[0]).toMatchObject({event_name:'换个事件名',utterances:['买这张。']});
  expect(parseTemplateFile(JSON.stringify(changed)).snapshot.groups[0].event_id).toBe(parseTemplateFile(JSON.stringify(changed)).snapshot.events[0].id);
 });
 it('preserves review metadata on final approval and reopens edited final groups for review',()=>{
  const group=parseTemplateFile(JSON.stringify(input)).snapshot.groups[0];
  const time='2026-11-23T12:00:00.000Z';
  const approved=reviewLocalGroup(group,'终审人','final',time);
  expect(approved).toMatchObject({review_status:'final_reviewed',reviewed_by:'终审人',reviewed_at:time});
  const edited=reviewLocalGroup(approved,'编辑人','edit',time);
  expect(edited).toMatchObject({review_status:'initial_reviewed',last_modified_by:{kind:'user',username:'编辑人'}});
  expect(edited).not.toHaveProperty('reviewed_by');
 });
 it('records missing current cards and replaces old snapshots when the official catalog is unavailable',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const group={...file.snapshot.groups[0],version:'s2',expression:'target.名称 is "新卡"',
   entity_snapshot:{season:'S1',entities:{previous:{name:'旧卡'}}}};
  const event={...file.snapshot.events[0],parameters:[{id:'p',key:'target',name:'目标',type:'entity' as const,entity_categories:['heroes']}]};
  const snapshot=withLocalEntitySnapshot(group,event,undefined,[]).entity_snapshot;
  expect(snapshot?.season).toBe('S2');
  expect(Object.values(snapshot?.entities??{})).toEqual([{name:'新卡',missing:true}]);
 });
 it('refuses to replace the same file when it was changed outside the editor',async()=>{
  const expected=JSON.stringify(input);
  const handle={name:'模板.json',getFile:async()=>({text:async()=>expected+'\n'}),createWritable:vi.fn()};
  await expect(saveTemplateFile(handle,expected,input)).rejects.toThrow('文件已在其他地方修改');
  expect(handle.createWritable).not.toHaveBeenCalled();
 });
});
