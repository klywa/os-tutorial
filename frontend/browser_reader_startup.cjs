const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),out=path.join(root,'temp/reader-startup-browser'),children=[];fs.mkdirSync(out,{recursive:true});let browser,last;
async function fixture(local){
 const child=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_fixture.py','--startup-test',...(local?['--local']:[])],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:path.join(root,'temp'),TMP:path.join(root,'temp')}});children.push(child);
 return new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('fixture timeout '+text)),30000);child.stdout.on('data',b=>{text+=b;try{const value=JSON.parse(text.split('\n')[0]);clearTimeout(timer);resolve('http://127.0.0.1:'+value.port);}catch{}});child.stderr.on('data',b=>process.stderr.write(b));child.on('exit',code=>{if(code){clearTimeout(timer);reject(Error('fixture exited '+code));}});});
}
async function open(base,width,local){
 const page=await browser.newPage({viewport:{width,height:900}});last=page;
 await page.addInitScript(()=>localStorage.setItem('wxq.preferences',JSON.stringify({view:'notes',selected:'browser-note',mode:'full'})));
 if(!local)await page.route(base+'/**',async route=>{const response=await route.fetch({headers:{...route.request().headers(),host:'klywa.xyz',origin:'https://klywa.xyz'}});await route.fulfill({response});});
 return page;
}
async function select(page,width,title){if(width<=760)await page.getByRole('button',{name:'目录',exact:true}).click();await page.getByRole('button',{name:title,exact:true}).click();await page.locator('.note-heading h1').filter({hasText:title}).waitFor();}
async function close(page){await page.unrouteAll({behavior:'ignoreErrors'});await page.context().close();}
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 const publicBase=await fixture(false),localBase=await fixture(true);
 for(const width of [390,1440]){
  const page=await open(publicBase,width,false);let releaseCards,cardCount=0,bodyAtRequest=false;const gate=new Promise(resolve=>releaseCards=resolve);let started;const cardsStarted=new Promise(resolve=>started=resolve);
  await page.route(publicBase+'/api/cards',async route=>{cardCount++;bodyAtRequest=await page.locator('.json-entry').count()>0;started();await gate;const response=await route.fetch({headers:{...route.request().headers(),host:'klywa.xyz',origin:'https://klywa.xyz'}});await route.fulfill({response});});
  await page.goto(publicBase);await page.getByLabel('用户名').fill('reader');await page.getByLabel('密码',{exact:true}).fill('fixture');await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.locator('.json-entry').first().waitFor();await cardsStarted;
  assert(bodyAtRequest,'card catalog must start after note DOM exists');assert.equal(cardCount,1);assert.equal(await page.locator('.entity-chip').count(),0);
  await page.screenshot({path:path.join(out,'plain-note-'+width+'.png')});releaseCards();await page.locator('.entity-chip').filter({hasText:'测试英雄'}).first().waitFor();assert.equal(cardCount,1);
  await select(page,width,'追加样例');await select(page,width,'协作阅读样例');assert.equal(cardCount,1,'note navigation must retain the shared catalog');await close(page);
  const lp=await open(localBase,width,true);let activityReads=0;
  await lp.route(localBase+'/api/crawler/activity',route=>{activityReads++;return route.fulfill({json:[{bvid:'fixture-task',url:'https://example.com',title:'正在运行的任务',state:'running',progress:{phase:'downloading'},jobs:[{id:'job',name:'样例批次'}]}]});});
  await lp.goto(localBase);await lp.locator('.json-entry').first().waitFor();const panel=lp.getByRole('region',{name:'全局任务监控'}),toggle=panel.locator('button[aria-expanded]');
  await lp.waitForFunction(()=>document.querySelector('.global-activity')?.textContent.includes('正在下载 1'));assert.equal(await toggle.getAttribute('aria-expanded'),'false');assert.equal(await panel.locator('.activity-body').count(),0);
  await select(lp,width,'追加样例');assert.equal(await toggle.getAttribute('aria-expanded'),'false');await toggle.click();await panel.getByText('正在运行的任务',{exact:true}).waitFor();
  await select(lp,width,'协作阅读样例');assert.equal(await toggle.getAttribute('aria-expanded'),'true');await toggle.click();await lp.waitForTimeout(2100);assert.equal(await toggle.getAttribute('aria-expanded'),'false');
  await lp.screenshot({path:path.join(out,'folded-tasks-'+width+'.png')});await lp.reload();await lp.locator('.json-entry').first().waitFor();assert.equal(await toggle.getAttribute('aria-expanded'),'false');assert(activityReads>=2);assert(await lp.evaluate(()=>document.documentElement.scrollWidth)<=width+1);await close(lp);
 }
 console.log('PASS: body before delayed cards, progressive entity enhancement, one catalog per session, default-folded active tasks, preserved choices across notes/polls, refresh reset; mobile+desktop. '+out);
})().catch(async e=>{console.error(e.stack);if(last&&!last.isClosed())await last.screenshot({path:path.join(out,'failure.png')});process.exitCode=1;}).finally(async()=>{if(browser){for(const c of browser.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await browser.close();}for(const child of children)try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}});
