// Read-only regression: delayed note loading must not discard an open help dialog.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 try{
  const page=await browser.newPage();let release;const gate=new Promise(resolve=>release=resolve);
  await page.addInitScript(()=>localStorage.setItem('wxq.preferences',JSON.stringify({view:'templates',selected:''})));
  await page.route('**/api/notes/catalog',async route=>{await gate;await route.continue();});
  await page.goto(process.env.HELP_TEST_ORIGIN||'http://127.0.0.1:8765/');
  await page.getByRole('button',{name:'帮助',exact:true}).click();
  const help=page.getByRole('dialog',{name:'话术模板库帮助',exact:true});await help.waitFor();
  await help.evaluate(el=>el.dataset.regressionMarker='keep-open');
  const detail=page.waitForResponse(response=>/\/api\/notes\/[^/]+(?:\?.*)?$/.test(response.url())&&!response.url().includes('/catalog'));
  const reading=page.waitForResponse(response=>/\/api\/notes\/[^/]+\/reading(?:\?.*)?$/.test(response.url()));
  release();await Promise.all([(await detail).finished(),(await reading).finished()]);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await help.count(),1,'background note resolution must keep the help dialog mounted');
  assert.equal(await help.getAttribute('data-regression-marker'),'keep-open','same dialog instance survives');
  await help.getByRole('button',{name:'下载完整示例',exact:true}).waitFor();
  console.log(JSON.stringify({ok:true,origin:page.url(),scenario:'delayed note resolution preserves open help'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
