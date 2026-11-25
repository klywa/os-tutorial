import {describe,expect,it,vi} from 'vitest';
import {fileDeliveryDocument,fileImportDocument,fileTemplateScopeId,fixEditedLocalUtterances,parseTemplateFile,previewTemplateFileExport,reviewLocalGroup,saveTemplateFile,templateGroupSeason,withLocalEntitySnapshot,writeLocalComment,writeLocalReviewStatus,writeTemplateDocument} from './templateFile';

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
 it('merges a scope field and an equivalent inline v0.4 condition',()=>{
  const event={name:'解释为何购买英雄',signature:'解释为何购买英雄(arg1: 英雄, arg2: Array<英雄|效果牌>)'};
  const first={id:'first',name:'解释为何购买曹操',event_name:event.name,syntax_version:'0.4',extra_key:'曹操',
   scope:{lineup:'三分登场'},expression:'我方.等级 == 3',
   utterances:[{id:'u1',text:'曹操可以重复触发登场。'}]};
  const second={...first,id:'second',name:'合并前',scope:{},priority:15,
   expression:'我方.阵容名称 == "三分登场" and 我方.等级 == 3',
   utterances:[{id:'u2',text:'曹操能接起登场成长。'}]};
  const file=parseTemplateFile(JSON.stringify({...input,events:[event],groups:[first,second]}));
  const merged=new Map<string,string>();
  const value={...file.snapshot.groups[1],name:first.name};
  const saved=writeTemplateDocument(file,[{kind:'group',action:'put',id:value.id,value}],{},merged);
  expect(merged.get('second')).toBe('first');
  expect(saved.groups).toHaveLength(1);
  expect(saved.groups[0]).toMatchObject({priority:15});
 });
 it('merges equivalent saved groups in document order and preserves fixed speech and comment targets',()=>{
  const same={...input.groups[0],id:'first',review_status:'final_reviewed',reviewed_by:'audit',reviewed_at:'2026-01-01'};
  const later={...same,id:'later',name:'准备合并',utterances:['新增。','买这张。'],
   legacy_utterance_flags:{1:{text:'买这张。',fixed:true}},
   file_comments:[{id:'comment',by:'editor',at:'2026-01-01',body:'保留批注',utterance_id:'file-utterance-1',
    original_text:'买这张。',target_text:'买这张。'}]};
  const file=parseTemplateFile(JSON.stringify({...input,groups:[same,later,input.groups[1]]}));
  const groups=new Map<string,string>();
  const value={...file.snapshot.groups[1],name:same.name};
  const result=writeTemplateDocument(file,[{kind:'group',action:'put',id:value.id,value}],{},groups);
  const reopened=parseTemplateFile(JSON.stringify(result));
  expect(groups.get('later')).toBe('first');
  expect(reopened.snapshot.groups.map(row=>row.id)).toEqual(['first',file.snapshot.groups[2].id]);
  expect(reopened.snapshot.groups[0]).toMatchObject({review_status:null,utterances:[
   {id:'file-utterance-0',text:'买这张。',fixed:true},{id:'file-utterance-1',text:'新增。'},
  ]});
  expect(reopened.snapshot.groups[0].reviewed_by).toBeUndefined();
  expect(reopened.comments.get('first')).toMatchObject([{id:'comment',utterance_id:'file-utterance-0'}]);
 });
 it('keeps review details for copied speech and keeps different scopes, rules and events in separate groups',()=>{
  const same={...input.groups[0],id:'first',review_status:'final_reviewed',reviewed_by:'audit',reviewed_at:'2026-01-01'};
  const file=parseTemplateFile(JSON.stringify({...input,groups:[same,
   {...same,id:'other-scope',scope:{player:'甲'}},{...same,id:'other-rule',expression:'arg1 is "乙"'},
   {...same,id:'other-event',event_name:'独立事件'}]}));
  const groups=new Map<string,string>();
  const value={...file.snapshot.groups[0],id:'copy',review_status:null,reviewed_by:undefined,reviewed_at:undefined};
  const result=writeTemplateDocument(file,[{kind:'group',action:'put',id:value.id,value}],{},groups);
  const reopened=parseTemplateFile(JSON.stringify(result));
  expect([...groups]).toEqual([['copy','first']]);
  expect(reopened.snapshot.groups.map(row=>row.id)).toEqual(['first','other-scope','other-rule','other-event']);
  expect(reopened.snapshot.groups[0]).toMatchObject({review_status:'final_reviewed',reviewed_by:'audit',reviewed_at:'2026-01-01'});
 });
 it('fixes edited existing text while leaving new and unchanged utterances as supplied',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const group=file.snapshot.groups[0],old=group.utterances[0];
  const added={id:'new',text:'新增话术。'};
  const first=fixEditedLocalUtterances(group,{...group,utterances:[old,added]});
  expect(first.utterances).toEqual([old,added]);
  const next=fixEditedLocalUtterances(first,{...first,utterances:[{...old,text:'修改话术。',ignored:true},added]});
  const reopened=parseTemplateFile(JSON.stringify(writeTemplateDocument(file,[{kind:'group',action:'put',id:group.id,value:next}])));
  expect(reopened.snapshot.groups[0].utterances).toMatchObject([{text:'修改话术。',ignored:true},{text:added.text}]);
  expect(reopened.snapshot.groups[0].utterances[0].fixed).toBeUndefined();
  const editedAgain=fixEditedLocalUtterances(next,{...next,utterances:[{...next.utterances[0],text:'再次修改。'},added]});
  expect(editedAgain.utterances[0]).toEqual({id:old.id,text:'再次修改。',ignored:true});
  const editedVisible=fixEditedLocalUtterances(group,{...group,utterances:[{...old,text:'修改可播话术。'},added]});
  expect(editedVisible.utterances[0].fixed).toBe(true);
 });
 it('keeps a wording brief longer than the editing recommendation',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const group=file.snapshot.groups[0];
  const wording_brief='字'.repeat(401);
  const output=writeTemplateDocument(file,[{kind:'group',action:'put',id:group.id,value:{...group,wording_brief}}]);
  const reopened=parseTemplateFile(JSON.stringify(output));
  expect(reopened.groupErrors).toEqual([]);
  expect(reopened.snapshot.groups[0].wording_brief).toBe(wording_brief);
  expect(fileDeliveryDocument(reopened).groups[0]).toMatchObject({wording_brief});
 });
 it('persists legacy ignore and fixed flags and excludes ignored content from delivery',()=>{
  const file=parseTemplateFile(JSON.stringify({...input,groups:[
   {...input.groups[0],utterances:['不导出。','固定保留。']},input.groups[1],
  ]}));
  const [first,second]=file.snapshot.groups,[ignored,fixed]=first.utterances;
  const result=writeTemplateDocument(file,[
   {kind:'group',action:'put',id:first.id,value:{...first,utterances:[{...ignored,ignored:true},{...fixed,fixed:true}]}},
   {kind:'group',action:'put',id:second.id,value:{...second,ignored:true}},
  ]);
  const reopened=parseTemplateFile(JSON.stringify(result));
  expect(reopened.snapshot.groups[0].utterances).toMatchObject([{ignored:true},{fixed:true}]);
  expect(reopened.snapshot.groups[1].ignored).toBe(true);
  expect(fileDeliveryDocument(reopened).groups).toMatchObject([{name:first.name,utterances:['固定保留。']}]);
  expect(parseTemplateFile(JSON.stringify(fileDeliveryDocument(reopened))).snapshot.groups[0].utterances[0].fixed).toBe(true);
  expect(fileImportDocument(reopened,[first.id,second.id]).groups).toMatchObject([{name:first.name,utterances:['固定保留。']}]);
 });
 it('writes edited scope names even when neither name is in the database',()=>{
  const file=parseTemplateFile(JSON.stringify(input));
  const group=file.snapshot.groups[0];
  const value={...group,scope:{player_id:fileTemplateScopeId('player',' 白歌 '),lineup_note_id:fileTemplateScopeId('lineup','三分 登场')}};
  const output=writeTemplateDocument(file,[{kind:'group',action:'put',id:group.id,value}]);
  expect(output.groups[0]).toMatchObject({scope:{player:'白歌',lineup:'三分 登场'},effective_expression:'玩家.使用棋手 is "白歌" and 玩家.使用阵容 is "三分 登场"'});
  expect(parseTemplateFile(JSON.stringify(output)).groupErrors).toEqual([]);
 });
 it('round-trips both comment scopes without changing the template or including comments in database imports',()=>{
  const row={...input.groups[0],review_status:'final_reviewed',extra:'保留'};
  let file=parseTemplateFile(JSON.stringify({...input,groups:[row,input.groups[1]]}));
  const group=file.snapshot.groups[0],message={id:'one',by:'编写员',at:'2026-11-24T00:00:00Z',body:' 整组建议 '};
  file=parseTemplateFile(JSON.stringify(writeLocalComment(file,group.id,undefined,message)));
  file=parseTemplateFile(JSON.stringify(writeLocalComment(file,group.id,group.utterances[0],{...message,id:'two',body:'话术建议'})));
  expect(file.comments.get(group.id)).toMatchObject([{id:'one',body:'整组建议'},{id:'two',original_text:'买这张。'}]);
  expect(fileImportDocument(file,[group.id]).groups).toEqual([row]);
  expect(fileDeliveryDocument(file,[group.id]).groups[0]).toMatchObject({...row,file_comments:file.comments.get(group.id)});
  expect(file.document.groups[1]).toEqual(input.groups[1]);
  expect(()=>writeLocalComment(file,group.id,{...group.utterances[0],text:'旧内容'},message)).toThrow(/已有修改/);
 });
 it('moves legacy row comments with the sentence and never attaches removed comments to its replacement',()=>{
  const original={...input.groups[0],utterances:['甲','乙','丙']};
  let file=parseTemplateFile(JSON.stringify({...input,groups:[original]}));
  const group=file.snapshot.groups[0],[a,b,c]=group.utterances;
  const message={id:'one',by:'编写员',at:'2026-11-24T00:00:00Z',body:'留意'};
  file=parseTemplateFile(JSON.stringify(writeLocalComment(file,group.id,a,message)));
  file=parseTemplateFile(JSON.stringify(writeLocalComment(file,group.id,b,{...message,id:'two'})));
  const edited=writeTemplateDocument(file,[{kind:'group',action:'put',id:group.id,value:{...group,utterances:[{...b,text:'乙新版'},c]}}]);
  const reopened=parseTemplateFile(JSON.stringify(edited));
  expect(reopened.comments.get(group.id)).toMatchObject([{id:'two',utterance_id:a.id,original_text:'乙',target_text:'乙新版'}]);
  const changed={...edited,groups:[{...(edited.groups[0] as object),utterances:['丙','乙新版']}]};
  expect(parseTemplateFile(JSON.stringify(changed)).comments.get(group.id)).toBeUndefined();
 });
 it('reports invalid groups and preserves their original rows while using valid groups',()=>{
  const invalid={...input.groups[0],name:'坏组',event_name:'缺失事件'};
  const rows=[invalid,input.groups[0],null,input.groups[1],{...input.groups[0]}];
  const file=parseTemplateFile(JSON.stringify({...input,groups:rows}));
  expect(file.snapshot.groups.map(group=>group.name)).toEqual(['选中组','未选中组']);
  expect(file.groupErrors.map(error=>error.index)).toEqual([0,2,4]);
  expect(file.groupErrors[0].message).toContain('坏组');
  const second=file.snapshot.groups[1];
  expect(fileImportDocument(file,[second.id]).groups).toEqual([input.groups[1]]);
  const changed=writeTemplateDocument(file,[{kind:'group',action:'put',id:second.id,value:{...second,name:'改名'}}]);
  expect(changed.groups.map((row,index)=>index===3?input.groups[1]:row)).toEqual(rows);
  expect(changed.groups[3]).toMatchObject({name:'改名'});
  const reviewed=writeLocalReviewStatus(file,{...second,review_status:'ai_generated'});
  expect(reviewed.groups).toEqual([invalid,input.groups[0],null,{...input.groups[1],review_status:'ai_generated'},rows[4]]);
 });
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
  expect(edited).toMatchObject({review_status:null,last_modified_by:{kind:'user',username:'编辑人'}});
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
