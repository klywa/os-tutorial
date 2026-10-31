import {describe,it,expect,vi,afterEach} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DashboardView} from './Dashboard';
import {formatRate,sortNotes,startDashboardPolling,type DashboardData} from './dashboardModel';

const fields=['rhythm','heroes','auction','equipment','talents','counter','operations'];
function fixture():DashboardData{
 return {revision:'one',generated_at:'2026-10-29T00:00:00Z',counts:{player:20,lineup:2},summary:{covered:1,total:14,rate:1/14},
  fields:fields.map((id,i)=>({id,label:['运营节奏','英雄','拍卖','关键装备','推荐天赋','克制方法','关键操作'][i],covered:i===1?1:0,total:2,rate:i===1?.5:0})),
  notes:[{id:'yi',title:'乙阵容',covered:1,rate:1/7,fields:Object.fromEntries(fields.map(id=>[id,{covered:id==='heroes',section:id==='heroes'?'英雄':null,node_id:id==='heroes'?'hero-node':null}]))},
   {id:'jia',title:'甲阵容',covered:0,rate:0,fields:Object.fromEntries(fields.map(id=>[id,{covered:false,section:null,node_id:null}]))}]};
}
afterEach(()=>vi.useRealTimers());
describe('dashboard presentation',()=>{
 it('renders the Top10 scope with joint usage, source, player, missing and ambiguous states',()=>{
  const data=fixture();Object.assign(data,{scope:'usage_top10',usage:{ready:true,state:'idle',stale:true,scope:{version:'vtest'},ambiguous:1,selected_count:2,last_success:'2026-10-29T00:00:00Z'}});
  Object.assign(data.notes[0],{rank:1,usage:.24,player_name:'香香',source_name:'大河流域 · 公孙离 · 虞姬',match_status:'missing_note',local_name:'大河开团射'});
  Object.assign(data.notes[1],{rank:2,usage:.16,player_name:'嬴律',match_status:'ambiguous',rate:null,candidates:['候选甲','候选乙']});
  const html=renderToStaticMarkup(<DashboardView data={data} error="" busy={false} checkedAt="" order="usage" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}}/>);
  for(const text of ['使用率 Top-10','Top-10 已确认覆盖率','第1名','24.0%','大河流域','未建笔记','待确认','候选甲','更新使用率','09:00','最近7天'])expect(html).toContain(text);
  expect(html).toContain('管理匹配');expect(html).toContain('aria-label="指定乙阵容的知识库匹配"');expect(html).toContain('dashboard-table-usage');expect(html).not.toContain('dashboard-match-button');expect(html).not.toContain('dashboard-source-name');
  expect(html).not.toContain('打开乙阵容的英雄');
 });
 it.each([20,50] as const)('renders Top-%i with the same matching and sorting controls',limit=>{
  const data=fixture();Object.assign(data,{scope:`usage_top${limit}`,usage:{ready:true,state:'idle'}});
  Object.assign(data.notes[0],{rank:1,usage:.2,match_status:'matched',note_id:'yi'});
  const html=renderToStaticMarkup(<DashboardView data={data} error="" busy={false} checkedAt="" order="usage" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}}/>);
  expect(html).toContain(`Top-${limit} 已确认覆盖率`);expect(html).toContain(`Top-${limit} 阵容＋棋手覆盖明细`);
  expect(html).toContain('指定乙阵容的知识库匹配');expect(html).toContain('打开乙阵容的英雄');expect(html).toContain('登场率从高到低');
 });
 it('does not present a false zero ranking before the first usage snapshot',()=>{
  const data=fixture();data.notes=[];data.summary={covered:0,total:0,rate:null};Object.assign(data,{scope:'usage_top10',usage:{ready:false,state:'running'}});
  const html=renderToStaticMarkup(<DashboardView data={data} error="" busy={false} checkedAt="" order="usage" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}}/>);
  expect(html).toContain('使用率数据尚未就绪');expect(html).not.toContain('暂无阵容笔记');expect(html).not.toContain('0.0%');
 });
 it('sorts usage by source rank and places unconfirmed coverage after confirmed rows',()=>{
  const rows=fixture().notes;Object.assign(rows[0],{rank:2});Object.assign(rows[1],{rank:1});
  expect(sortNotes(rows,'usage').map(n=>n.id)).toEqual(['jia','yi']);
  Object.assign(rows[1],{rate:null});expect(sortNotes(rows,'asc').map(n=>n.id)).toEqual(['yi','jia']);
 });
 it('sorts by coverage in both directions with stable Chinese title ties',()=>{
  const notes=fixture().notes;
  expect(sortNotes(notes,'asc').map(n=>n.id)).toEqual(['jia','yi']);
  expect(sortNotes(notes,'desc').map(n=>n.id)).toEqual(['yi','jia']);
  const ties=notes.map(n=>({...n,covered:0,rate:0}));
  expect(sortNotes(ties,'desc').map(n=>n.title)).toEqual([...ties].map(n=>n.title).sort((a,b)=>a.localeCompare(b,'zh-CN')));
  expect(notes[0].id).toBe('yi');
 });
 it('renders counts, all seven dimensions and per-note coverage as readable text',()=>{
  const html=renderToStaticMarkup(<DashboardView data={fixture()} error="" busy={false} checkedAt="" order="asc" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}}/>);
  for(const text of ['棋手笔记','阵容笔记','整体覆盖率','7.1%','14.3%','50.0%','1 / 2','已覆盖','缺失','克制方法','关键操作','至少一条实质内容'])expect(html).toContain(text);
  expect(html.indexOf('甲阵容')).toBeLessThan(html.indexOf('乙阵容'));
  expect(html).toContain('打开乙阵容的英雄');
 });
 it('renders empty rates and retained snapshot together with a failure',()=>{
  expect(formatRate(null)).toBe('—');expect(formatRate(0)).toBe('0.0%');
  const data=fixture();data.notes=[];data.counts.lineup=0;data.summary={covered:0,total:0,rate:null};
  const html=renderToStaticMarkup(<DashboardView data={data} error="更新失败" busy={false} checkedAt="" order="asc" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}}/>);
  expect(html).toContain('暂无阵容笔记');expect(html).toContain('更新失败');expect(html).toContain('棋手笔记');
 });
});

describe('visible dashboard refresh lifecycle',()=>{
 function setup(read: (signal:AbortSignal)=>Promise<DashboardData> = async()=>fixture()){
  vi.useFakeTimers();
  const page=new EventTarget(),doc=new EventTarget();let visible=true;
  const onData=vi.fn(),onError=vi.fn(),onBusy=vi.fn();
  const load=vi.fn(read);
  const polling=startDashboardPolling({read:load,onData,onError,onBusy},{page,doc,isVisible:()=>visible});
  return {page,doc,load,polling,onData,onError,onBusy,hide:()=>{visible=false;doc.dispatchEvent(new Event('visibilitychange'));},show:()=>{visible=true;doc.dispatchEvent(new Event('visibilitychange'));}};
 }
 it('fetches on entry, every 3s, focus and save; pauses while hidden and disposes listeners',async()=>{
  const s=setup();await vi.advanceTimersByTimeAsync(0);expect(s.load).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(3000);expect(s.load).toHaveBeenCalledTimes(2);
  s.hide();await vi.advanceTimersByTimeAsync(9000);s.page.dispatchEvent(new Event('focus'));expect(s.load).toHaveBeenCalledTimes(2);
  s.show();await vi.advanceTimersByTimeAsync(0);expect(s.load).toHaveBeenCalledTimes(3);
  s.page.dispatchEvent(new Event('focus'));await vi.advanceTimersByTimeAsync(0);
  s.page.dispatchEvent(new Event('wxq:knowledge-saved'));await vi.advanceTimersByTimeAsync(0);
  expect(s.load).toHaveBeenCalledTimes(5);
  s.polling.stop();await vi.advanceTimersByTimeAsync(6000);s.page.dispatchEvent(new Event('focus'));expect(s.load).toHaveBeenCalledTimes(5);
 });
 it('retains data on error and allows manual retry',async()=>{
  let fail=false;const s=setup(async()=>{if(fail)throw new Error('断开');return fixture();});
  await vi.advanceTimersByTimeAsync(0);fail=true;await vi.advanceTimersByTimeAsync(3000);
  expect(s.onData).toHaveBeenCalledTimes(1);expect(s.onError).toHaveBeenLastCalledWith('断开');
  fail=false;s.polling.refresh();await vi.advanceTimersByTimeAsync(0);expect(s.onData).toHaveBeenCalledTimes(2);expect(s.onError).toHaveBeenLastCalledWith('');s.polling.stop();
 });
 it('coalesces overlapping refreshes and ignores completion after unmount',async()=>{
  let resolve!:(value:DashboardData)=>void;const s=setup(()=>new Promise(r=>{resolve=r;}));
  await vi.advanceTimersByTimeAsync(6000);s.polling.refresh();expect(s.load).toHaveBeenCalledTimes(1);
  s.polling.stop();resolve(fixture());await vi.advanceTimersByTimeAsync(0);expect(s.onData).not.toHaveBeenCalled();
  expect(s.load.mock.calls[0][0].aborted).toBe(true);
 });
});

it('hides all public usage refresh and guest match controls',()=>{
 const data=fixture();Object.assign(data,{scope:'usage_top10',usage:{ready:true,state:'idle'}});
 const html=renderToStaticMarkup(<DashboardView data={data} error="" busy={false} checkedAt="" order="usage" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}} publicMode canManageMatches={false}/>);
 expect(html).not.toContain('更新使用率');expect(html).not.toContain('管理匹配');expect(html).not.toContain('指定乙阵容');expect(html).toContain('每小时');
});

it('allows public administrators to match without requesting usage refresh',()=>{
 const data=fixture();Object.assign(data,{scope:'usage_top10',usage:{ready:true,state:'idle'}});
 const html=renderToStaticMarkup(<DashboardView data={data} error="" busy={false} checkedAt="" order="usage" onOrder={()=>{}} onRefresh={()=>{}} onOpen={()=>{}} publicMode canManageMatches/>);
 expect(html).toContain('管理匹配');expect(html).toContain('指定乙阵容');expect(html).not.toContain('更新使用率');
});
