const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const modulePath = path.join(__dirname, 'local_supervisor.cjs');
test('restart delays cap at 60 seconds and reset after stable runtime', () => {
  assert.ok(fs.existsSync(modulePath), 'durable supervisor implementation is required');
  const {Backoff} = require(modulePath);
  const retry = new Backoff();
  assert.deepEqual(Array.from({length: 6}, () => retry.failure(0)), [1000,5000,15000,60000,60000,60000]);
  retry.stable(59999); assert.equal(retry.failure(0),60000);
  retry.stable(60000); assert.equal(retry.failure(0),1000);
});
test('snapshot sharing violations retry without acknowledging an unwritten replacement', () => {
  const {writeSnapshot}=require(modulePath);
  assert.equal(typeof writeSnapshot,'function','durable snapshot writer required');
  const temporaryRoot=path.resolve(__dirname,'../temp');fs.mkdirSync(temporaryRoot,{recursive:true});
  const directory=fs.mkdtempSync(path.join(temporaryRoot,'wxq-supervisor-'));
  const destination=path.join(directory,'status.json');
  fs.writeFileSync(destination,'{"desired":"running"}');
  const rename=fs.renameSync;let blocked=2;
  try {
    fs.renameSync=(...args)=>{if(blocked-- > 0)throw Object.assign(new Error('sharing violation'),{code:'EPERM'});return rename(...args);};
    writeSnapshot(destination,{desired:'paused'});
    assert.deepEqual(JSON.parse(fs.readFileSync(destination,'utf8')),{desired:'paused'});
    fs.renameSync=()=>{throw Object.assign(new Error('sharing violation'),{code:'EPERM'});};
    assert.throws(()=>writeSnapshot(destination,{desired:'running'}),/sharing violation/);
    assert.deepEqual(JSON.parse(fs.readFileSync(destination,'utf8')),{desired:'paused'});
  }finally{fs.renameSync=rename;fs.rmSync(directory,{recursive:true,force:true});}
});
