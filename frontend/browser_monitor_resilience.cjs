/* Isolated browser fixture: no network acquisition and no existing queue writes. */
const {chromium}=require('C:/Users/klywa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {spawn,spawnSync}=require('child_process');
const path=require('path'),fs=require('fs'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'temp/monitor-browser');fs.mkdirSync(out,{recursive:true});
const child=spawn(path.join(root,'.wxq-runtime/Scripts/python.exe'),['-u','frontend/browser_proposal_fixture.py','--local'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:path.join(root,'temp'),TMP:path.join(root,'temp')}});
let browser,lastPage;
(async()=>{
 const fixture=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('fixture timeout '+text)),30000);child.stdout.on('data',data=>{text+=data;try{const value=JSON.parse(text.split('\n')[0]);clearTimeout(timer);resolve(value);}catch{}});child.stderr.on('data',data=>process.stderr.write(data));child.on('exit',code=>{if(code)reject(Error('fixture exit '+code));});});
 const base='http://127.0.0.1:'+fixture.port;
 const config={keywords:[],tags:[],strict_match:true,order:'totalrank',mode:'auto',scan_limit:100,process_limit:50};
 const retry={attempt:6,next_retry_at:'2099-11-02T10:30:00+08:00',category:'busy',error:'知识库正在保存，请稍后重试'};
 const creator={uid:'17214680',name:'奇妙',url:'https://space.bilibili.com/17214680',date_from:'2026-10-01',keywords:[],tags:[],enabled:true,job_id:'job1',monitor_state:'waiting',next_check:'2099-11-03T09:00:00+08:00',tag_progress:{pending:1},tag_retry:retry};
 const item={bvid:'BV1JQnz6YEf3',url:'https://www.bilibili.com/video/BV1JQnz6YEf3',title:'页面解析恢复验证',keywords:[],state:'queued',error:'Unable to extract initial state; see https://github.com/yt-dlp',error_info:{category:'extractor',phase:'downloading',recoverable:true,hint:'后台重试'},retry:{...retry,category:'extractor',error:'Unable to extract initial state'},progress:{phase:'retry_wait',next_retry_at:retry.next_retry_at,attempt:6}};
 let job={id:'job1',creator:creator.uid,state:'scanned',config,created:'2026-11-02T09:00:00+08:00',scanned:1,matched:1,duplicates:0,counts:{queued:1,running:0,failed:0,succeeded:0},items:[item]};
 browser=await chromium.launch({headless:true,executablePath:'C:/Users/klywa/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'});
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:1000}}),page=await context.newPage(),errors=[];
  let releaseJobs,releaseCreators,failCreators=false;
  const jobsGate=new Promise(resolve=>{releaseJobs=resolve;}),creatorsGate=new Promise(resolve=>{releaseCreators=resolve;});
  lastPage=page;
  page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.stack);});
  await page.route('**/api/crawler/**',async route=>{
   const request=route.request(),url=new URL(request.url());let value;
   if(url.pathname.endsWith('/settings'))value={clock:'09:00',cookies:'',parallelism:2,search:config};
   else if(url.pathname.endsWith('/jobs')){await jobsGate;value=[job];}
   else if(url.pathname.endsWith('/creators')||url.pathname.endsWith('/creators/resume')){await creatorsGate;if(failCreators){await route.fulfill({status:503,json:{error:'测试读取中断'}});return;}value=[creator];}
   else if(url.pathname.endsWith('/retry')){job={...job,items:[{...item,error:'',error_info:null,retry:null,progress:{phase:'queued'}}]};value=job;}
   else if(url.pathname.includes('/jobs/job1'))value=job;
   else value=[];
   await route.fulfill({json:value});
  });
  await page.goto(base);await page.locator('.json-entry').first().waitFor();await page.getByRole('button',{name:'爬取',exact:true}).click();
  await page.getByRole('tab',{name:'UP主监听',exact:true}).click();
  await page.getByRole('heading',{name:'UP主监听（加载中）',exact:true}).waitFor();
  assert.equal(await page.getByText('尚未添加UP主，点击上方按钮开始监听。',{exact:true}).count(),0);
  releaseCreators();
  await page.locator('.creator-entry').getByText('等待自动重试',{exact:false}).waitFor();
  await page.getByText('正在读取任务列表…',{exact:true}).waitFor();
  // The creator is already visible even while the jobs response is held.
  assert.equal(await page.locator('.creator-entry').count(),1);
  await page.screenshot({path:path.join(out,`creator-${width}.png`),fullPage:true});
  releaseJobs();
  await page.locator('.job-history-item > button').first().click();
  await page.locator('.crawl-result .retry-status').getByText('等待自动重试',{exact:false}).waitFor();
  await page.locator('.crawl-result summary').click();
  assert(await page.locator('.crawl-result pre').innerText().then(s=>s.includes('Unable to extract initial state')));
  await page.screenshot({path:path.join(out,`retry-${width}.png`),fullPage:true});
  await page.locator('.crawl-result').getByRole('button',{name:'立即重试此视频'}).click();
  await page.locator('.crawl-result .retry-status').waitFor({state:'detached'});
  failCreators=true;
  await page.getByText('UP主列表读取失败：',{exact:false}).waitFor();
  assert.equal(await page.locator('.creator-entry').count(),1);
  assert.equal(await page.getByText('尚未添加UP主，点击上方按钮开始监听。',{exact:true}).count(),0);
  failCreators=false;await page.getByRole('button',{name:'重新读取UP主列表',exact:true}).click();
  await page.getByRole('button',{name:'重新读取UP主列表',exact:true}).waitFor({state:'detached'});
  assert.deepEqual(errors,[]);
  console.log(`browser ${width}: independent creator loading, no false empty state, failure retention, retry details and manual retry state PASS`);
  // Restore a waiting fixture for the next viewport.
  job={...job,items:[item]};await page.goto('about:blank');await page.unrouteAll({behavior:'wait'});await context.close();
 }
})().catch(async e=>{if(lastPage){await lastPage.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});console.error((await lastPage.locator('body').innerText().catch(()=>'' )).slice(0,1200));}console.error(e);process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();
 if(child.exitCode===null)spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
});
