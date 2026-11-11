// Run from repository root against a disposable localhost fixture only.
const {spawn,execFileSync}=require('node:child_process'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),out=path.join(root,'temp/proposal-navigation-browser');fs.mkdirSync(out,{recursive:true});
const child=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_proposal_fixture.py'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:path.join(root,'temp'),TMP:path.join(root,'temp')}});
let browser,last,localBase,localChild;const errors=[];let requests=0;const waiting=[];
async function fetchRoute(route,options){if(requests>=4)await new Promise(resolve=>waiting.push(resolve));requests++;try{return await route.fetch(options);}finally{requests--;waiting.shift()?.();}}
(async()=>{
 let output='';const fixture=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('fixture startup '+output)),30000);child.stdout.on('data',b=>{output+=b;try{const f=JSON.parse(output.split('\n')[0]);clearTimeout(t);resolve(f);}catch{}});child.stderr.on('data',b=>process.stderr.write(b));child.on('exit',c=>{if(c)reject(Error('fixture exit '+c));});});
 const base='http://127.0.0.1:'+fixture.port,headers={host:'klywa.xyz',origin:'https://klywa.xyz'};
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 async function page(width=1440,role='admin',local=false,long=false,zoom=1,beforeOpen){
  const endpoint=local?localBase:base,requestHeaders=local?{origin:endpoint}:headers;
  const c=await browser.newContext({viewport:{width:Math.round(width/zoom),height:Math.round(1000/zoom)},deviceScaleFactor:zoom});
  if(!local)await c.request.post(endpoint+'/api/auth/login',{headers:requestHeaders,data:{username:role==='admin'?'reviewer':'alice',password:'fixture'}});
  await c.addInitScript(()=>localStorage.setItem('wxq.preferences',JSON.stringify({view:'notes',selected:'one',mode:'full'})));
  const p=await c.newPage();last=p;p.on('pageerror',e=>errors.push(e.message));
  await p.route(endpoint+'/**',async route=>{try{const response=await fetchRoute(route,{headers:{...route.request().headers(),...requestHeaders}});if(route.request().url().endsWith('/api/auth/me')&&(local||long)){const value=await response.json();if(local)value.mode='local';if(long){value.username='这是用于检查顶栏裁切的很长用户名'.repeat(4);value.sync={state:'pending',phase:'custom',message:'这是很长的同步状态说明'.repeat(12)};}await route.fulfill({response,json:value});}else await route.fulfill({response});}catch(e){await route.abort('failed').catch(()=>{});}});
  await beforeOpen?.(p,endpoint);
  await p.goto(endpoint);if(!beforeOpen)await p.locator('.json-entry').first().waitFor();return p;
 }
 async function open(p){if(await p.getByRole('dialog',{name:'提案审核'}).isVisible())return;if(!await p.locator('.account-items').getByRole('button',{name:'提案',exact:true}).isVisible())await p.getByRole('button',{name:'账号菜单',exact:true}).click();await p.locator('.account-items').getByRole('button',{name:'提案',exact:true}).click();await p.getByRole('dialog',{name:'提案审核'}).waitFor();}
 const card=(p,id)=>p.locator(`[data-proposal-id="${id}"]`);
 async function jump(p,id,target){await open(p);await card(p,id).getByRole('button',{name:'定位到原文',exact:true}).click();await p.getByRole('dialog',{name:'提案审核'}).waitFor({state:'hidden'});await p.locator('.proposal-location-target').waitFor();if(target)assert.equal(await p.locator('.proposal-location-target').evaluate(el=>el.dataset.node||el.id),target);assert(await p.locator('.proposal-location-target').evaluate(el=>document.activeElement===el));}
 const p=await page(),drawer=p.getByRole('dialog',{name:'提案审核'});
 await jump(p,fixture.ids.first,'one-a');await p.waitForTimeout(2600);assert.equal(await p.locator('.proposal-location-target').count(),0);
 await open(p);await drawer.getByLabel('作者',{exact:true}).fill('alice');await card(p,fixture.ids.changed).scrollIntoViewIfNeeded();const offset=await drawer.evaluate(el=>el.scrollTop);await jump(p,fixture.ids.changed,'source:target');assert((await p.locator('.content-scroll').evaluate(el=>el.scrollTop))>100);await p.screenshot({path:path.join(out,'source-highlight-desktop.png')});
 await open(p);assert.equal(await drawer.getByLabel('作者',{exact:true}).inputValue(),'alice');assert(Math.abs(await drawer.evaluate(el=>el.scrollTop)-offset)<5,'drawer list position lost');
 await jump(p,fixture.ids.inserted,fixture.approvedNode);
 await open(p);await drawer.getByLabel('状态',{exact:true}).selectOption('closed');await jump(p,fixture.ids.approved,fixture.approvedNode);
 await open(p);await jump(p,fixture.ids.removed,'chapter-two');await p.getByText('原条目或插入位置已变化，已定位到所在章节。',{exact:false}).waitFor();
 await open(p);await jump(p,fixture.ids.orphan);assert(await p.locator('.proposal-location-target').evaluate(el=>el.classList.contains('content-scroll')));await p.getByText('原位置已变化，已打开笔记开头。',{exact:false}).waitFor();
 // Failed loads cannot close the panel or mutate the reader/draft.
 await open(p);await drawer.getByLabel('状态',{exact:true}).selectOption('pending');let fail=true;
 await p.route(base+'/api/notes/two',route=>fail?route.fulfill({status:404,json:{error:'笔记不存在'}}):route.fallback());
 const before=await p.locator('.compact-note-heading h1').textContent();await card(p,fixture.ids.changed).getByRole('button',{name:'定位到原文',exact:true}).click();await drawer.getByText('无法定位：笔记不存在',{exact:true}).waitFor();assert.equal(await p.locator('.compact-note-heading h1').textContent(),before);fail=false;
 // An unsaved proposal anywhere blocks another card's navigation and keeps its lease.
 await card(p,fixture.ids.first).getByLabel('正文',{exact:true}).click();await card(p,fixture.ids.first).getByLabel('正文',{exact:true}).fill('未保存提案改稿');
 const locksUrl=base+'/api/edit-locks?note_id=one&client_id=browser-check';const held=await p.request.get(locksUrl,{headers}).then(r=>r.json());
 await card(p,fixture.ids.changed).getByRole('button',{name:'定位到原文',exact:true}).click();await drawer.getByText('提案改稿尚未保存，请先保存或撤销改动后定位。',{exact:true}).first().waitFor();assert.equal(await card(p,fixture.ids.first).getByLabel('正文',{exact:true}).textContent(),'未保存提案改稿');const kept=await p.request.get(locksUrl,{headers}).then(r=>r.json());assert.deepEqual(kept.leases.map(l=>l.id),held.leases.map(l=>l.id));await card(p,fixture.ids.first).getByRole('button',{name:'撤销改动',exact:true}).click();
 // Repeated clicks while the latest pair loads submit only one navigation.
 let release,seen;const gate=new Promise(r=>release=r),started=new Promise(r=>seen=r);let holding=true,loads=0;
 await p.route(base+'/api/notes/two',async route=>{if(!holding)return route.fallback();loads++;const response=await fetchRoute(route,{headers:{...route.request().headers(),...headers}});seen();await gate;await route.fulfill({response});});
 await card(p,fixture.ids.changed).getByRole('button',{name:'定位到原文',exact:true}).evaluate(el=>{el.click();el.click();});await started;assert.equal(loads,1);holding=false;release();await drawer.waitFor({state:'hidden'});
 // Inline note draft guard remains active.
 await open(p);await jump(p,fixture.ids.first,'one-a');await p.getByRole('button',{name:'编辑段落：当前条目',exact:true}).click();await p.locator('[data-entry=one-a]').getByLabel('正文',{exact:true}).fill('未保存笔记草稿');await open(p);await card(p,fixture.ids.changed).getByRole('button',{name:'定位到原文',exact:true}).click();await drawer.getByText('定位已取消，请先保存或取消当前修改。',{exact:true}).waitFor();assert.equal(await p.locator('[data-entry=one-a]').getByLabel('正文',{exact:true}).inputValue(),'未保存笔记草稿');await drawer.getByRole('button',{name:'关闭',exact:true}).click();await p.locator('.review-toolbar').getByRole('button',{name:'取消',exact:true}).click();
 // A main draft created during the asynchronous preflight must also block it.
 await open(p);let releaseLate,seeLate;const lateGate=new Promise(r=>releaseLate=r),lateSeen=new Promise(r=>seeLate=r);let late=true;
 await p.route(base+'/api/notes/two',async route=>{if(!late)return route.fallback();const response=await fetchRoute(route,{headers:{...route.request().headers(),...headers}});seeLate();await lateGate;await route.fulfill({response});});
 await card(p,fixture.ids.changed).getByRole('button',{name:'定位到原文',exact:true}).click();await lateSeen;
 await p.getByRole('button',{name:'编辑段落：当前条目',exact:true}).click();await p.locator('[data-entry=one-a]').getByLabel('正文',{exact:true}).fill('请求期间新建的正文草稿');late=false;releaseLate();
 await drawer.getByText('定位已取消，请先保存或取消当前修改。',{exact:true}).waitFor();assert.equal(await p.locator('[data-entry=one-a]').getByLabel('正文',{exact:true}).inputValue(),'请求期间新建的正文草稿');await drawer.getByRole('button',{name:'关闭',exact:true}).click();await p.locator('.review-toolbar').getByRole('button',{name:'取消',exact:true}).click();
 console.log('Same/cross-note, data-node, insert/delete/closed fallbacks, highlight/focus, saved filters/offset, errors, dirty leases and repeated clicks: PASS');
 let loadReading,readingRequested;
 const readingGate=new Promise(resolve=>loadReading=resolve);
 const readingStarted=new Promise(resolve=>readingRequested=resolve);
 const cold=await page(390,'admin',false,false,1,(tab,endpoint)=>tab.route(endpoint+'/api/notes/one',async route=>{
  readingRequested();
  await readingGate;
  await route.fallback();
 }));
 await readingStarted;
 await open(cold);
 const coldCard=card(cold.getByRole('dialog',{name:'提案审核'}),fixture.ids.first);
 const coldText=coldCard.getByRole('textbox',{name:'正文',exact:true});
 await coldText.click();await coldText.fill('首篇笔记加载前输入的改稿');
 await coldCard.getByRole('button',{name:'撤销改动',exact:true}).waitFor();
 loadReading();await cold.locator('.json-entry').first().waitFor();
 assert.equal(await coldText.textContent(),'首篇笔记加载前输入的改稿');
 await coldCard.getByRole('button',{name:'撤销改动',exact:true}).click();
 await cold.context().close();
 await open(p);
 const ordinary=card(drawer,fixture.ids.first);
 const ordinaryText=ordinary.getByRole('region',{name:'拟修改'}).getByRole('textbox',{name:'正文',exact:true});
 await ordinary.getByRole('textbox',{name:'名称',exact:true}).focus();
 await p.keyboard.press('Tab');
 assert(await ordinaryText.evaluate(el=>el===document.activeElement));
 await ordinaryText.fill('已保存的提案改稿');
 assert.equal(await ordinaryText.locator('ins').textContent(),'已保存的提案改稿');
 await p.keyboard.press('End');await p.keyboard.press('Enter');await p.keyboard.insertText('换行');
 assert.equal(await ordinaryText.textContent(),'已保存的提案改稿\n换行');
 await ordinaryText.fill('已保存的提案改稿');
 await ordinary.getByRole('button',{name:'保存改稿',exact:true}).click();
 await ordinary.getByRole('button',{name:'撤销改动',exact:true}).waitFor({state:'hidden'});
 await ordinaryText.click();await ordinaryText.fill('待撤销的第二次改稿');
 await drawer.getByRole('button',{name:'关闭',exact:true}).click();
 assert(await drawer.isVisible());
 await drawer.getByRole('textbox',{name:'笔记',exact:true}).fill('隐藏当前提案');
 assert(await ordinary.isVisible());
 await ordinary.getByRole('button',{name:'撤销改动',exact:true}).click();
 assert.equal(await ordinaryText.textContent(),'已保存的提案改稿');
 const supported=card(drawer,fixture.ids.evidence);
 const supportedText=supported.getByRole('textbox',{name:'正文',exact:true});
 await supportedText.click();await supportedText.fill('证据仍适用的改稿');
 const confirmation=supported.getByRole('checkbox',{name:'我已核对证据，仍支持本次改稿'});
 const approve=supported.getByRole('button',{name:'确认此条',exact:true});
 assert(await approve.isDisabled());
 await confirmation.check();assert(await approve.isEnabled());
 await supportedText.dispatchEvent('compositionstart');
 assert(await approve.isDisabled());
 await supportedText.fill('再次修改后核对的正文');
 await supportedText.dispatchEvent('compositionend');
 assert(!(await confirmation.isChecked()));assert(await approve.isDisabled());
 await confirmation.check();await approve.click();
 await supported.waitFor({state:'hidden'});
 const accepted=await p.request.get(base+'/api/proposals?status=approved&note_id=one',{headers}).then(r=>r.json());
 assert.equal(accepted.items.find(item=>item.id===fixture.ids.evidence).proposed_node.value,'再次修改后核对的正文');
 console.log('Direct keyboard and mouse editing, save and undo, drawer guards and evidence approval: PASS');
 for(const width of [375,390,430,760,768,1024,1440])for(const role of ['admin','annotator']){
  const v=await page(width,role,false,true);await v.waitForTimeout(100);
  if(width<=760)await v.getByRole('button',{name:'账号菜单',exact:true}).click();
  const boxes=await v.locator('.account-items').evaluate(el=>[...el.querySelectorAll('button,select')].filter(e=>e.getClientRects().length).map(e=>({text:e.textContent,w:e.clientWidth,sw:e.scrollWidth,r:e.getBoundingClientRect().toJSON(),h:el.closest('.app-header').getBoundingClientRect().toJSON(),wrap:getComputedStyle(e).whiteSpace})));
  for(const b of boxes){assert.equal(b.wrap,'nowrap');assert(b.sw<=b.w+1,'text clipped '+width+' '+b.text);if(width>760){assert(b.r.bottom<=b.h.bottom+1);assert(b.r.top>=b.h.top);}}
  if(width>760){const controls=boxes.filter(b=>['提案','退出登录'].includes(b.text));assert.equal(Math.round(controls[0].r.top),Math.round(controls[1].r.top));}else for(const b of boxes)assert(b.r.height>=44);
  assert(await v.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'page overflow '+width);
  await v.screenshot({path:path.join(out,`header-${width}-${role}.png`)});
  if(width===390&&role==='admin'){await jump(v,fixture.ids.changed,'source:target');await v.screenshot({path:path.join(out,'source-highlight-mobile.png')});}
  await v.unrouteAll({behavior:'wait'});await v.context().close();
 }
 localChild=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_proposal_fixture.py','--local'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:path.join(root,'temp'),TMP:path.join(root,'temp')}});
 const localFixture=await new Promise((resolve,reject)=>{let value='';const timer=setTimeout(()=>reject(Error('local fixture startup '+value)),30000);localChild.stdout.on('data',b=>{value+=b;try{const f=JSON.parse(value.split('\n')[0]);clearTimeout(timer);resolve(f);}catch{}});localChild.stderr.on('data',b=>process.stderr.write(b));});localBase='http://127.0.0.1:'+localFixture.port;
 for(const [width,zoom] of [[1440,1.25],[1024,1.25]]){const v=await page(width,'admin',true,true,zoom);assert(await v.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'local/zoom page overflow');await v.screenshot({path:path.join(out,`local-zoom-${width}.png`)});await v.unrouteAll({behavior:'wait'});await v.context().close();}
 assert.deepEqual(errors,[]);console.log('Seven viewports, public roles, local controls, long names/status, 125% layout and screenshots: PASS');console.log(out);
})().catch(async e=>{console.error(e.stack);if(last&&!last.isClosed()){fs.writeFileSync(path.join(out,'failure.html'),await last.content());await last.screenshot({path:path.join(out,'failure.png')});}process.exitCode=1;}).finally(async()=>{if(browser){for(const c of browser.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await browser.close();}for(const process of [child,localChild].filter(Boolean)){try{execFileSync('taskkill',['/PID',String(process.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}}});
