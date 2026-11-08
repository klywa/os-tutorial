// Help-only acceptance on a disposable random-port fixture; never mutates real data.
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),artifacts=path.join(root,'temp/template-help-browser');fs.mkdirSync(artifacts,{recursive:true});
const fixture=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_templates_fixture.py'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
let browser,page;const errors=[];
(async()=>{
 const info=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('fixture startup '+output)),30000);fixture.stdout.on('data',chunk=>{output+=chunk;try{const data=JSON.parse(output.split('\n')[0]);clearTimeout(timer);resolve(data);}catch{}});fixture.stderr.on('data',chunk=>process.stderr.write(chunk));fixture.on('exit',code=>{if(code)reject(Error('fixture exit '+code));});});
 const base='http://127.0.0.1:'+info.port;
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.__copies=[];window.__denyCopy=false;Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{if(window.__denyCopy)throw Error('denied');window.__copies.push(text);}}});});
 await page.goto(base+'/admin');await page.getByLabel('用户名',{exact:true}).fill('reviewer');await page.getByLabel('密码',{exact:true}).fill('fixture');await page.getByRole('button',{name:'登录',exact:true}).click();
 const warning=page.getByRole('dialog',{name:'模板关联资料有变化'});await warning.waitFor();await warning.getByRole('button',{name:'已知晓，稍后检查'}).click();await warning.waitFor({state:'hidden'});
 await page.getByRole('button',{name:'模板库',exact:true}).click();
 const initial=await page.evaluate(async()=>await(await fetch('/api/templates')).json());
 async function help(role,mobile=false){
  const opener=page.getByRole('button',{name:'帮助',exact:true});await opener.click();
  const dialog=page.getByRole('dialog',{name:'话术模板库帮助',exact:true});await dialog.waitFor();
  assert(await dialog.getByRole('button',{name:'关闭话术模板库帮助',exact:true}).evaluate(el=>el===document.activeElement),'initial focus in dialog');
  assert.equal(await dialog.locator('table').count(),10);assert.equal(await dialog.locator('.entity-chip').count(),0,'protocol code cannot become gameplay chips');
  assert.equal(await dialog.locator('a[href^="examples/"]').count(),0);
  await page.screenshot({path:path.join(artifacts,role+'-contract.png'),fullPage:true});
  for(const [title,filename,id] of [['最小示例','speech-template-library-minimal.json','minimal'],['完整示例','speech-template-library.json','complete']]){
   await dialog.getByRole('link',{name:title,exact:true}).click();
   assert.equal(await dialog.locator('#template-help-'+id).count(),1);
   const code=dialog.getByRole('textbox',{name:title+' JSON',exact:true}),text=await code.inputValue();
   assert(await code.getAttribute('readonly')!==null);assert.equal(JSON.parse(text).schema_version,2);assert(JSON.parse(text).groups.every(g=>g.utterances.every(u=>typeof u==='string')&&!('related_entities' in g)));
   assert.deepEqual(JSON.parse(text),JSON.parse(fs.readFileSync(path.join(root,'docs/examples',filename),'utf8')));
   await dialog.getByRole('button',{name:'一键复制'+title,exact:true}).click();
   await dialog.getByRole('region',{name:title,exact:true}).getByRole('status').filter({hasText:'JSON 已复制'}).waitFor();
   assert.equal(await page.evaluate(()=>window.__copies.at(-1)),text);
   await page.evaluate(()=>window.__denyCopy=true);await dialog.getByRole('button',{name:'一键复制'+title,exact:true}).click();
   await dialog.getByRole('region',{name:title,exact:true}).getByRole('status').filter({hasText:'复制失败'}).waitFor();
   assert(await code.evaluate(el=>document.activeElement===el&&el.selectionStart===0&&el.selectionEnd===el.value.length));
   await page.evaluate(()=>window.__denyCopy=false);
   const pending=page.waitForEvent('download');await dialog.getByRole('button',{name:'下载'+title,exact:true}).click();const download=await pending;
   assert.equal(download.suggestedFilename(),filename);const file=path.join(artifacts,role+'-'+filename);await download.saveAs(file);assert.deepEqual(JSON.parse(fs.readFileSync(file,'utf8')),JSON.parse(text));
  }
  await dialog.getByRole('button',{name:'关闭帮助',exact:true}).focus();await page.keyboard.press('Tab');assert(await dialog.getByRole('button',{name:'关闭话术模板库帮助',exact:true}).evaluate(el=>el===document.activeElement),'Tab cycles inside dialog');
  if(mobile){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'no page overflow');const table=dialog.locator('.template-help-table').first();assert(await table.evaluate(el=>el.scrollWidth>el.clientWidth),'tables scroll within mobile dialog');}
  await page.screenshot({path:path.join(artifacts,role+(mobile?'-mobile':'-desktop')+'.png'),fullPage:true});
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert(await opener.evaluate(el=>el===document.activeElement),'focus returns to Help');
 }
 await help('admin');
 for(const [name,role] of [['alice','annotator'],['reader','viewer']]){
  await page.evaluate(async name=>{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,password:'fixture'})});if(!response.ok)throw Error('login failed');},name);
  await page.reload();await page.getByRole('button',{name:'模板库',exact:true}).click();if(role==='viewer')await page.setViewportSize({width:390,height:844});await help(role,role==='viewer');
 }
 const after=await page.evaluate(async()=>await(await fetch('/api/templates')).json());assert.equal(after.revision,initial.revision,'help cannot change library');assert.deepEqual(errors,[]);
 console.log(JSON.stringify({ok:true,artifacts,scenarios:['all roles','canonical contract tables','plain protocol code','exact source JSON','copy both examples','clipboard fallback selects all','download both examples','relative links','focus trap and return','desktop and mobile','no library mutation'],errors}));
})().catch(async error=>{console.error(error);if(page){fs.writeFileSync(path.join(artifacts,'failure.html'),await page.content());await page.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true});}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();fixture.kill();});
