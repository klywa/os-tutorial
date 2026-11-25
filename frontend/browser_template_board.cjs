// Run after the frontend build: node frontend/browser_template_board.cjs
// The server and all template changes are confined to a disposable fixture.
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const readline=require('node:readline');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||
 'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function main(){
 const root=path.resolve(__dirname,'..');
 const fixture=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),
  ['-u','frontend/browser_templates_fixture.py','--collaboration','--paginate'],
  {cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'},stdio:['ignore','pipe','inherit']});
 const output=readline.createInterface({input:fixture.stdout});
 let browser;
 try{
  const {port}=await Promise.race([once(output,'line').then(([line])=>JSON.parse(line)),
   once(fixture,'exit').then(([code])=>{throw Error('fixture exit '+code);})]);
  const base='http://127.0.0.1:'+port;
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||
   'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
  const page=await browser.newPage({viewport:{width:1440,height:770}});
  page.setDefaultTimeout(7000);
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('dialog',nativeDialog=>/^(确认复核|确定删除这条话术)/.test(nativeDialog.message())?nativeDialog.accept():nativeDialog.dismiss());
  const button=(name,scope=page)=>scope.getByRole('button',{name,exact:typeof name==='string'});
  const dialog=name=>page.getByRole('dialog',{name});
  const close=scope=>button(/^关闭/,scope).first().click();
  const row=name=>button('选择'+name);
  const detail=name=>button('查看'+name+'详情');
  const selection=page.locator('[data-template-board-pick][aria-pressed="true"]');
  const source=page.getByRole('group',{name:'内容来源'});
  const display=page.getByRole('group',{name:'模板显示方式'});
  const chooseSource=label=>button(label,source).click();

  async function login(username,role){
   const signedIn=await page.request.post(base+'/api/auth/login',{headers:{Origin:base},data:{username,password:'fixture'}});
   assert(signedIn.ok(),await signedIn.text());
   if(role){
    const switched=await page.request.post(base+'/api/auth/role',{headers:{Origin:base},data:{role}});
    assert(switched.ok(),await switched.text());
   }
   await page.goto(base+'/admin');
   await button('模板库').click();
   await chooseSource('数据库');
   const compact=button('看板',display);
   if(await compact.count()&&await compact.getAttribute('aria-pressed')!=='true')await compact.click();
   await row('穿戴末世').waitFor();
  }

  await login('reviewer');
  assert.equal(await page.locator('.template-group').count(),0);
  const mode=page.getByRole('navigation',{name:'主要导航'}).getByLabel('模式',{exact:true});
  await mode.selectOption('万象速决');
  await row('选择末世').waitFor();
  assert.equal(await row('穿戴末世').count(),0);
  await mode.selectOption('万象大赛');
  await row('穿戴末世').waitFor();
  assert.equal(await row('选择末世').count(),0);
  await mode.selectOption('');
  await button('按实体').click();
  await page.getByLabel('查找实体').fill('末世');
  const entities=page.getByRole('complementary',{name:'实体列表'});
  await button(/末世.*装备/,entities).click();
  await row('穿戴末世').waitFor();
  assert.equal(await row('选择末世').count(),0);
  assert.equal(await row('穿戴末世').getAttribute('aria-description'),'穿上的装备');
  await button('卡片').click();
  await page.getByRole('article',{name:'穿戴末世',exact:true}).waitFor();
  assert.equal(await row('穿戴末世').count(),0);
  assert.equal(await page.getByRole('article',{name:'选择末世',exact:true}).count(),0);
  await button('看板',display).click();
  await button(/末世.*天赋/,entities).click();
  await row('选择末世').waitFor();
  assert.equal(await row('穿戴末世').count(),0);
  assert.equal(await row('选择末世').getAttribute('aria-description'),'选中的天赋');
  await row('选择末世').press('Space');
  assert.equal(await row('选择末世').getAttribute('aria-pressed'),'true');
  await detail('选择末世').click();
  const talent=dialog('选择末世 · 模板详情');
  await talent.waitFor();
  assert.equal(await talent.getByRole('article',{name:'选择末世'}).count(),1);
  await close(talent);
  await button(/^清除选择/).click();
  await button('按事件').click();
  await button('卡片').click();
  const cards=page.locator('.template-group-list .template-group');
  const top=await cards.nth(0).boundingBox(),next=await cards.nth(1).boundingBox();
  assert(top&&next&&next.y>=top.y+top.height,'expanded cards must stack vertically');
  const controls=await page.getByRole('group',{name:'模板分类方式'}).boundingBox();
  const sidebar=await page.locator('.template-events:visible').first().boundingBox();
  assert(controls&&sidebar&&controls.y<sidebar.y,'browse controls belong above the workspace');
  await button('看板',display).click();
  const resultActions=page.getByRole('group',{name:'模板结果操作'});
  await button('导出当前筛选',resultActions).waitFor();
  assert.equal(await button('导出当前筛选',page.locator('.template-toolbar')).count(),0);
  assert.equal(await button('批量添加标签',resultActions).count(),0);
  await row('穿戴末世').click();
  await page.getByLabel('搜索模板').fill('穿戴末世');
  await row('选择末世').waitFor({state:'hidden'});
  const sharedExport=dialog('导出到文件');
  await button('导出当前筛选',resultActions).click();
  assert.equal(await sharedExport.getByLabel('导出范围').inputValue(),'selected');
  await button('合并到已有文件',sharedExport).waitFor();
  await button('取消',sharedExport).click();
  await button('导出到文件',page.locator('.template-toolbar')).click();
  assert.equal(await sharedExport.getByLabel('导出范围').inputValue(),'selected');
  await button('取消',sharedExport).click();
  await button(/^清除选择/,resultActions).click();
  await button('导出当前筛选',resultActions).click();
  assert.equal(await sharedExport.getByLabel('导出范围').inputValue(),'filtered');
  await button('取消',sharedExport).click();
  await page.getByLabel('搜索模板').fill('');

  const picks=page.locator('[data-template-board-pick]');
  const first=await picks.nth(0).boundingBox(),third=await picks.nth(2).boundingBox();
  assert(first&&third);
  const drag=async(endY)=>{
   const x=first.x+25;
   await page.mouse.move(x,first.y+first.height/2);
   await page.mouse.down();
   await page.mouse.move(x,endY,{steps:8});
  };
  await drag(third.y+third.height/2);
  await page.mouse.up();
  assert.equal(await selection.count(),3);
  await drag(third.y+third.height/2);
  await page.mouse.up();
  assert.equal(await selection.count(),0);
  await picks.nth(0).press('ArrowDown');
  assert(await picks.nth(1).evaluate(node=>node===document.activeElement));
  await picks.nth(1).press('Shift+ArrowDown');
  assert.equal(await selection.count(),2);
  await button(/^清除选择/).click();
  const scroll=page.locator('.template-group-list').first();
  const bounds=await scroll.boundingBox();
  assert(bounds,'board has a visible scroll container');
  await drag(bounds.y+bounds.height-6);
  await page.waitForFunction(()=>document.querySelector('.template-group-list').scrollTop>25);
  await page.mouse.up();
  assert((await selection.count())>3);
  await button(/^清除选择/).click();

  await login('alice');
  await detail('穿戴末世').click();
  const editing=dialog('穿戴末世 · 模板详情');
  await editing.waitFor();
  const writerStatus=editing.getByRole('group',{name:'审核状态 · 穿戴末世'});
  assert.equal(await writerStatus.getByRole('button').count(),3);
  assert(await button('复核完成',writerStatus).isDisabled());
  const [statusProposal]=await Promise.all([
   page.waitForResponse(response=>response.url().includes('/api/templates/groups/equip/review')),
   button('初核完成',writerStatus).click(),
  ]);
  assert(statusProposal.ok(),await statusProposal.text());
  assert.equal((await statusProposal.json()).proposal.source,'review-status');
  await button('显示原数据',editing).waitFor();
  await button('显示原数据',editing).click();
  await button('编辑模板穿戴末世',editing).waitFor();
  await close(editing);
  await row('穿戴末世').click();
  await button('批量添加标签',resultActions).click();
  const writerBatch=dialog('批量添加标签');
  await writerBatch.getByLabel('要添加的标签').fill('提案验收');
  const changePath=response=>new URL(response.url()).pathname.endsWith('/api/templates/changes')&&response.request().method()==='POST';
  const [writerResponse]=await Promise.all([page.waitForResponse(changePath),button('提交提案',writerBatch).click()]);
  assert(writerResponse.ok(),await writerResponse.text());
  assert.deepEqual((await writerResponse.json()).proposal.changes.map(change=>change.value.tags),[['提案验收']]);
  const writerSnapshot=await (await page.request.get(base+'/api/templates')).json();
  const originalEquip=writerSnapshot.groups.find(group=>group.id==='equip');
  async function submitProposal(changes){
   const result=await page.request.post(base+'/api/templates/changes',{headers:{Origin:base},data:{revision:writerSnapshot.revision,changes}});
   assert(result.ok(),await result.text());
   return (await result.json()).proposal;
  }
  const removedUtterance=originalEquip.utterances[0];
  const addedUtterance={id:'proposal-line',text:'待审话术新内容。'};
  const draftEquip={...originalEquip,name:'待审卡片名称',utterances:[addedUtterance]};
  const draftNew={...originalEquip,id:'new-proposal-card',name:'验收新组'};
  const newest=await submitProposal([
   {kind:'group',action:'put',id:draftEquip.id,value:draftEquip},
   {kind:'group',action:'put',id:draftNew.id,value:draftNew},
  ]);
  const withdrawn=await submitProposal([{kind:'group',action:'put',id:originalEquip.id,value:{...originalEquip,priority:97}}]);
  const withdrew=await page.request.post(base+'/api/templates/proposals/'+withdrawn.id+'/withdraw',{headers:{Origin:base},data:{proposal_revision:withdrawn.proposal_revision}});
  assert(withdrew.ok(),await withdrew.text());
  await button('刷新模板库').click();
  await button('我的提案').click();
  const proposalDialog=dialog('我的模板提案');
  const withdrawnPanel=proposalDialog.locator('.template-withdrawn-proposals');
  await withdrawnPanel.getByText('已撤回（1）',{exact:true}).waitFor();
  assert.equal(await withdrawnPanel.getAttribute('open'),null);
  const times=await proposalDialog.locator('.template-proposals > .template-proposal > header time').evaluateAll(elements=>elements.map(element=>element.dateTime));
  assert.deepEqual(times,[...times].sort().reverse());
  await button('定位待审卡片名称',proposalDialog).click();
  const boardPreview=dialog('穿戴末世 · 模板详情');
  const proposedCard=boardPreview.locator('[data-proposal-card]');
  await proposedCard.locator('h2[data-proposal-change]').getByText('待审卡片名称').waitFor();
  await proposedCard.locator('[data-proposal-change]').getByText(addedUtterance.text,{exact:true}).waitFor();
  await proposedCard.locator('s').getByText(removedUtterance.text,{exact:true}).waitFor();
  assert.equal(await button(/^导出/,proposedCard).count(),0);
  assert.equal(await boardPreview.getByLabel('预览提案').inputValue(),newest.id);
  await boardPreview.getByLabel('预览提案').selectOption((await writerResponse.json()).proposal.id);
  await proposedCard.locator('[data-proposal-change]').getByText('提案验收',{exact:true}).waitFor();
  assert.equal(await proposedCard.getByText(addedUtterance.text,{exact:true}).count(),0);
  await button('显示原数据',boardPreview).click();
  await boardPreview.getByRole('heading',{name:'穿戴末世',exact:true}).waitFor();
  await close(boardPreview);
  await button('卡片',display).click();
  await button('我的提案').click();
  await button('定位待审卡片名称',proposalDialog).click();
  await page.locator('.template-group-list [data-feedback-group="equip"]').filter({hasText:'待审卡片名称'}).waitFor();
  assert(await page.locator('.template-group-list [data-feedback-group="equip"]').evaluate(node=>node===document.activeElement));
  await page.getByLabel('搜索模板').fill('不存在的定位验收筛选');
  await button('我的提案').click();
  await button('定位待审卡片名称',proposalDialog).click();
  await boardPreview.getByRole('heading',{name:'待审卡片名称'}).waitFor();
  await close(boardPreview);
  assert.equal(await page.getByLabel('搜索模板').inputValue(),'不存在的定位验收筛选');
  await page.getByLabel('搜索模板').fill('');
  await button('我的提案').click();
  await button('定位验收新组',proposalDialog).click();
  const temporary=dialog('验收新组 · 临时提案卡');
  await temporary.getByText('提案 · 新模板组',{exact:true}).waitFor();
  assert.equal(await button('显示原数据',temporary).count(),0);
  await close(temporary);
  const exportedFormal=await (await page.request.get(base+'/api/templates/export?authoring=1&group_ids=equip')).json();
  assert.equal(exportedFormal.groups[0].name,'穿戴末世');
  // Close the extra fixture proposal before the formal edit and rollback checks.
  const withdrawnNewest=await page.request.post(base+'/api/templates/proposals/'+newest.id+'/withdraw',{headers:{Origin:base},data:{proposal_revision:newest.proposal_revision}});
  assert(withdrawnNewest.ok(),await withdrawnNewest.text());
  await login('reader');
  await detail('穿戴末世').click();
  const reading=dialog('穿戴末世 · 模板详情');
  await reading.waitFor();
  assert.equal(await button('显示原数据',reading).count(),0);
  assert(await button('初核完成',reading.getByRole('group',{name:'审核状态 · 穿戴末世'})).isDisabled());
  assert.equal(await button('编辑模板穿戴末世',reading).count(),0);
  assert.equal(await button(/^编辑标签|^编辑批次/,reading).count(),0);

  await login('reviewer','quality');
  const downloaded=await page.request.get(base+'/api/templates/export?authoring=1&group_ids=forge,equip,talent');
  assert(downloaded.ok(),await downloaded.text());
  const portable=await downloaded.json();
  const [one,two,three]=portable.groups;
  portable.groups=[
   {...one,name:'文件甲',batch:['已整理','待合并'],review_status:'initial_reviewed',last_modified_by:{kind:'user',username:'alice'}},
   {...two,name:'文件乙',batch:['已整理'],review_status:'ai_generated',last_modified_by:{kind:'ai'}},
   {...three,name:'文件丙',batch:['另一批'],review_status:'ai_generated',last_modified_by:{kind:'ai'}},
  ];
  await page.evaluate(doc=>{
   let raw=JSON.stringify(doc);
   let exported='';
   let fileWriteGate;
   window.holdBoardWrite=()=>{fileWriteGate=new Promise(resolve=>{window.releaseBoardWrite=resolve;});};
   window.readBoardFixtureFile=()=>JSON.parse(raw);
   window.readBoardExportFile=()=>JSON.parse(exported);
   const handle={
    name:'浏览器验收模板.json',
    getFile:async()=>new File([raw],'浏览器验收模板.json',{type:'application/json'}),
    createWritable:async()=>{
     let next;
     return {write:async value=>{next=value;},close:async()=>{const gate=fileWriteGate;fileWriteGate=null;if(gate)await gate;raw=next;},abort:async()=>{}};
    },
   };
   Object.defineProperty(window,'showOpenFilePicker',{configurable:true,value:async()=>[{
    ...handle,isSameEntry:async other=>other.name===handle.name,
   }]});
   Object.defineProperty(window,'showSaveFilePicker',{configurable:true,value:async()=>({
    name:'新导出模板.json',getFile:async()=>new File([exported],'新导出模板.json'),
    createWritable:async()=>{
     let next;
     return {write:async value=>{next=value;},close:async()=>{exported=next;},abort:async()=>{}};
    },
   })});
  },portable);
  await chooseSource('文件');
  await button('打开模板文件').click();
  await button('看板',display).click();
  await row('文件甲').waitFor();
  await mode.selectOption('万象速决');
  await row(portable.groups.find(group=>group.id==='talent').name).waitFor();
  assert.equal(await row(portable.groups.find(group=>group.id==='equip').name).count(),0);
  await mode.selectOption('');
  assert.equal(await row('穿戴末世').count(),0);
  await button(/^筛选/).click();
  await page.getByRole('checkbox',{name:'已整理',exact:true}).check();
  await page.getByRole('checkbox',{name:'待合并',exact:true}).check();
  assert.equal(await page.locator('[data-template-board-row]').count(),1);
  await page.getByLabel('审核状态').selectOption('ai_generated');
  assert.equal(await page.locator('[data-template-board-row]').count(),0);
  await page.getByLabel('审核状态').selectOption('initial_reviewed');
  await page.getByLabel('最后修改人').selectOption('ai');
  assert.equal(await page.locator('[data-template-board-row]').count(),0);
  await page.getByLabel('最后修改人').selectOption('user:alice');
  assert.equal(await page.locator('[data-template-board-row]').count(),1);
  assert.equal(await row('文件甲').count(),1);
  await button('清空筛选').click();
  await page.keyboard.press('Escape');
  await row('文件甲').click();
  await row('文件乙').click();
  await button('批量添加批次',resultActions).click();
  const fileBatch=dialog('批量添加批次');
  await fileBatch.getByLabel('要添加的批次').fill('验收共同批次，验收共同批次');
  await button('确认添加',fileBatch).click();
  await fileBatch.waitFor({state:'hidden'});
  const fileBatches=await page.evaluate(()=>window.readBoardFixtureFile().groups.map(group=>[group.name,group.batch??[]]));
  for(const [name,batches] of fileBatches)assert.equal(batches.filter(value=>value==='验收共同批次').length,name==='文件甲'||name==='文件乙'?1:0);
  await button(/^导入所选到数据库/).click();
  const importing=dialog('导入所选模板到数据库');
  await importing.waitFor();
  assert.deepEqual(await importing.getByRole('listitem').allTextContents(),['文件甲','文件乙']);
  const [previewResponse]=await Promise.all([
   page.waitForResponse(response=>response.url().includes('/api/templates/import/preview')),
   button('检查并预览',importing).click(),
  ]);
  assert(previewResponse.ok(),await previewResponse.text());
  const previewBody=await previewResponse.json();
  assert.deepEqual(previewBody.errors,[]);
  assert.deepEqual(previewBody.changes.filter(change=>change.kind==='group').map(change=>change.value.name).sort(),['文件乙','文件甲']);
  const [submitted]=await Promise.all([
   page.waitForResponse(response=>response.url().includes('/api/templates/import/commit')),
   button('确认提交导入提案',importing).click(),
  ]);
  assert(submitted.ok(),await submitted.text());
  assert.equal((await submitted.json()).proposal.author_role,'quality');
  await detail('文件甲').click();
  const fileDetail=dialog('文件甲 · 模板详情');
  const fileStatus=fileDetail.getByRole('group',{name:'审核状态 · 文件甲'});
  await page.evaluate(()=>window.holdBoardWrite());
  await button('复核完成',fileStatus).click();
  try{
   assert.equal(await button('复核完成',fileStatus).getAttribute('aria-pressed'),'true');
   await button('复核完成',fileStatus).click();
   assert.equal(await fileStatus.getByRole('button',{pressed:true}).count(),0);
  }finally{await page.evaluate(()=>window.releaseBoardWrite());}
  await page.waitForFunction(()=>window.readBoardFixtureFile().groups.find(group=>group.name==='文件甲').review_status===null);
  await button('复核完成',fileStatus).click();
  await page.waitForFunction(()=>window.readBoardFixtureFile().groups.find(group=>group.name==='文件甲').review_status==='final_reviewed');
  const saved=await page.evaluate(()=>window.readBoardFixtureFile());
  assert.equal(saved.groups.find(group=>group.name==='文件甲').review_status,'final_reviewed');
  assert.equal(saved.groups.find(group=>group.name==='文件甲').reviewed_by,'reviewer');
  await button(/^编辑批次/,fileDetail).click();
  await button('移除批次 待合并',fileDetail).click();
  const batchInput=fileDetail.getByRole('textbox',{name:'新增批次',exact:true});
  await batchInput.fill('文件验收');
  await batchInput.press('Tab');
  await batchInput.waitFor({state:'hidden'});
  await page.waitForFunction(()=>window.readBoardFixtureFile().groups.find(group=>group.name==='文件甲').batch.includes('文件验收'));
  assert.deepEqual(await page.evaluate(()=>window.readBoardFixtureFile().groups.find(group=>group.name==='文件甲').batch),['已整理','验收共同批次','文件验收']);
  await button('复核完成',fileStatus).click();
  await page.waitForFunction(()=>window.readBoardFixtureFile().groups.find(group=>group.name==='文件甲').review_status==='final_reviewed');
  await close(fileDetail);
  const exportToolbar=page.locator('.template-toolbar');
  await button('导出到文件',exportToolbar).click();
  const fileExport=dialog('导出到文件');
  assert.equal(await fileExport.getByLabel('导出范围').inputValue(),'selected');
  await button('新建文件',fileExport).click();
  await button('确认写入',fileExport).click();
  await fileExport.waitFor({state:'hidden'});
  const exported=await page.evaluate(()=>window.readBoardExportFile());
  assert.deepEqual(exported.groups.map(group=>group.name),['文件甲','文件乙']);
  assert.equal(exported.groups[0].review_status,'final_reviewed');
  await page.getByLabel('搜索模板').fill('文件甲');
  await button('导出到文件',exportToolbar).click();
  await fileExport.getByLabel('导出范围').selectOption('filtered');
  await button('合并到已有文件',fileExport).click();
  await fileExport.getByText('目标文件没有变化。',{exact:true}).waitFor();
  assert(await button('确认写入',fileExport).isDisabled());
  await button('取消',fileExport).click();
  await chooseSource('数据库');
  await row('穿戴末世').waitFor();
  assert.equal(await row('文件甲').count(),0);
  await detail('穿戴末世').click();
  const databaseDetail=dialog('穿戴末世 · 模板详情');
  await button('显示原数据',databaseDetail).click();
  await button('导出到文件',databaseDetail).click();
  await button('合并到已有文件',fileExport).click();
  await fileExport.getByText(/覆盖 1 组/).waitFor();
  await button('确认写入',fileExport).click();
  await fileExport.waitFor({state:'hidden'});
  const merged=await page.evaluate(()=>window.readBoardFixtureFile());
  assert.equal(merged.groups.length,3);
  assert.equal(merged.groups.find(group=>group.id==='equip').name,'穿戴末世');
  await close(dialog('穿戴末世 · 模板详情'));
  await chooseSource('文件');
  await page.getByLabel('搜索模板').fill('');
  await row('穿戴末世').waitFor();

  await login('reviewer');
  const state=await (await page.request.get(base+'/api/templates')).json();
  const original=state.groups.find(group=>group.id==='equip');
  const revised={...original,name:'穿戴末世·历史验收'};
  const changed=await page.request.post(base+'/api/templates/changes',{headers:{Origin:base},data:{
   revision:state.revision,changes:[{kind:'group',action:'put',id:revised.id,value:revised}],
  }});
  assert(changed.ok(),await changed.text());
  assert.equal((await changed.json()).groups.find(group=>group.id==='equip').review_status,null);
  await button('刷新模板库').click();
  await detail(revised.name).click();
  const revisedDetail=dialog(revised.name+' · 模板详情');
  await button('显示原数据',revisedDetail).click();
  const recordButton=button('版本记录',revisedDetail);
  await recordButton.hover();
  await dialog(revised.name+' · 模板详情').getByRole('tooltip').filter({hasText:'最近操作'}).waitFor();
  await recordButton.click();
  const history=page.getByRole('dialog',{name:/修订历史/});
  const revisions=history.getByLabel('修订版本');
  await revisions.waitFor();
  await revisions.selectOption({index:1});
  await button('预览回退',history).click();
  await button('确认回退',history).click();
  await history.waitFor({state:'hidden'});
  const restored=(await (await page.request.get(base+'/api/templates')).json()).groups.find(group=>group.id==='equip');
  assert.equal(restored.name,original.name);
  assert.equal(restored.last_modified_by.username,'reviewer');
  assert.equal(restored.review_status,null);
  const currentStatus=dialog(original.name+' · 模板详情').getByRole('group',{name:'审核状态 · '+original.name});
  await button('初核完成',currentStatus).click();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('.template-review-statuses')).every(group=>group.getAttribute('aria-busy')!=='true'));
  assert.equal((await (await page.request.get(base+'/api/templates')).json()).groups.find(group=>group.id==='equip').review_status,'initial_reviewed');
  const reviewRoute=url=>url.pathname.endsWith('/api/templates/groups/equip/review');
  await page.route(reviewRoute,route=>route.fulfill({status:503,json:{error:'测试保存失败'}}),{times:1});
  await button('复核完成',currentStatus).click();
  await page.getByRole('alert').filter({hasText:'测试保存失败'}).last().waitFor();
  assert.equal(await button('初核完成',currentStatus).getAttribute('aria-pressed'),'true');
  let releaseReview,markStarted;
  const heldReview=new Promise(resolve=>{releaseReview=resolve;});
  const started=new Promise(resolve=>{markStarted=resolve;});
  await page.route(reviewRoute,async route=>{markStarted();await heldReview;await route.continue();},{times:1});
  const replacement=page.waitForResponse(response=>reviewRoute(new URL(response.url()))&&response.request().postDataJSON().status==='ai_generated');
  await button('复核完成',currentStatus).click();
  await started;
  try{
   assert.equal(await button('复核完成',currentStatus).getAttribute('aria-pressed'),'true');
   await button('复核完成',currentStatus).click();
   assert.equal(await currentStatus.getByRole('button',{pressed:true}).count(),0);
   await button('AI生成',currentStatus).click();
   assert.equal(await button('AI生成',currentStatus).getAttribute('aria-pressed'),'true');
  }finally{releaseReview();}
  assert((await replacement).ok());
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('.template-review-statuses')).every(group=>group.getAttribute('aria-busy')!=='true'));
  for(const [label,value] of [['复核完成','final_reviewed'],['复核完成',null],['AI生成','ai_generated']]){
   const response=page.waitForResponse(response=>response.url().includes('/api/templates/groups/equip/review'));
   await button(label,currentStatus).click();
   const result=await response;
   assert(result.ok(),await result.text());
   const group=(await result.json()).groups.find(group=>group.id==='equip');
   assert.equal(group.review_status,value);
   assert.deepEqual(group.last_modified_by,restored.last_modified_by);
   assert.equal(group.reviewed_by,value==='final_reviewed'?'reviewer':undefined);
   assert.equal(await page.getByText('审核状态已更新。',{exact:true}).count(),0);
   if(value===null)await currentStatus.getByRole('button',{pressed:true}).waitFor({state:'hidden'});
  }
  const editedCard=dialog(original.name+' · 模板详情');
  const conditions=editedCard.getByRole('region',{name:'卡牌与条件'});
  const editCondition=button('编辑模板'+original.name,conditions);
  const copyCondition=button('复制完整条件',conditions);
  const [editBox,copyBox]=await Promise.all([editCondition.boundingBox(),copyCondition.boundingBox()]);
  assert(editBox&&copyBox&&editBox.x<copyBox.x&&editBox.y===copyBox.y&&editBox.height===copyBox.height);
  const conditionTrigger=button('就地编辑完整触发条件',conditions);
  await conditionTrigger.click();
  const conditionInput=conditions.getByRole('textbox',{name:'正式条件表达式'});
  const previousExpression=await conditionInput.inputValue();
  await conditionInput.fill('玩家.等级 >= ');
  await button('保存条件',conditions).click();
  await conditions.locator('.template-expression-editor [role="alert"]').waitFor();
  assert.equal(await conditionInput.inputValue(),'玩家.等级 >= ');
  await conditionInput.press('Escape');
  await conditionTrigger.waitFor();
  assert.equal(await dialog('编辑模板组').count(),0);
  const savedExpression=previousExpression+' and 玩家.等级 >= 1';
  const writeCondition=async value=>{
   await conditionTrigger.click();
   await conditionInput.fill(value);
   await button('保存条件',conditions).click();
   await conditionTrigger.waitFor();
   const result=await (await page.request.get(base+'/api/templates')).json();
   const updated=result.groups.find(row=>row.id===original.id);
   assert.equal(updated.expression,value);
   assert.deepEqual(updated.scope,original.scope);
  };
  await writeCondition(savedExpression);
  await writeCondition(previousExpression);
  const speechRow=editedCard.locator('li[data-feedback-utterance]').first();
  await button(/^编辑话术/,speechRow).click();
  const speechInput=speechRow.getByRole('textbox',{name:'修改话术内容'});
  const beforeSlot=await speechInput.inputValue();
  await speechInput.fill('对手主力是');
  await button('对局.当前对手.主C',speechRow).click();
  assert.equal(await speechInput.inputValue(),'对手主力是{对局.当前对手.主C}');
  const writeSpeech=async value=>{
   await speechInput.fill(value);
   await button('保存话术',speechRow).click();
   await speechInput.waitFor({state:'hidden'});
   const result=await (await page.request.get(base+'/api/templates')).json();
   assert(result.groups.find(row=>row.id===original.id).utterances.some(row=>row.text===value));
  };
  await writeSpeech('对手主力是{对局.当前对手.主C}。');
  await button(/^编辑话术/,speechRow).click();
  await writeSpeech(beforeSlot);
  await editCondition.click();
  await button('取消',dialog('编辑模板组')).click();
  await editedCard.waitFor();
  await button(/^编辑标签/,editedCard).click();
  const tagInput=editedCard.getByRole('textbox',{name:'新增标签',exact:true});
  await tagInput.fill('取消验收');
  await tagInput.press('Escape');
  await tagInput.waitFor({state:'hidden'});
  assert.equal(await editedCard.getByText('取消验收',{exact:true}).count(),0);
  await button(/^编辑标签/,editedCard).click();
  await tagInput.fill('数据库验收');
  await tagInput.press('Enter');
  const [metadataResponse]=await Promise.all([
   page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/templates/changes')&&response.request().method()==='POST'),
   button(/^编辑批次/,editedCard).click(),
  ]);
  assert(metadataResponse.ok(),await metadataResponse.text());
  const updatedGroup=(await metadataResponse.json()).groups.find(group=>group.id==='equip');
  assert(updatedGroup.tags.includes('数据库验收'));
  assert(!updatedGroup.tags.includes('取消验收'));
  await editedCard.getByRole('textbox',{name:'新增批次',exact:true}).press('Escape');
  await button(/^编辑标签.*数据库验收/,editedCard).waitFor();
  await close(editedCard);
  await row('穿戴末世').click();
  await row('选择末世').click();
  await button('批量添加标签',resultActions).click();
  const labelBatch=dialog('批量添加标签');
  await labelBatch.getByLabel('要添加的标签').fill('数据库验收，组批量验收');
  await labelBatch.getByRole('status').filter({hasText:'将更新 2 个模板组'}).waitFor();
  const [bulkResponse]=await Promise.all([page.waitForResponse(changePath),button('确认添加',labelBatch).click()]);
  assert(bulkResponse.ok(),await bulkResponse.text());
  assert.deepEqual(bulkResponse.request().postDataJSON().changes.map(change=>change.id).sort(),['equip','talent']);
  for(const group of (await bulkResponse.json()).groups.filter(group=>['equip','talent'].includes(group.id)))
   assert.deepEqual(group.tags.slice(-2),['数据库验收','组批量验收']);
  await labelBatch.waitFor({state:'hidden'});
  await button(/^清除选择.*2/,resultActions).waitFor();
  await login('alice');
  const approvalBase=await (await page.request.get(base+'/api/templates')).json();
  const approvalEquip=approvalBase.groups.find(group=>group.id==='equip');
  const approvalLine={id:'approval-draft-line',text:'卡片采纳验收稿。'};
  const put=value=>({kind:'group',action:'put',id:value.id,value});
  const approvalDraft={...approvalEquip,utterances:[...approvalEquip.utterances,approvalLine]};
  const approvalNew={...approvalEquip,id:'card-approval-new',name:'待采纳临时卡'};
  const submitApproval=await page.request.post(base+'/api/templates/changes',{headers:{Origin:base},data:{
   revision:approvalBase.revision,changes:[put(approvalDraft),put(approvalNew)],
  }});
  assert(submitApproval.ok(),await submitApproval.text());
  const approvalId=(await submitApproval.json()).proposal.id;
  await button('刷新模板库').click();
  await detail('穿戴末世').click();
  const approvalDetail=dialog('穿戴末世 · 模板详情');
  const approvalText=approvalDetail.locator('[data-feedback-utterance="approval-draft-line"]');
  await approvalText.getByText(approvalLine.text,{exact:true}).waitFor();
  assert.equal(await button('采纳本组',approvalDetail).count(),0);
  await button('显示原数据',approvalDetail).click();
  assert.equal(await approvalText.count(),0);
  await close(approvalDetail);
  await detail('穿戴末世').click();
  await approvalText.getByText(approvalLine.text,{exact:true}).waitFor();
  await button(/^编辑话术/,approvalText).click();
  const inlineText=approvalText.getByLabel('修改话术内容');
  await inlineText.fill('作者在卡片修改。');
  const proposalEdit=url=>url.pathname.endsWith('/api/templates/proposals/'+approvalId+'/edit');
  await page.route(proposalEdit,route=>route.fulfill({status:409,json:{error:'验收冲突，草稿保留'}}),{times:1});
  await button('保存提案',approvalText).click();
  await approvalText.getByRole('alert').filter({hasText:'验收冲突，草稿保留'}).waitFor({timeout:30000});
  assert.equal(await inlineText.inputValue(),'作者在卡片修改。');
  await button('保存提案',approvalText).click();
  await inlineText.waitFor({state:'hidden'});
  await approvalText.locator('.template-utterance-text').getByText('作者在卡片修改。',{exact:true}).waitFor();
  await button('＋ 新增话术',approvalDetail).click();
  const newDraftText=approvalDetail.getByLabel('新增话术内容');
  await newDraftText.fill('待审卡片原位新增。');
  await button('保存提案',approvalDetail).click();
  await newDraftText.waitFor({state:'hidden'});
  await approvalDetail.locator('.template-utterance-text').getByText('待审卡片原位新增。',{exact:true}).waitFor();
  await button(/^编辑标签/,approvalDetail).click();
  await approvalDetail.getByLabel('新增标签').fill('提案原位标签');
  const [metadataSaved]=await Promise.all([
   page.waitForResponse(response=>proposalEdit(new URL(response.url()))),
   approvalDetail.getByLabel('新增标签').press('Tab'),
  ]);
  assert(metadataSaved.ok(),await metadataSaved.text());
  await button(/^编辑标签.*提案原位标签/,approvalDetail).waitFor();

  function holdDraftEdit(){
   let release,started;
   const resume=new Promise(resolve=>{release=resolve;});
   const reached=new Promise(resolve=>{started=resolve;});
   return {release,reached,install:()=>page.route(proposalEdit,async route=>{started();await resume;await route.continue();},{times:1})};
  }
  const delayed=holdDraftEdit();
  await delayed.install();
  const initialClick=performance.now();
  await button(/^忽略话术/,approvalText).click();
  await delayed.reached;
  const optimistic=button(/^取消忽略话术/,approvalText);
  await optimistic.waitFor();
  const feedbackMs=Math.round(performance.now()-initialClick);
  const conditionArea=approvalDetail.getByRole('region',{name:'卡牌与条件'});
  const groupEditDialog=dialog('修改模板提案');
  const temporaryLineId=await approvalDetail.locator('li').filter({hasText:'待审卡片原位新增。'}).getAttribute('data-feedback-utterance');
  const temporaryLine=approvalDetail.locator('[data-feedback-utterance="'+temporaryLineId+'"]');
  const replay=page.waitForResponse(response=>proposalEdit(new URL(response.url()))&&
   response.request().postDataJSON().group_editor?.ignore?.value===false,{timeout:45000});
  void replay.catch(()=>{});
  try{
   assert.equal(await optimistic.getAttribute('aria-busy'),'true');
   await optimistic.click();
   assert(await button('看板',display).isEnabled());
   await button(/^编辑话术/,temporaryLine).click();
   await temporaryLine.getByLabel('修改话术内容').fill('待审卡片并行编辑。');
   await close(approvalDetail);
   await detail('穿戴末世').click();
   assert.equal(await temporaryLine.getByLabel('修改话术内容').inputValue(),'待审卡片并行编辑。');
   await button('保存提案',temporaryLine).click();
   assert(await button(/^编辑话术/,approvalText).isEnabled());
   await button('编辑模板穿戴末世',conditionArea).click();
   await groupEditDialog.getByLabel('优先级').fill('37');
   await button('保存提案修改',groupEditDialog).click();
  }finally{delayed.release();}
  const replayResponse=await replay;
  assert(replayResponse.ok(),await replayResponse.text());
  await groupEditDialog.waitFor({state:'hidden'});
  const editedLine=approvalDetail.locator('li').filter({hasText:'待审卡片并行编辑。'});
  await editedLine.locator('.template-utterance-text').waitFor();
  const saveTiming=replayResponse.request().timing();
  console.log('忽略按钮反馈 '+feedbackMs+' ms（含浏览器点击），未延迟的取消忽略 HTTP '+Math.round(saveTiming.responseEnd-saveTiming.requestStart)+' ms。');
  assert.equal(await button(/^忽略话术/,approvalText).getAttribute('aria-busy'),null);
  await approvalDetail.getByText('优先级 37',{exact:true}).waitFor();
  await button('＋ 新增话术',approvalDetail).click();
  await newDraftText.fill('后台删除验收话术。');
  await button('保存提案',approvalDetail).click();
  const disposable=approvalDetail.locator('li').filter({hasText:'后台删除验收话术。'});
  await disposable.locator('.template-utterance-text').waitFor();
  const deleting=holdDraftEdit();
  await deleting.install();
  await button(/^删除话术/,disposable).click();
  await deleting.reached;
  try{
   await button(/^编辑话术/,approvalText).click();
   assert(await inlineText.isVisible());
   await button('取消',approvalText).click();
   assert(await button('编辑模板穿戴末世',conditionArea).isEnabled());
  }finally{deleting.release();}
  await disposable.waitFor({state:'hidden'});

  await login('reviewer');
  await detail('穿戴末世').click();
  const stagedLine=approvalDetail.locator('li').filter({hasText:'待审卡片并行编辑。'});
  const fixing=holdDraftEdit();
  await fixing.install();
  await button(/^固定话术/,stagedLine).click();
  await fixing.reached;
  await stagedLine.getByText('已固定',{exact:true}).waitFor();
  assert(await button(/^编辑话术/,stagedLine).isDisabled());
  try{
   assert.equal(await button('采纳本组',approvalDetail).count(),1);
   assert(await button(/^编辑话术/,approvalText).isEnabled());
   await button(/^取消固定话术/,stagedLine).click();
  }finally{fixing.release();}
  await stagedLine.getByText('已固定',{exact:true}).waitFor({state:'hidden'});
  await button(/^编辑话术/,approvalText).click();
  await inlineText.fill('管理员修改并采纳。');
  await button('保存并采纳本组',approvalText).click();
  await inlineText.waitFor({state:'hidden'});
  await approvalText.locator('.template-utterance-text').getByText('管理员修改并采纳。',{exact:true}).waitFor();
  const allProposals=async()=>await (await page.request.get(base+'/api/templates/proposals')).json();
  const remaining=(await allProposals()).find(item=>item.id===approvalId);
  assert.equal(remaining.status,'pending');
  assert.deepEqual(remaining.changes.map(change=>change.id),[approvalNew.id]);
  const formalAfter=await (await page.request.get(base+'/api/templates')).json();
  assert(formalAfter.groups.find(group=>group.id==='equip').utterances.some(row=>row.text==='管理员修改并采纳。'));
  await close(approvalDetail);
  await button('提案审核').click();
  await button('定位待采纳临时卡',dialog('模板提案审核')).click();
  const approvalTemporary=dialog('待采纳临时卡 · 临时提案卡');
  await button('编辑模板待采纳临时卡',approvalTemporary).click();
  const groupEditor=dialog('修改模板提案');
  await groupEditor.getByLabel('模板组名称').fill('正式验收新卡');
  await button('保存提案',groupEditor).click();
  const editedTemporary=dialog('正式验收新卡 · 临时提案卡');
  let releaseFailure;
  const failEdit=new Promise(resolve=>{releaseFailure=resolve;});
  await page.route(proposalEdit,async route=>{await failEdit;await route.fulfill({status:503,json:{error:'验收保存失败'}});},{times:1});
  const flagRow=editedTemporary.locator('[data-feedback-utterance]').first();
  await button(/^忽略话术/,flagRow).click();
  let approveCalls=0;
  const trackApproval=request=>{if(new URL(request.url()).pathname.endsWith('/api/templates/proposals/'+approvalId+'/approve'))approveCalls++;};
  page.on('request',trackApproval);
  try{
   await button('采纳本组',editedTemporary).click();
   await button('等待保存…',editedTemporary).waitFor();
  }finally{releaseFailure();}
  await editedTemporary.getByText('采纳前有一项修改保存失败，请核对待审稿后重新采纳。',{exact:true}).waitFor();
  assert.equal(approveCalls,0);
  page.off('request',trackApproval);
  await button(/^忽略话术/,flagRow).waitFor();
  await button('＋ 新增话术',editedTemporary).click();
  await editedTemporary.getByLabel('新增话术内容').fill('采纳后仍需确认的草稿。');
  await button('采纳本组',editedTemporary).click();
  const acceptedDetail=dialog('正式验收新卡 · 模板详情');
  await acceptedDetail.waitFor();
  assert.equal(await acceptedDetail.getByLabel('新增话术内容').inputValue(),'采纳后仍需确认的草稿。');
  assert.equal((await allProposals()).find(item=>item.id===approvalId).status,'approved');
  assert.deepEqual(errors,[]);
  console.log('通过看板、提案预览和定位、原数据切换、文件导入导出、复核、数据库回退及原位编辑。');
 }finally{
  if(browser)await browser.close();
  output.close();
  fixture.kill();
 }
}

main().catch(error=>{console.error(error);process.exitCode=1;});
