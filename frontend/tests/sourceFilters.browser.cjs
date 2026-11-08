// Run against the local service: NODE_PATH=<Playwright modules> node tests/sourceFilters.browser.cjs
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fixtures=Array.from({length:40},(_,i)=>({id:`search-test-${i}`,title:`搜索测试内容 ${i}`,url:'https://example.com/'+i,author:i===0?'Alpha万象棋':`测试UP主${String(i).padStart(2,'0')}${i===39?'很长的名称'.repeat(8):''}`,keywords:[i===0?'攻略关键词':'普通关键词'],batches:[i===0?'BatchABC':'BatchOther'],stage:i===0?'failed':'registered',knowledge_status:i===0?'submitted':'unprocessed',linked_notes:[]}));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000},hasTouch:true});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route(/\/api\/sources$/,route=>route.fulfill({json:fixtures}));
  await page.addInitScript(()=>localStorage.setItem('wxq.preferences',JSON.stringify({view:'sources'})));
  await page.goto(process.env.SOURCE_FILTERS_URL||'http://127.0.0.1:8765');
  await page.waitForLoadState('networkidle');
  const bar=page.getByRole('region',{name:'筛选外部内容'});
  const combo=label=>bar.getByRole('combobox',{name:label,exact:true});
  const count=number=>page.getByText(`${number} 条符合条件`,{exact:true}).waitFor();
  await count(40);
  assert.equal(await bar.getByRole('combobox').count(),5);
  // Typing filters candidates only; Chinese substring and case-insensitive matching.
  for(const [label,query,option] of [['关键词',' 攻略 ','攻略关键词'],['UP主',' alpha ','Alpha万象棋'],['批次',' abc ','BatchABC'],['处理状态','失败','失败'],['沉淀状态','待核对','已提交待核对']]){
   const field=combo(label);await field.click();await field.fill(query);
   await count(40);await bar.getByRole('option',{name:option,exact:true}).waitFor();
   await field.press('Enter');await count(1);assert.equal(await field.inputValue(),option);
   await bar.getByRole('button',{name:'重置',exact:true}).click();await count(40);
  }
  // Navigation, cancellation and no-match Enter preserve the selected filter.
  const author=combo('UP主');await author.click();await author.fill('Alpha');await author.press('Enter');await count(1);
  await author.click();await author.fill('没有此UP主');await bar.getByText('无匹配选项').waitFor();
  await author.press('Enter');await count(1);await author.press('Escape');assert.equal(await author.inputValue(),'Alpha万象棋');
  await author.click();await author.fill('测试');await bar.getByRole('button',{name:'重置',exact:true}).focus();
  assert.equal(await author.inputValue(),'Alpha万象棋');await count(1);
  await author.click();await author.fill('测试');await page.getByRole('heading',{name:'外部内容',exact:true}).click();
  assert.equal(await author.inputValue(),'Alpha万象棋');await count(1);
  // IME confirmation must not select; a subsequent deliberate Enter does.
  await author.click();await author.fill('测试UP主01');await author.dispatchEvent('compositionstart');
  await author.press('Enter');await count(1);assert.equal(await author.getAttribute('aria-expanded'),'true');
  await author.dispatchEvent('compositionend');await author.press('Enter');await count(1);assert.equal(await author.inputValue(),'测试UP主01');
  // The all option clears a filter; selecting resets checkbox selection.
  await page.getByRole('checkbox',{name:'全选本页',exact:true}).check();
  await author.click();await author.press('ArrowUp');await author.press('ArrowUp');await author.press('Enter');await count(40);
  assert.equal(await page.getByRole('checkbox',{name:'全选本页',exact:true}).isChecked(),false);
  await author.click();assert.equal(await author.inputValue(),'');
  const options=bar.getByRole('listbox',{name:'UP主选项'});
  const dimensions=await options.evaluate(el=>({client:el.clientHeight,scroll:el.scrollHeight}));assert.ok(dimensions.scroll>dimensions.client);
  await page.screenshot({path:path.resolve('../temp/source-filters-desktop.png'),animations:'disabled'});
  await author.press('Escape');
  // Tab focus also opens an empty search instead of editing the selected label.
  await combo('关键词').focus();assert.equal(await combo('关键词').getAttribute('aria-expanded'),'true');
  await combo('关键词').press('Escape');
  // Mobile dialog must keep its own Escape behavior and scrollable options.
  await page.setViewportSize({width:390,height:844});
  await bar.getByRole('button',{name:'筛选',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'更多筛选'});await dialog.waitFor();
  assert.equal(await dialog.getByRole('combobox').count(),5);
  const mobileAuthor=dialog.getByRole('combobox',{name:'UP主',exact:true});await mobileAuthor.click();
  await mobileAuthor.fill('测试UP主39');await page.screenshot({path:path.resolve('../temp/source-filters-mobile.png'),animations:'disabled'});
  await dialog.getByRole('option').tap();await count(1);
  await mobileAuthor.click();await mobileAuthor.press('Escape');assert.equal(await dialog.isVisible(),true);
  await dialog.getByRole('button',{name:'重置全部条件',exact:true}).click();await count(40);
  await dialog.getByRole('button',{name:'完成',exact:true}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);console.log('PASS: five filters, search/commit, cancel, keyboard, IME, selection reset, desktop/mobile');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
