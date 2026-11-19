// Exercise real API writes against the disposable library, pausing only A's request.
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const readline=require('node:readline');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||
  'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function main(){
 const root=path.resolve(__dirname,'..');
 const fixture=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_templates_fixture.py','--collaboration'],
  {cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'},stdio:['ignore','pipe','inherit']});
 const output=readline.createInterface({input:fixture.stdout});
 let browser;
 try{
  const info=await Promise.race([once(output,'line').then(([line])=>JSON.parse(line)),once(fixture,'exit').then(([code])=>{throw Error('fixture exit '+code);})]);
  const base='http://127.0.0.1:'+info.port;
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||
   'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
  const page=await browser.newPage();
  await page.goto(base+'/admin');
  await page.getByLabel('用户名',{exact:true}).fill('reviewer');
  await page.getByLabel('密码',{exact:true}).fill('fixture');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.getByRole('button',{name:'模板库',exact:true}).click();
  for(const [gid,key,id] of [['forge','arg3','card:643402'],['equip','arg2','card:643303'],['talent','arg2','card:646017']]){
   const image=page.locator('[data-feedback-group="'+gid+'"] .template-action-parameters div').filter({has:page.getByText(key,{exact:true})}).locator('img');
   await image.waitFor();
   await image.evaluate(img=>img.decode());
   assert((await image.evaluate(img=>img.naturalWidth))>0);
   assert(decodeURIComponent(await image.getAttribute('src')).includes('/'+id+'/images/'));
  }
  const a=page.locator('[data-feedback-group="forge"]'), b=page.locator('[data-feedback-group="equip"]');
  const groupButton=b.locator('.template-card-actions button').filter({hasText:'组批注'});
  const lineButton=b.getByRole('button',{name:'批注话术1'});
  await lineButton.click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('话术批注',{exact:true}).fill('初稿');
  await dialog.getByRole('button',{name:'发布批注'}).click();
  await dialog.getByLabel('回复批注').fill('补充');
  await dialog.getByRole('button',{name:'发送回复'}).click();
  await dialog.getByRole('button',{name:'编辑我的批注'}).nth(1).click();
  await dialog.getByLabel('修改批注内容').fill('已修订的补充');
  await dialog.getByRole('button',{name:'保存批注修改'}).click();
  await dialog.getByText('修改历史（1）').click();
  assert(await dialog.getByText('补充',{exact:false}).count()>=2);
  await dialog.getByRole('button',{name:'关闭批注',exact:true}).click();
  await dialog.getByText('没有符合条件的批注。').waitFor();
  await dialog.getByRole('button',{name:/关闭.*批注与记录/}).click();
  assert.equal(await lineButton.locator('span').textContent(),'1');
  assert.equal(await groupButton.locator('span').textContent(),'0');
  await groupButton.click();
  await dialog.getByLabel('批注状态').selectOption('all');
  await dialog.getByText('没有符合条件的批注。').waitFor();
  await dialog.getByLabel('模板组批注').fill('整组建议');
  await dialog.getByRole('button',{name:'发布批注'}).click();
  await dialog.getByRole('button',{name:'编辑我的批注'}).waitFor();
  await dialog.getByRole('button',{name:/关闭.*批注与记录/}).click();
  assert.equal(await groupButton.locator('span').textContent(),'1');
  for(const outcome of ['success','failure','conflict']){
   let release,started;
   const gate=new Promise(resolve=>{release=resolve;});
   const waiting=new Promise(resolve=>{started=resolve;});
   const endpoint=base+'/api/templates/changes';
   await page.route(endpoint,async route=>{
    if(route.request().postDataJSON().changes[0].id!=='forge')return route.continue();
    started();
    await gate;
    if(outcome==='failure')return route.fulfill({status:503,json:{error:'模拟保存失败'}});
    return route.continue();
   });
   await a.locator('.template-card-actions').getByRole('button',{name:/^(取消)?忽略$/}).click();
   await waiting;
   await b.getByRole('button',{name:/编辑模板/}).click();
   const draft=dialog.getByLabel('说明与依据（可选）');
   await draft.fill('编辑 B：'+outcome);
   if(outcome==='conflict'){
    const state=await (await page.request.get(base+'/api/templates')).json();
    const unrelated=state.groups.find(g=>g.id==='talent');
    const response=await page.request.post(endpoint,{headers:{Origin:base},data:{revision:state.revision,
     changes:[{kind:'group',action:'put',id:unrelated.id,value:{...unrelated,priority:7}}]}});
    assert(response.ok(),await response.text());
   }
   release();
   if(outcome==='success')await a.getByText('已忽略',{exact:true}).waitFor();
   else await page.getByRole('alert').filter({hasText:'保存忽略状态失败'}).waitFor();
   assert.equal(await draft.inputValue(),'编辑 B：'+outcome);
   await dialog.getByRole('button',{name:'保存模板',exact:true}).click();
   await dialog.waitFor({state:'hidden'});
   const saved=await (await page.request.get(base+'/api/templates')).json();
   assert.equal(saved.groups.find(g=>g.id==='equip').explanation,'编辑 B：'+outcome);
   await page.unroute(endpoint);
  }
  console.log('Passed direct thread counts, own-message revisions, three typed image resources and independent group editing after success, failure and revision conflict.');
 }finally{
  if(browser)await browser.close();
  output.close();fixture.kill();
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
