// Disposable localhost UI acceptance; uses bundled Node Playwright (Python binding unavailable).
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),artifacts=path.join(root,'temp/private-reader-browser');fs.mkdirSync(artifacts,{recursive:true});
const children=[];let browser,last;const errors=[];
async function fixture(local=false){
 const child=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_fixture.py',...(local?['--local']:[])],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:path.join(root,'temp'),TMP:path.join(root,'temp')}});children.push(child);
 return new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('fixture timeout '+output)),30000);child.stdout.on('data',b=>{output+=b;try{const result=JSON.parse(output.split('\n')[0]);clearTimeout(timer);resolve(result);}catch{}});child.stderr.on('data',b=>process.stderr.write(b));child.on('exit',code=>{clearTimeout(timer);if(code)reject(Error('fixture exit '+code));});});
}
async function open(base,width=1440,local=false){
 const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();last=page;
 page.on('pageerror',e=>errors.push(e.message));
 if(!local)await page.route(base+'/**',async route=>{const response=await route.fetch({headers:{...route.request().headers(),host:'klywa.xyz',origin:'https://klywa.xyz'}});await route.fulfill({response});});
 return page;
}
async function login(page,name){await page.getByLabel('用户名',{exact:true}).fill(name);await page.getByLabel('密码',{exact:true}).fill('fixture');await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.json-entry').first().waitFor();}
async function account(page,width){if(width<=760)await page.getByRole('button',{name:'账号菜单',exact:true}).click();}
async function countCache(page){return page.evaluate(()=>new Promise(resolve=>{const request=indexedDB.open('wxq.reader',1);request.onsuccess=()=>{const db=request.result;if(!db.objectStoreNames.contains('entries')){db.close();resolve(0);return;}const count=db.transaction('entries').objectStore('entries').count();count.onsuccess=()=>{db.close();resolve(count.result);};};}));}
(async()=>{
 const data=await fixture(),base='http://127.0.0.1:'+data.port;
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 for(const width of [390,1440]){
  const page=await open(base,width),requests=[];page.on('request',r=>{if(r.url().includes('/api/'))requests.push(r.url());});
  await page.addInitScript(()=>{if(sessionStorage.getItem('seeded'))return;sessionStorage.setItem('seeded','yes');localStorage.setItem('wxq.reader.workspace','old-public');const request=indexedDB.open('wxq.reader',1);request.onupgradeneeded=()=>request.result.createObjectStore('entries',{keyPath:'key'});request.onsuccess=()=>{const d=request.result,tx=d.transaction('entries','readwrite');tx.objectStore('entries').put({key:'legacy',value:'OLD SECRET'});tx.oncomplete=()=>d.close();};});
  await page.goto(base);await page.getByRole('heading',{name:'账号登录'}).waitFor();
  assert.equal(await page.locator('.app').count(),0);assert(requests.every(u=>u.endsWith('/api/auth/me')));assert.equal(await countCache(page),0);
  await page.screenshot({path:path.join(artifacts,`login-${width}.png`)});
  await page.getByLabel('用户名').fill('unknown');await page.getByLabel('密码',{exact:true}).fill('wrong');await page.getByRole('button',{name:'登录',exact:true}).click();await page.getByRole('alert').waitFor();
  requests.length=0;await login(page,'reader');
  assert.equal(await page.getByRole('button',{name:'编辑笔记',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'提案',exact:true}).count(),0);
  assert(!requests.some(u=>/\/(proposals|edit-locks)(?:[/?]|$)/.test(u)));assert.equal(await countCache(page),0);
  const actions=await page.locator('.note-actions button').allTextContents();assert.equal(actions[actions.indexOf('导出整篇')+1],'导出json');
  for(const name of ['导出整篇','导出json']){
   const download=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();const file=await download;const target=path.join(artifacts,width+'-'+file.suggestedFilename());await file.saveAs(target);
   if(name==='导出json'){const json=JSON.parse(fs.readFileSync(target,'utf8'));assert.equal(json.note.id,'browser-note');assert.equal(json.schema_version,1);assert(JSON.stringify(json).includes('终局技巧'));assert(!JSON.stringify(json).includes('提案修改内容'));}
   else assert(fs.readFileSync(target,'utf8').includes('终局技巧'));
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+1);await page.screenshot({path:path.join(artifacts,`viewer-${width}.png`)});
  await account(page,width);await page.getByRole('button',{name:'退出登录',exact:true}).click();await page.getByRole('heading',{name:'账号登录'}).waitFor();assert.equal(await page.locator('.json-entry').count(),0);assert.equal(await countCache(page),0);
  await login(page,'reader');await page.context().clearCookies();await page.getByRole('heading',{name:'账号登录'}).waitFor({timeout:12000});assert.equal(await page.locator('.app').count(),0);
  await page.reload();await page.getByRole('heading',{name:'账号登录'}).waitFor();await page.unrouteAll({behavior:"ignoreErrors"});await page.context().close();
 }
 const admin=await open(base);await admin.clock.install();await admin.goto(base+'/admin');await login(admin,'reviewer');
 let releaseRole,roleStarted=false,meDuringRole=0;const roleGate=new Promise(resolve=>{releaseRole=resolve;});
 admin.on('request',request=>{if(roleStarted&&request.url().endsWith('/api/auth/me'))meDuringRole++;});
 await admin.route(base+'/api/auth/role',async route=>{roleStarted=true;await roleGate;const response=await route.fetch({headers:{...route.request().headers(),host:'klywa.xyz',origin:'https://klywa.xyz'}});await route.fulfill({response});});
 await admin.getByLabel('切换身份').selectOption('viewer');await admin.waitForFunction(()=>!document.querySelector('.app'));
 await admin.clock.fastForward(61000);const observedMe=meDuringRole;roleStarted=false;releaseRole();assert.equal(observedMe,0,'background /me must not run during role transition');
await admin.locator('.account-name').filter({hasText:'浏览者'}).waitFor();assert.equal(await admin.getByRole('button',{name:'编辑笔记',exact:true}).count(),0);await admin.getByLabel('切换身份').selectOption('admin');await admin.getByRole('button',{name:'编辑笔记',exact:true}).waitFor();await admin.unrouteAll({behavior:"ignoreErrors"});await admin.context().close();
 const local=await fixture(true),localBase='http://127.0.0.1:'+local.port,lp=await open(localBase,1440,true);await lp.goto(localBase);await lp.locator('.json-entry').first().waitFor();assert.equal(await lp.getByRole('heading',{name:'账号登录'}).count(),0);await lp.getByLabel('切换身份').selectOption('viewer');await lp.locator('.account-name').filter({hasText:'浏览者'}).waitFor();assert.equal(await lp.getByRole('button',{name:'编辑笔记',exact:true}).count(),0);await lp.getByLabel('切换身份').selectOption('admin');await lp.getByRole('button',{name:'编辑笔记',exact:true}).waitFor();await lp.context().close();
 assert.deepEqual(errors,[]);console.log('PASS: private login, legacy-cache purge, viewer UI/no editing requests, MD/JSON downloads, logout, expiry, admin/local role simulation at mobile+desktop. Screenshots: '+artifacts);
})().catch(async error=>{console.error(error.stack);if(last&&!last.isClosed())await last.screenshot({path:path.join(artifacts,'failure.png')});process.exitCode=1;}).finally(async()=>{if(browser){for(const context of browser.contexts())for(const page of context.pages())await page.unrouteAll({behavior:"ignoreErrors"});await browser.close();}for(const child of children){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}}});
