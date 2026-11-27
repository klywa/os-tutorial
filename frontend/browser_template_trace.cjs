// Run after npm run build. Optionally pass the path to a generated main library.
// TRACE_GROUP_ID selects one group. TRACE_GROUP_LIMIT limits a large library.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createHash}=require('node:crypto');
const {once}=require('node:events');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const labels={identify:'知识点列表',enrich:'补充知识',events:'事件框架',conditions:'条件',phrases:'话术生成'};

function sample(input){
 if(input)return [input,input.replace(/\.json$/i,'-detail.json')].map(file=>({name:path.basename(file),raw:fs.readFileSync(file,'utf8')}));
 const name='模板验收样本.json';
 const library=JSON.parse(fs.readFileSync(path.join(root,'docs/examples/speech-template-library-minimal.json'),'utf8'));
 const group=library.groups[0];
 library.events=[{name:group.event_name,category:'解释类',signature:group.event_name+'()'}];
 group.id='test_group';
 group.syntax_version='0.4';
 group.extra_key='';
 group.utterances=Array.from({length:6},(_,i)=>({id:`sentence_${i}`,text:`刷新后检查第 ${i+1} 个选项。`}));
 const raw=JSON.stringify(library),writing={limited:'只讨论当前商店',not_limited:'英雄类型不限',expected:'检查刷新结果',wording:'用短句提醒'};
 const writingCondition={...writing,id:'condition',event_id:'event',expression:'商店刷新',reason:'已有资源'};
 const details={schema_version:2,run_id:'browser-test',library_name:name,library_sha256:createHash('sha256').update(raw).digest('hex'),
  knowledge_lists:{list:[{original:'刷新后检查商店',type:'操作',prerequisite:'选择刷新',related_knowledge:'刷新消耗资源'},
   {original:'找到英雄后考虑购买',type:'操作',prerequisite:'商店出现该英雄',related_knowledge:'购买消耗金币'}]},
  points:{point:{knowledge:'刷新后可看新的商店英雄。',events:[{id:'event',event:'刷新商店',expected:'查看新英雄'},
   {id:'other_event',event:'购买英雄',expected:'补充棋子'}],conditions:[writingCondition,{...writingCondition,id:'other_condition',expression:'刷新后出现可用英雄'}]}},
  prompts:Object.fromEntries(Object.keys(labels).map(stage=>[stage,`输入提示词样本 ${stage}`])),groups:{
   [group.id]:{point_id:'point',event_id:'event',condition_id:'condition',knowledge_list_id:'list',
    prompt_ids:Object.fromEntries(Object.keys(labels).map(stage=>[stage,stage])),writing,
    sentences:Object.fromEntries(group.utterances.map(item=>[item.id,item.text]))},
  }};
 return [{name,raw},{name:name.replace(/\.json$/,'-detail.json'),raw:JSON.stringify(details)}];
}

async function check(browser,base,[main,detail],fixtureServer){
 const page=await browser.newPage({viewport:{width:1540,height:960}});
 page.setDefaultTimeout(12000);
 const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 try{
  if(fixtureServer){
   const login=await page.request.post(base+'/api/auth/login',{headers:{Origin:base},data:{username:'reviewer',password:'fixture'}});
   assert(login.ok(),await login.text());
  }
  await page.goto(fixtureServer?base+'/admin':base);
  const button=(name,scope=page)=>scope.getByRole('button',{name,exact:true});
  await button('模板库').click();
  const source=page.getByRole('group',{name:'内容来源'});
  await button('文件',source).click();
  // Playwright supplies handles to the browser's native directory picker.
  // The application resolves filenames, parses bytes and renders normally.
  await page.evaluate(({main,detail})=>{
   const fixture=window.traceFixture={main,detail,raw:main.raw,detailRaw:detail.raw,reads:0,picks:0,denied:false};
   const secondName='另一份主库.json',secondDetailName='另一份主库-detail.json';
   const mainHandle={kind:'file',name:main.name,getFile:async()=>new File([fixture.raw],main.name)};
   const secondMain={kind:'file',name:secondName,getFile:async()=>new File([main.raw],secondName)};
   const secondDetail={kind:'file',name:secondDetailName,getFile:async()=>new File([
    JSON.stringify({...JSON.parse(detail.raw),library_name:secondName}),
   ],secondDetailName)};
   const detailHandle={kind:'file',name:detail.name,getFile:async()=>{
    const raw=fixture.detailRaw;
    fixture.reads++;
    if(fixture.held)await fixture.held;
    return new File([raw],detail.name);
   }};
   const directory={kind:'directory',name:'模板目录样本',async *values(){yield mainHandle;yield detailHandle;yield secondMain;yield secondDetail;},
    requestPermission:async()=>fixture.denied?'denied':'granted',
    async getFileHandle(name){
     if(fixture.denied)throw new DOMException('Denied','NotAllowedError');
     if(name===secondDetail.name)return secondDetail;
     if(name!==detail.name||fixture.detailRaw==null)throw new DOMException('Missing','NotFoundError');
     return detailHandle;
    },
   };
   fixture.delay=()=>{fixture.held=new Promise(resolve=>{fixture.release=()=>{fixture.held=null;resolve();};});};
   window.showDirectoryPicker=async()=>{fixture.picks++;return directory;};
   window.showOpenFilePicker=async()=>{throw Error('Main library must be selected within the authorized directory');};
  },{main,detail});
  const choose=page.getByRole('dialog',{name:'选择模板文件'});
  await page.getByText('系统窗口只显示文件夹', {exact:false}).waitFor({timeout:3000});
  await button('选择模板文件夹').click();
  const mainFiles=choose.getByLabel('主库文件');
  assert.deepEqual((await mainFiles.locator('option').allTextContents()).sort(),[main.name,'另一份主库.json'].sort());
  await mainFiles.selectOption(main.name);
  await button('打开主库',choose).click();
  const cards=button('卡片',page.getByRole('group',{name:'模板显示方式'}));
  await cards.waitFor();
  if(await cards.getAttribute('aria-pressed')!=='true')await cards.click();
  const library=JSON.parse(main.raw),trace=JSON.parse(detail.raw);
  const dialog=page.getByRole('dialog',{name:'话术溯源'}),chain=dialog.getByRole('region',{name:'句级溯源'});
  const close=()=>button('关闭话术溯源',dialog).click();
  const reads=()=>page.evaluate(()=>window.traceFixture.reads);
  assert.equal(await reads(),0);
  let sentenceCount=0;
  const groups=library.groups.filter(group=>trace.groups[group.id]&&
   (!process.env.TRACE_GROUP_ID||group.id===process.env.TRACE_GROUP_ID)).slice(0,Number(process.env.TRACE_GROUP_LIMIT||Infinity));
  async function open(group){
   await page.getByLabel('搜索模板').fill(group.name);
   const card=page.locator('[data-feedback-group="'+group.id+'"]:visible').first();
   await button('溯源',card).click();
  }
  for(const group of groups){
   await open(group);
   const entry=trace.groups[group.id],point=trace.points[entry.point_id];
   for(const [id,sentence] of Object.entries(entry.sentences)){
    await dialog.getByLabel('选择话术').selectOption(id);
    await chain.waitFor();
    const stages=chain.locator(':scope > details');
    assert.deepEqual(await stages.locator(':scope > summary').allTextContents(),Object.values(labels));
    assert.equal(await chain.locator(':scope > details[open]').count(),0);
    await dialog.getByLabel('选择话术').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.closest('summary')?.textContent),labels.identify);
    await button('关闭话术溯源',dialog).focus();
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.closest('summary')?.textContent),labels.phrases);
    const stage=key=>chain.locator(`[data-trace-stage="${key}"]`);
    for(const item of trace.knowledge_lists[entry.knowledge_list_id]){
     if(item.original)assert((await stage('identify').textContent()).includes(item.original));
    }
    for(const key of ['enrich','events','conditions','phrases'])assert((await stage(key).textContent()).includes(point.knowledge));
    if(point.type){
     await stage('enrich').locator(':scope > summary').click();
     const type=stage('enrich').locator('dd').filter({hasText:point.type});
     await type.waitFor();
     assert.equal(await type.textContent(),point.type);
    }
    for(const key of ['events','conditions','phrases']){
     for(const event of point.events)assert((await stage(key).textContent()).includes(event.event));
    }
    for(const key of ['conditions','phrases']){
     for(const condition of point.conditions)assert((await stage(key).textContent()).includes(condition.expression));
     assert((await stage(key).locator('ol[aria-label="条件列表"] li[aria-current="true"]').textContent()).includes(point.conditions.find(row=>row.id===entry.condition_id).expression));
    }
    await stage('phrases').locator(':scope > summary').click();
    const generated=stage('phrases').getByRole('list',{name:'生成的话术'});
    assert.equal(await generated.getByRole('listitem').count(),6);
    assert((await generated.locator('[aria-current="true"]').textContent()).includes(sentence));
    assert(await generated.evaluate(list=>{
     const body=list.closest('.template-trace');
     body.scrollTop=body.scrollHeight;
     const last=list.lastElementChild.getBoundingClientRect(),viewport=body.getBoundingClientRect();
     return getComputedStyle(body).overflowY==='auto'&&viewport.bottom<=innerHeight+1&&
      (body.scrollHeight<=body.clientHeight||body.scrollTop>0&&last.bottom<=viewport.bottom+1);
    }), 'The last utterance must be reachable by scrolling inside the trace body');
    for(const text of Object.values(entry.writing))assert((await stage('phrases').textContent()).includes(text));
    for(const [key,prompt] of Object.entries(entry.prompt_ids)){
     if(await stage(key).getAttribute('open')===null)await stage(key).locator(':scope > summary').click();
     const fold=stage(key).locator('details');
     assert.equal(await fold.getAttribute('open'),null);
     assert.equal(await fold.evaluate(element=>element.parentElement.firstElementChild===element),true,
      'The input prompt must be reachable at the top of its stage');
     await fold.locator('summary').click();
     assert.equal(await fold.locator('pre').textContent(),trace.prompts[prompt]);
     await fold.locator('summary').click();
    }
    assert.equal(await dialog.locator('input[type=file]').count(),0);
    sentenceCount++;
   }
   await close();
  }
  assert(sentenceCount>0);
  assert.equal(await reads(),1);

  const group=groups[0];
  const reload=()=>button('重新读取模板文件').click();
  await page.evaluate(()=>{window.traceFixture.raw+='\n';window.traceFixture.detailRaw=null;});
  await reload();
  await open(group);
  await dialog.getByRole('alert').filter({hasText:detail.name}).waitFor();
  await page.evaluate(()=>{window.traceFixture.detailRaw=window.traceFixture.detail.raw;});
  await button('重试读取',dialog).click();
  await dialog.getByRole('status').filter({hasText:'生成后有修改'}).waitFor();
  await chain.waitFor();
  await close();

  await button('关闭文件').click();
  await button(main.name,page.getByRole('region',{name:'最近载入的模板文件'})).click();
  await open(group);
  await chain.waitFor();
  await close();
  assert.deepEqual(await page.evaluate(()=>[window.traceFixture.reads,window.traceFixture.picks]),[2,1]);

  await page.evaluate(()=>{window.traceFixture.denied=true;});
  await reload();
  await open(group);
  await dialog.getByRole('alert').filter({hasText:'权限'}).waitFor();
  await page.evaluate(()=>{window.traceFixture.denied=false;});
  await button('重试读取',dialog).click();
  await chain.waitFor();
  await close();

  await page.evaluate(()=>{
   const fixture=window.traceFixture,unrelated=JSON.parse(fixture.detail.raw);
   unrelated.groups={different:Object.values(unrelated.groups)[0]};
   fixture.detailRaw=JSON.stringify(unrelated);
   fixture.delay();
  });
  await reload();
  await open(group);
  await page.waitForFunction(()=>window.traceFixture.reads===4);
  await close();
  await button('选择其他主库').click();
  await mainFiles.selectOption('另一份主库.json');
  await button('打开主库',choose).click();
  await open(group);
  await dialog.getByText('另一份主库-detail.json',{exact:true}).waitFor();
  await page.evaluate(()=>{window.traceFixture.release();});
  await chain.waitFor();
  assert.equal(await dialog.getByRole('alert').count(),0);
  await close();
  await button('选择其他主库').click();
  await mainFiles.selectOption(main.name);
  await button('打开主库',choose).click();
  await open(group);
  await dialog.getByRole('alert').filter({hasText:'不匹配'}).waitFor();
  assert.equal(await chain.count(),0);
  await close();
  await button('数据库',source).click();
  await page.waitForLoadState('networkidle');
  assert.equal(await button('溯源').count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({base,sentences:sentenceCount,lazyRead:true,recentDirectory:true,retries:true,missingDetail:true,sameNameMismatch:true,fileSwitch:true}));
 }finally{await page.close();}
}

(async()=>{
 const files=sample(process.argv[2]);
 const fixture=process.env.TRACE_BASES?undefined:spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),
  ['-u','frontend/browser_templates_fixture.py'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'},stdio:['ignore','pipe','inherit']});
 const output=fixture&&readline.createInterface({input:fixture.stdout});
 let browser;
 try{
  const base=process.env.TRACE_BASES??await Promise.race([once(output,'line').then(([line])=>'http://127.0.0.1:'+JSON.parse(line).port),
   once(fixture,'exit').then(([code])=>{throw Error('fixture exit '+code);})]);
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
  for(const url of base.split(','))await check(browser,url,files,!!fixture);
 }finally{await browser?.close();output?.close();fixture?.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
