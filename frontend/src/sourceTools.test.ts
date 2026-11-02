import {expect,it} from 'vitest';
import {buildSourcePrompt,keepSelection,copyOrFallback,DEFAULT_SOURCE_PROMPT_TEMPLATE,StagingWriteGate,newerBasket,removeSubmittedSelection,singleFlight} from './sourceTools';
it('prompt keeps every staged item with title, local path or URL and optional single-line notes',()=>{
 const value=buildSourcePrompt('李信牺牲流',[
  {id:'a',title:'教学甲',location:'D:\\raw\\one.md',notes:'  关注前期\n转阵  '},
  {id:'b',title:'教学乙',location:'https://example.com/video',notes:''},
  {id:'c',title:'',location:'https://example.com/other',notes:'  '},
 ]);
 expect(value).toContain('整理【李信牺牲流】');expect(value).toContain('若有冲突，则让用户裁决');
 expect(value).toContain('- 教学甲：D:\\raw\\one.md（关注前期 转阵）\n- 教学乙：https://example.com/video\n- c：https://example.com/other');
});
it('selection survives page slicing and drops only ignored or absent IDs',()=>{
 expect(keepSelection(['a','b','a'],[{id:'a'},{id:'b'},{id:'c',ignored:true}])).toEqual(['a','b']);
 expect(keepSelection(['a','c'],[{id:'a'},{id:'c',ignored:true}])).toEqual(['a']);
});

it('clipboard rejection preserves complete editable text for manual copying',async()=>{const text='自定义prompt\n- D:/raw/a.md';expect(await copyOrFallback(text,async()=>{throw new Error('denied');})).toBe(text);expect(await copyOrFallback(text,async()=>{})).toBe('');});

it('renders template tokens in one pass without interpreting inserted source or name tokens',()=>{
 const items=[{id:'a',title:'标题{阵容名}',location:'https://example.com/{内容列表}',notes:'备注{阵容名}'}];
 expect(buildSourcePrompt('名字{内容列表}',items,'{阵容名}\n{内容列表}\n{阵容名}')).toBe('名字{内容列表}\n- 标题{阵容名}：https://example.com/{内容列表}（备注{阵容名}）\n名字{内容列表}');
 expect(buildSourcePrompt('甲',[],DEFAULT_SOURCE_PROMPT_TEMPLATE)).toBe(buildSourcePrompt('甲',[]));
});
it('successful add clears only submitted IDs from current selection',()=>{
 expect(removeSubmittedSelection(['a','b','c'],['a','b'])).toEqual(['c']);
});
it('rejects old polling snapshots for the same project',()=>{
 const current={revision:4,project_key:'one'};
 expect(newerBasket(current,{revision:3,project_key:'one'})).toBe(current);
 expect(newerBasket(current,{revision:5,project_key:'one'}).revision).toBe(5);
 expect(newerBasket(current,{revision:1,project_key:'two'}).project_key).toBe('two');
});
it('dependent snapshots wait for add and do not run after failed add until retry succeeds',async()=>{
 const gate=new StagingWriteGate();let release!:()=>void,read=false;
 const adding=gate.run(()=>new Promise<void>(resolve=>release=resolve));
 const copying=gate.wait().then(()=>{read=true;});
 await Promise.resolve();expect(read).toBe(false);release();await adding;await copying;expect(read).toBe(true);
 await expect(gate.run(async()=>{throw Error('add failed');})).rejects.toThrow('add failed');
 await expect(gate.wait()).rejects.toThrow('add failed');
 await gate.run(async()=>{});await gate.wait();
});
it('rechecks a snapshot when another local mutation completes during its request',async()=>{
 const gate=new StagingWriteGate();let value=1,calls=0,release!:()=>void,started!:()=>void;
 const seen=new Promise<void>(resolve=>started=resolve);
 const reading=gate.read(async()=>{const captured=value;calls++;if(calls===1){started();await new Promise<void>(resolve=>release=resolve);}return captured;});
 await seen;await gate.run(async()=>{value=2;});release();
 expect(await reading).toBe(2);expect(calls).toBe(2);
});
it('shares an in-flight source load across initial loading and polling and retries after failure',async()=>{
 let calls=0,release!:(value:number)=>void;
 const load=singleFlight(()=>{calls++;return new Promise<number>(resolve=>release=resolve);});
 const first=load(),poll=load();expect(poll).toBe(first);expect(calls).toBe(1);
 release(826);expect(await poll).toBe(826);const next=load();expect(calls).toBe(2);release(827);expect(await next).toBe(827);
 let fail=true;const retry=singleFlight(async()=>{if(fail)throw Error('offline');return 1;});
 await expect(retry()).rejects.toThrow('offline');fail=false;expect(await retry()).toBe(1);
});
