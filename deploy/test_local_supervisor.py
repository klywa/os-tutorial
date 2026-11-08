"""Disposable real listeners: never touch the user's 8765/5173 services."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

FIXTURE='''import json,os,sys,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
root,port,kind=sys.argv[1],int(sys.argv[2]),sys.argv[3]
if kind=='slow':time.sleep(.8)
stops=0
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  data={'root':root,'port':port,'mode':'local','pid':os.getpid(),'instance_id':str(os.getpid())}
  body=json.dumps(data).encode();self.send_response(200);self.end_headers();self.wfile.write(body)
 def do_POST(self):
  global stops
  stops+=1
  if kind=='stop-retry' and stops==1:
   self.send_response(503);self.end_headers();return
  self.send_response(202);self.end_headers();threading.Thread(target=http.shutdown).start()
http=HTTPServer(('127.0.0.1',port),H)
if kind=='crash':threading.Timer(.7,lambda:os._exit(23)).start()
http.serve_forever();http.server_close()
'''

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'local_supervisor.py').is_file(),'supervisor controller required')
        import local_supervisor
        self.api=local_supervisor
        base=HERE.parent/'temp';base.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)
        self.fixture=self.root/'fixture.py';self.fixture.write_text(FIXTURE)
        self.config={'root':str(self.root),'services':{}}
        for name in ('backend','frontend'):
            p=port()
            self.config['services'][name]={'port':p,'root':str(self.root),'cwd':str(self.root),
                'identity_path':'/status','stop_path':'/stop','command':[sys.executable,str(self.fixture),str(self.root),str(p),'stable']}
        self.addCleanup(self.cleanup)
    def cleanup(self):
        try:self.api._request(self.root,'shutdown',{},timeout=10)
        except (OSError,RuntimeError):pass
        deadline=time.monotonic()+8
        while (self.root/'raw/local-services/control.json').exists() and time.monotonic()<deadline:time.sleep(.15)
        for process in self.api._launchers:
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        self.tmp.cleanup()
    def wait(self,predicate,timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=self.api.status(self.root)
            if predicate(value):return value
            time.sleep(.15)
        self.fail(f'timed out: {value}')
    def start(self):
        self.api._bootstrap(self.root,self.config)
        self.api.resume(self.root,('backend','frontend'))
        return self.wait(lambda s:all(x['state']=='running' for x in s['services'].values()))
    def test_launcher_exit_survival_idempotency_and_no_control_secret(self):
        configfile=self.root/'input.json';configfile.write_text(json.dumps(self.config))
        code="import sys,json;sys.path.insert(0,sys.argv[1]);import local_supervisor as s;s._bootstrap(sys.argv[2],json.load(open(sys.argv[3])));s.resume(sys.argv[2],('backend','frontend'))"
        subprocess.run([sys.executable,'-c',code,str(HERE),str(self.root),str(configfile)],check=True,timeout=20)
        first=self.wait(lambda s:all(x['state']=='running' for x in s['services'].values()))
        time.sleep(1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _:self.api._bootstrap(self.root,self.config),range(3)))
        second=self.api.status(self.root)
        self.assertEqual(first['pid'],second['pid'])
        self.assertEqual(first['services']['backend']['pid'],second['services']['backend']['pid'])
        self.assertNotIn('token',json.dumps(second))
        self.assertNotIn('token',(self.root/'raw/local-services/manager.log').read_text())
    def test_unexpected_exit_records_real_code_and_explicit_pause_prevents_restart(self):
        self.config['services']['backend']['command'][-1]='crash'
        self.api._bootstrap(self.root,self.config);self.api.resume(self.root,('backend',))
        result=self.wait(lambda s:s['services']['backend'].get('exit_code')==23)
        service=result['services']['backend']
        self.assertEqual(service['exit_code_hex'],'0x00000017')
        self.assertTrue(service['exit_time']);self.assertEqual(service['retry_delay_ms'],1000)
        self.api.pause(self.root,('backend',),reason='publish')
        time.sleep(1.4)
        paused=self.api.status(self.root)['services']['backend']
        self.assertEqual(paused['desired'],'paused');self.assertEqual(paused['restart_count'],0)
        self.config['services']['backend']['command'][-1]='stable'
        self.api.resume(self.root,('backend',))
        self.wait(lambda s:s['services']['backend']['restart_count']>=1)
    def test_foreign_port_is_preserved_and_wrong_root_manager_rejected(self):
        service=self.config['services']['backend']
        foreign=subprocess.Popen([sys.executable,str(self.fixture),str(self.root/'foreign'),str(service['port']),'stable'])
        self.addCleanup(lambda: self.finish_fixture(foreign))
        time.sleep(.4)
        self.api._bootstrap(self.root,self.config);self.api.resume(self.root,('backend',))
        state=self.wait(lambda s:s['services']['backend']['state']=='foreign')
        self.assertIsNone(state['services']['backend']['pid']);self.assertIsNone(foreign.poll())
    def test_adopts_existing_service_with_unknown_exit_code_then_publish_pause_resume(self):
        service=self.config['services']['backend']
        existing=subprocess.Popen(service['command'])
        self.addCleanup(lambda:self.finish_fixture(existing))
        time.sleep(.4)
        self.api._bootstrap(self.root,self.config);self.api.resume(self.root,('backend',))
        state=self.wait(lambda s:s['services']['backend']['state']=='running')['services']['backend']
        self.assertEqual(state['pid'],existing.pid);self.assertEqual(state['ownership'],'observed')
        self.assertIsNone(state['exit_code'])
        self.api._request(self.root,'pause',{'services':['backend'],'reason':'publish','stop':True})
        self.wait(lambda s:s['services']['backend']['state']=='paused')
        time.sleep(1.1);self.assertEqual(self.api.status(self.root)['services']['backend']['desired'],'paused')
        self.api.resume(self.root,('backend',));self.wait(lambda s:s['services']['backend']['state']=='running')

    def test_stop_during_startup_and_resume_during_shutdown_never_duplicate_listener(self):
        self.config['services']['backend']['command'][-1]='slow'
        self.api._bootstrap(self.root,self.config);self.api.resume(self.root,('backend',))
        first=self.wait(lambda s:s['services']['backend']['state']=='starting')['services']['backend']['pid']
        self.api._request(self.root,'pause',{'services':['backend'],'reason':'explicit_stop','stop':True})
        self.wait(lambda s:s['services']['backend']['state']=='paused')
        time.sleep(1.2)
        self.assertIsNone(self.api.status(self.root)['services']['backend']['pid'])
        self.api.resume(self.root,('backend',))
        next_state=self.wait(lambda s:s['services']['backend']['state']=='running')['services']['backend']
        self.assertNotEqual(first,next_state['pid'])
        self.api._request(self.root,'pause',{'services':['backend'],'reason':'publish','stop':True})
        self.api.resume(self.root,('backend',))
        final=self.wait(lambda s:s['services']['backend']['state']=='running' and s['services']['backend']['pid']!=next_state['pid'])
        self.assertEqual(final['services']['backend']['restart_count'],2)

    def test_transient_safe_stop_failure_retries_without_respawning(self):
        self.config['services']['backend']['command'][-1]='stop-retry'
        self.start()
        result=self.api.stop(self.root,('backend',),timeout=8)
        backend=result['services']['backend']
        self.assertEqual(backend['state'],'paused');self.assertIsNone(backend['pid'])
        self.assertEqual(backend['restart_count'],0)

    def test_dead_manager_snapshot_reports_unavailable_and_preserves_last_diagnostics(self):
        directory=self.root/'raw/local-services';directory.mkdir(parents=True)
        snapshot=directory/'status.json'
        snapshot.write_text(json.dumps({'available':True,'root':str(self.root),'pid':123,
            'services':{'backend':{'state':'running','pid':456,'exit_code':None}}}))
        self.assertTrue(self.api.stored_status(self.root)['available'])
        past=time.time()-30;os.utime(snapshot,(past,past))
        stale=self.api.stored_status(self.root)
        self.assertFalse(stale['available'])
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['services']['backend']['pid'],456)

    def test_concurrent_cold_bootstrap_creates_one_authenticated_manager(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.api._bootstrap(self.root,self.config),range(3)))
        self.assertEqual(len({result['pid'] for result in results}),1)
        control=json.loads((self.root/'raw/local-services/control.json').read_text())
        request=urllib.request.Request(f"http://127.0.0.1:{control['port']}/status",headers={'Authorization':'Bearer wrong'})
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request,timeout=3)
        self.assertEqual(failure.exception.code,403)
        failure.exception.close()
        self.assertNotIn(control['token'],json.dumps(results))

    def test_wrong_root_control_file_is_rejected_before_network_request(self):
        directory=self.root/'raw/local-services';directory.mkdir(parents=True)
        (directory/'control.json').write_text(json.dumps({'root':str(self.root/'foreign'),'port':1,'token':'private','pid':123}))
        with self.assertRaisesRegex(RuntimeError,'身份不匹配'):
            self.api.status(self.root)
        (directory/'control.json').unlink()

    def test_status_snapshot_recovers_transient_sharing_failure_and_reports_unavailable_if_locked(self):
        directory=self.root/'raw/local-services';directory.mkdir(parents=True)
        snapshot=directory/'status.json'
        body=json.dumps({'available':True,'root':str(self.root),'services':{'backend':{'state':'running'}}})
        snapshot.write_text(body)
        with patch.object(Path,'read_text',side_effect=[PermissionError('sharing violation'),body]):
            self.assertTrue(self.api.stored_status(self.root)['available'])
        with patch.object(Path,'read_text',side_effect=PermissionError('sharing violation')):
            state=self.api.stored_status(self.root)
        self.assertFalse(state['available'])
        self.assertEqual(state['snapshot_error'],'temporarily_unavailable')

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_real_windows_read_handle_allows_bounded_retry_then_atomic_replacement(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        filename=self.root/'locked-status.json';filename.write_text('{"desired":"running"}')
        # Permit reads/writes, but intentionally withhold FILE_SHARE_DELETE.
        handle=kernel.CreateFileW(str(filename),0x80000000,3,None,3,0,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
        script="process.stdout.write('writing\\n');require(process.argv[1]).writeSnapshot(process.argv[2],{desired:'paused'});"
        child=subprocess.Popen([shutil.which('node'),'-e',script,str(HERE/'local_supervisor.cjs'),str(filename)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'writing')
            time.sleep(.06)
        finally:kernel.CloseHandle(handle)
        stdout,stderr=child.communicate(timeout=5)
        self.assertEqual(child.returncode,0,stderr)
        self.assertEqual(json.loads(filename.read_text()),{'desired':'paused'})

    def finish_fixture(self,process):
        if process.poll() is None:process.terminate()
        process.wait(timeout=5)

if __name__=='__main__':unittest.main()
