// Run from the project root against both running local services:
// node frontend/browser_template_trace.cjs path/to/library.json
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function check(browser,base,files){
 const page=await browser.newPage({viewport:{width:1540,height:960}});
 page.setDefaultTimeout(12000);
 const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 try{
  await page.goto(base);
  const button=(name,scope=page)=>scope.getByRole('button',{name,exact:true});
  await button('模板库').click();
  await button('文件',page.getByRole('group',{name:'内容来源'})).click();
  // Chromium's native picker cannot be driven by Playwright. Supply read-only
  // file handles for the actual bytes, leaving the app's parsing and UI intact.
  async function choose(items){
   await page.evaluate(items=>{
    window.showOpenFilePicker=async()=>items.map(({name,raw})=>({name,getFile:async()=>new File([raw],name)}));
   },items);
   await button('打开模板文件').click();
   const cards=button('卡片',page.getByRole('group',{name:'模板显示方式'}));
   if(await cards.getAttribute('aria-pressed')!=='true')await cards.click();
  }
  await choose(files);
  const library=JSON.parse(files[0].raw),detail=JSON.parse(files[1].raw);
  const dialog=page.getByRole('dialog',{name:'话术溯源'});
  const select=dialog.getByLabel('选择话术');
  const labels={identify:'知识点识别',split:'分流',enrich:'知识补充',events:'事件框架生成',conditions:'条件生成',phrases:'话术生成',assemble:'汇总'};
  let sentenceCount=0,revisionCount=0;
  for(const group of library.groups){
   await page.getByLabel('搜索模板').fill(group.name);
   const card=page.locator('[data-feedback-group]').filter({visible:true}).and(page.locator('[data-feedback-group="'+group.id+'"]'));
   await button('溯源',card).click();
   for(const [id,sentence] of Object.entries(detail.groups[group.id].sentences)){
    await select.selectOption(id);
    const chain=dialog.getByRole('region',{name:'句级溯源'});
    await chain.getByText(id,{exact:true}).waitFor();
    const nodes=chain.locator(':scope > details');
    assert.deepEqual(await nodes.locator(':scope > summary').allTextContents(),sentence.node_ids.map(ref=>labels[detail.nodes[ref].stage]));
    for(const [index,nodeId] of sentence.node_ids.entries()){
     const record=detail.nodes[nodeId],node=nodes.nth(index);
     const version=sentence.node_versions?.[nodeId]??record.selected_version;
     const adopted=version===record.selected_version?record:[...record.attempts,...record.revisions].find(item=>item.id===version);
     await node.locator(':scope > summary').click();
     await node.getByText(nodeId+' · 实际采用版本 '+version,{exact:true}).waitFor();
     for(const [heading,expected] of [['实际输入',adopted.input],['采用的输出',adopted.output]]){
      const fold=node.locator(':scope > details').filter({has:page.getByText(heading,{exact:true})});
      await fold.locator('summary').click();
      await fold.locator('pre').waitFor();
      assert.equal(await fold.locator('pre').textContent(),typeof expected==='string'?expected:JSON.stringify(expected,null,2));
      await fold.locator('summary').click();
     }
     for(const call of record.attempts.filter(call=>call.prompt)){
      const attempt=node.locator(':scope > details').filter({has:page.getByText('调用 '+call.id+(call.id===version?' · 已采用':''),{exact:true})});
      await attempt.locator(':scope > summary').click();
      const prompt=attempt.locator('details').filter({has:page.getByText('实际发送的 prompt',{exact:true})});
      assert.equal(await prompt.getAttribute('open'),null);
      await prompt.locator('summary').click();
      await prompt.locator('pre').waitFor();
      assert.equal(await prompt.locator('pre').textContent(),typeof call.prompt==='string'?call.prompt:JSON.stringify(call.prompt,null,2));
      await attempt.locator(':scope > summary').click();
     }
     for(const revision of record.revisions){
      const label='人工修订 '+revision.id+(revision.id===version?' · 已采用':'');
      const fold=node.locator(':scope > details').filter({has:page.getByText(label,{exact:true})});
      await fold.locator('summary').click();
      await fold.locator('pre').waitFor();
      assert.deepEqual(JSON.parse(await fold.locator('pre').textContent()),revision);
      revisionCount++;
     }
     await node.locator(':scope > summary').click();
    }
    sentenceCount++;
   }
   await button('关闭话术溯源',dialog).click();
  }
  assert(sentenceCount>0);
  await button('关闭文件').click();
  await choose([files[0]]);
  await button('溯源',page.locator('[data-feedback-group]').first()).click();
  await dialog.getByText('无生成记录',{exact:true}).waitFor();
  const upload=dialog.locator('input[type=file]');
  await upload.setInputFiles({name:'其他库-detail.json',mimeType:'application/json',buffer:Buffer.from(files[1].raw)});
  await dialog.getByRole('alert').filter({hasText:files[1].name}).waitFor();
  await upload.setInputFiles({name:files[1].name,mimeType:'application/json',buffer:Buffer.from(files[1].raw)});
  await dialog.getByRole('region',{name:'句级溯源'}).waitFor();
  await button('关闭话术溯源',dialog).click();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({base,sentences:sentenceCount,revisions:revisionCount,legacy:true,manualAttachment:true}));
 }finally{await page.close();}
}

(async()=>{
 const input=process.argv[2];
 if(!input)throw Error('请提供生成的主库 JSON 路径。');
 const files=[input,input.replace(/\.json$/i,'-detail.json')].map(file=>({name:path.basename(file),raw:fs.readFileSync(file,'utf8')}));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 try{for(const base of (process.env.TRACE_BASES||'http://127.0.0.1:8765,http://127.0.0.1:5173').split(','))await check(browser,base,files);}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
