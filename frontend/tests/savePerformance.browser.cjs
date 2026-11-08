// Uses an installed Playwright via NODE_PATH; launches Vite only for the hook harness.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const base='http://127.0.0.1:5174';
(async()=>{
 const vite=spawn(process.execPath,[path.resolve('node_modules/vite/bin/vite.js'),'--port','5174','--strictPort'],{cwd:path.resolve('.'),windowsHide:true,stdio:'ignore'});
 let browser;
 try{
  for(let i=0;i<60;i++){try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,200));}
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const sources=[0,1,2].map(i=>({id:'perf-'+i,title:'待忽略 '+i,url:'https://example.com/'+i,author:'UP主',stage:'registered',knowledge_status:'unprocessed',linked_notes:[],revision:'old'}));
  let release,releaseSecond,started=0;
  await page.route(/\/api\/sources$/,route=>route.fulfill({json:sources}));
  await page.route(/\/api\/sources\/perf-\d$/,async route=>{
   started++;const id=route.request().url().split('/').pop();
   if(id==='perf-0')await new Promise(r=>release=r);
   if(id==='perf-1')await new Promise(r=>releaseSecond=r);
   if(id==='perf-1')return route.fulfill({status:503,json:{error:'模拟保存失败'}});
   const source=sources.find(s=>s.id===id);Object.assign(source,route.request().postDataJSON(),{revision:'new'});
   await route.fulfill({json:source});
  });
  await page.addInitScript(()=>localStorage.setItem('wxq.preferences',JSON.stringify({view:'sources'})));
  await page.goto(process.env.SOURCE_TEST_URL||'http://127.0.0.1:8765');await page.waitForLoadState('networkidle');
  const row=i=>page.locator('.external-row').filter({hasText:'待忽略 '+i});
  await row(0).getByRole('button',{name:'忽略',exact:true}).click();
  await row(0).getByRole('button',{name:'忽略中…',exact:true}).waitFor();
  assert.equal(await row(0).getByRole('button',{name:'忽略中…',exact:true}).isDisabled(),true);
  assert.equal(await row(1).getByRole('button',{name:'忽略',exact:true}).isEnabled(),true);
  await row(1).getByRole('button',{name:'忽略',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.external-row button:disabled').length>1);
  assert.equal(started,2);releaseSecond();await page.getByRole('alert').filter({hasText:'模拟保存失败'}).waitFor();
  assert.equal(await row(1).getByRole('button',{name:'忽略',exact:true}).isEnabled(),true);
  release();await row(0).waitFor({state:'detached'});assert.equal(await row(1).count(),1);
  await page.close();

  const reader=await browser.newPage();reader.on('pageerror',error=>errors.push(error.message));
  let revision='r1',counts={},delayNext=false,releaseOld;
  const note=()=>({id:'n',type:'other',title:'Note',revision,claims:[],entities:[],core:[],document:{schema_version:6,nodes:[{id:'h',type:'heading',level:1,title:'Note'}]}});
  await reader.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),key=url.pathname;counts[key]=(counts[key]||0)+1;
   let json;
   if(key==='/api/notes/catalog')json={workspace_id:'test',revision,ready:true,notes:[note()]};
   else if(key==='/api/options')json={entities:[],factions:[],sections:{}};
   else if(key==='/api/notes/n/reading'){json={note_id:'n',revision,sections:[]};if(delayNext){delayNext=false;await new Promise(r=>releaseOld=r);}}
   else if(key==='/api/notes/n/revision')json={revision};
   else json=note();
   await route.fulfill({json,headers:{'X-Workspace-Id':'test'}}).catch(()=>{});
  });
  await reader.goto(base+'/tests/readerHarness.html');
  await reader.waitForFunction(()=>document.querySelector('output')?.textContent.includes('"verified":true'));
  counts={};revision='r2';await reader.getByRole('button',{name:'Accept save'}).click();
  await reader.waitForFunction(()=>document.querySelector('output')?.textContent.includes('"reader":"r2"'));
  assert.equal(counts['/api/notes/n']||0,0);assert.equal(counts['/api/notes/n/reading'],1);assert.equal(counts['/api/notes/catalog'],1);
  // Later external revisions must consume a fresh detail, not reuse r2 forever.
  counts={};revision='r3';await reader.getByRole('button',{name:'External save'}).click();
  await reader.waitForFunction(()=>document.querySelector('output')?.textContent.includes('"reader":"r3"'));
  assert.equal(counts['/api/notes/n'],1);assert.equal(counts['/api/notes/n/reading'],1);
  // A delayed pre-save refresh must not overwrite the accepted revision.
  delayNext=true;await reader.getByRole('button',{name:'External save'}).click();
  while(!releaseOld)await new Promise(r=>setTimeout(r,10));
  revision='r2';await reader.getByRole('button',{name:'Accept save'}).click();releaseOld();
  await reader.waitForFunction(()=>document.querySelector('output')?.textContent.includes('"reader":"r2"'));
  await reader.getByRole('button',{name:'Clear selection'}).click();await reader.getByRole('button',{name:'External save'}).click();
  assert.deepEqual(errors,[]);console.log('PASS: independent ignores, failed save retained, one refresh per save, external refresh and stale-response guards');
 }finally{if(browser)await browser.close();vite.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
