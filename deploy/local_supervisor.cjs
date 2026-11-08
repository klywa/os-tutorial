/* Project-local durable supervisor. No service installation or login hooks. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');

class Backoff {
  constructor() { this.failures = 0; }
  failure() { return [1000,5000,15000,60000][Math.min(this.failures++,3)]; }
  stable(milliseconds) { if (milliseconds >= 60000) this.failures = 0; }
}
const normal = p => process.platform === 'win32' ? path.resolve(p).toLowerCase() : path.resolve(p);
const now = () => new Date().toISOString();
function writeSnapshot(filename,value) {
  const temporary=`${filename}.tmp`;
  fs.writeFileSync(temporary,JSON.stringify(value,null,2),{mode:0o600});
  for(let attempt=0;;attempt++) {
    try{fs.renameSync(temporary,filename);return;}
    catch(error){
      if(!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt>=7)throw error;
      // Windows readers/scanners may briefly hold a non-delete-sharing handle.
      // Bound the wait; exhausted durable writes must reject control requests.
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,20);
    }
  }
}
function jsonRequest(port, pathname, method='GET', headers={}) {
  return new Promise((resolve,reject) => {
    const request=http.request({host:'127.0.0.1',port,path:pathname,method,headers,timeout:2000},response => {
      let body='';response.on('data',chunk => {body+=chunk; if(body.length>1024*1024) request.destroy(new Error('oversize response'));});
      response.on('end',() => {
        if(response.statusCode<200 || response.statusCode>=300) return reject(new Error(`HTTP ${response.statusCode}`));
        try {resolve(body ? JSON.parse(body) : {});} catch {reject(new Error('invalid identity'));}
      });
    });
    request.on('timeout',()=>request.destroy(new Error('request timeout')));
    request.on('error',reject);request.end(method==='POST'?'{}':undefined);
  });
}
function occupied(port) {
  return new Promise(resolve=>{
    const socket=net.connect({host:'127.0.0.1',port});let done=false;
    const finish=value=>{if(done)return;done=true;socket.destroy();resolve(value);};
    socket.setTimeout(500);socket.on('connect',()=>finish(true));socket.on('error',()=>finish(false));socket.on('timeout',()=>finish(true));
  });
}
async function main(configPath) {
  const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
  const root=path.resolve(config.root), directory=path.join(root,'raw','local-services');
  fs.mkdirSync(directory,{recursive:true});
  const lock=path.join(directory,'manager.lock');
  try {fs.mkdirSync(lock);} catch(error) {
    let pid;try{pid=JSON.parse(fs.readFileSync(path.join(lock,'owner.json'),'utf8')).pid;}catch{}
    if(!Number.isInteger(pid)) throw new Error('manager startup lock requires manual inspection');
    try{process.kill(pid,0);throw new Error('manager already exists or owner PID has been reused');}
    catch(e){if(e.code!=='ESRCH')throw e;}
    fs.rmSync(lock,{recursive:true});fs.mkdirSync(lock);
  }
  fs.writeFileSync(path.join(lock,'owner.json'),JSON.stringify({pid:process.pid,root,started_at:now()}));
  const token=crypto.randomBytes(32).toString('hex'), instance=crypto.randomUUID();
  const log=message=>fs.appendFileSync(path.join(directory,'manager.log'),`${now()} ${message}\n`);
  const services={};
  for(const [name,c] of Object.entries(config.services)) {
    services[name]={config:c,child:null,retry:new Backoff(),data:{name,port:c.port,desired:'paused',state:'paused',
      reason:'initial',pid:null,instance_id:null,ownership:null,start_time:null,exit_time:null,exit_code:null,
      exit_code_hex:null,exit_signal:null,restart_count:0,retry_delay_ms:0,next_restart_at:null,
      stdout_log:path.join(directory,`${name}.stdout.log`),stderr_log:path.join(directory,`${name}.stderr.log`)}};
  }
  const started=now();let closing=false;
  const snapshot=()=>({available:true,mode:'local',root,pid:process.pid,instance_id:instance,started_at:started,
    services:Object.fromEntries(Object.entries(services).map(([name,s])=>[name,{...s.data}]))});
  const save=()=>writeSnapshot(path.join(directory,'status.json'),snapshot());
  const identity=async s=>{
    const identity=await jsonRequest(s.config.port,s.config.identity_path);
    if(typeof identity.root!=='string'||normal(identity.root)!==normal(s.config.root)||
      identity.mode!=='local'||identity.port!==s.config.port) throw new Error('foreign service identity');
    if(s.data.instance_id&&identity.instance_id&&identity.instance_id!==s.data.instance_id) throw new Error('service instance changed');
    return identity;
  };
  function failed(s,code,signal,observed=false) {
    s.child=null;s.stopRequested=false;s.stopSent=false;s.data.exit_time=now();s.data.exit_code=observed?null:code;
    s.data.exit_code_hex=Number.isInteger(code)&&!observed?`0x${(code>>>0).toString(16).padStart(8,'0')}`:null;
    s.data.exit_signal=signal||null;s.data.pid=null;s.data.instance_id=null;
    s.retry.stable(Date.now()-(s.since||Date.now()));
    if(s.data.desired==='running'&&!closing){s.data.retry_delay_ms=s.retry.failure();s.due=Date.now()+s.data.retry_delay_ms;
      s.data.next_restart_at=new Date(s.due).toISOString();s.data.state='backoff';}
    else {s.data.state='paused';s.due=0;s.data.next_restart_at=null;}
    log(`${s.data.name} exited ownership=${observed?'observed':'managed'} code=${s.data.exit_code} hex=${s.data.exit_code_hex} signal=${signal||'none'} desired=${s.data.desired}`);save();
  }
  async function tickService(s) {
    if(s.child) {
      if(s.data.state==='starting'||s.stopRequested)try {
        const id=await identity(s);s.data.instance_id=id.instance_id||null;
        if(s.stopRequested&&!s.stopSent){await stopService(s);s.stopSent=true;}
        else if(!s.stopRequested)s.data.state='running';
      }catch{}
      if(s.data.state==='running')s.retry.stable(Date.now()-s.since);return;
    }
    if(s.data.desired!=='running') {
      if(s.data.state==='stopping'&&!(await occupied(s.config.port))){
        if(s.data.ownership==='observed')failed(s,null,null,true);
        else s.data.state='paused';
      }return;
    }
    if(s.due&&Date.now()<s.due)return;
    if(await occupied(s.config.port)) {
      try {
        const id=await identity(s);
        if(s.data.ownership!=='observed')log(`${s.data.name} adopted existing listener (exit code unavailable)`);
        s.data.state='running';s.data.ownership='observed';s.data.pid=id.pid||null;s.data.instance_id=id.instance_id||null;
        s.since=s.since||Date.now();s.retry.stable(Date.now()-s.since);delete s.data.error;
      }catch(error){s.data.state='foreign';s.data.error=error.message;s.data.pid=null;}
      return;
    }
    if(s.data.state==='running'&&s.data.ownership==='observed'){failed(s,null,null,true);return;}
    const out=fs.openSync(s.data.stdout_log,'a'),err=fs.openSync(s.data.stderr_log,'a');
    try {
      const child=spawn(s.config.command[0],s.config.command.slice(1),{cwd:s.config.cwd,
        env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',WXQ_SUPERVISOR_INSTANCE:instance},
        windowsHide:true,stdio:['ignore',out,err]});
      s.child=child;s.stopRequested=false;s.stopSent=false;s.since=Date.now();s.due=0;
      if(s.data.start_time)s.data.restart_count++;
      Object.assign(s.data,{state:'starting',ownership:'managed',pid:child.pid||null,start_time:now(),instance_id:null,next_restart_at:null});
      delete s.data.error;
      child.once('error',error=>{s.data.error=error.message;log(`${s.data.name} spawn error ${error.message}`);});
      child.once('close',(code,signal)=>failed(s,code,signal));
      log(`${s.data.name} started pid=${child.pid}`);
    }finally{fs.closeSync(out);fs.closeSync(err);}
  }
  async function stopService(s) {
    await identity(s);s.data.state='stopping';
    await jsonRequest(s.config.port,s.config.stop_path,'POST',{'Content-Type':'application/json','Origin':`http://127.0.0.1:${s.config.port}`,'X-WXQ-Supervisor':instance});
  }
  async function pause(names,reason,stop) {
    for(const name of names)if(!services[name])throw new Error('unknown service');
    for(const name of names){const s=services[name];s.data.desired='paused';s.data.reason=reason;s.due=0;s.data.next_restart_at=null;}
    save(); // Durable intent precedes any stop request or child exit event.
    if(stop)for(const name of names){const s=services[name];
      s.stopRequested=true;
      if(!(await occupied(s.config.port))){s.data.state=s.child?'stopping':'paused';continue;}
      try {await stopService(s);s.stopSent=true;}catch(error){s.data.error=error.message;
        s.data.state=/identity|instance/.test(error.message)?'foreign':'stopping';
        log(`${name} stop request failed: ${error.message}`);}
    }
  }
  let queue=Promise.resolve();
  function serialized(operation){const promise=queue.then(operation);queue=promise.catch(error=>log(`operation failed: ${error.message}`));return promise;}
  const server=http.createServer((request,response)=>{
    if(request.headers.authorization!==`Bearer ${token}`||request.headers.origin||request.headers.host!==`127.0.0.1:${server.address().port}`){response.writeHead(403);response.end();return;}
    let body='';request.on('data',chunk=>{body+=chunk;if(body.length>16384)request.destroy();});
    request.on('end',()=>serialized(async()=>{
      const data=body?JSON.parse(body):{};
      if(request.url==='/status'&&request.method==='GET'){}
      else if(request.method==='POST'&&request.url==='/pause')await pause(data.services||['backend'],data.reason||'explicit_stop',!!data.stop);
      else if(request.method==='POST'&&request.url==='/resume'){
        for(const name of data.services||Object.keys(services)){const s=services[name];if(!s)throw new Error('unknown service');
          s.data.desired='running';s.data.reason=null;s.due=0;s.data.next_restart_at=null;}
      }else if(request.method==='POST'&&request.url==='/shutdown'){
        closing=true;await pause(Object.keys(services),'manager_shutdown',true);
        // Wait for safe shutdown; never force-kill a service or an active job.
        const finish=async()=>{
          if(Object.values(services).some(s=>s.child)||(await Promise.all(Object.values(services).map(s=>occupied(s.config.port)))).some(Boolean))return setTimeout(finish,200);
          clearInterval(timer);server.close(()=>{fs.rmSync(lock,{recursive:true});fs.rmSync(path.join(directory,'control.json'),{force:true});process.exit(0);});
        };setTimeout(finish,100);
      }else throw new Error('unsupported operation');
      save();response.setHeader('Content-Type','application/json');response.end(JSON.stringify(snapshot()));
    }).catch(error=>{response.writeHead(409,{'Content-Type':'application/json'});response.end(JSON.stringify({error:error.message}));}));
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const control={root,pid:process.pid,instance_id:instance,port:server.address().port,token};
  writeSnapshot(path.join(directory,'control.json'),control);
  save();log(`manager started pid=${process.pid}`);
  let tickPending=false;
  const timer=setInterval(()=>{
    if(tickPending)return;tickPending=true;
    serialized(async()=>{
      for(const service of Object.values(services)){
        if(!service.child&&service.stopRequested&&!service.stopSent&&await occupied(service.config.port)){
          try{await stopService(service);service.stopSent=true;}catch(error){service.data.error=error.message;}
        }
        await tickService(service);
      }
      save();
    }).finally(()=>{tickPending=false;});
  },300);
  process.on('uncaughtException',error=>{log(`fatal ${error.stack}`);process.exit(1);});
  process.on('unhandledRejection',error=>log(`rejection ${error.stack||error}`));
}
module.exports={Backoff,writeSnapshot};
if(require.main===module)main(process.argv[2]).catch(error=>{process.stderr.write(`${error.stack}\n`);process.exit(1);});
