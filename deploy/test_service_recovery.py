"""Real HTTP processes exercise restart readiness, retries and Windows lifetime."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import local_sync as sync

sys.path.insert(0,str(sync.ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'))


FIXTURE = r'''
import argparse, json, os, socket, sys, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--root');p.add_argument('--port',type=int);a=p.parse_args()
root=Path(a.root);config=json.loads((root/'raw/config.json').read_text())
counter=root/'raw/attempts';n=int(counter.read_text())+1 if counter.exists() else 1;counter.write_text(str(n))
if n<=config.get('exit_attempts',0):sys.exit(17)
time.sleep(config.get('delay',0))
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/api/local-service/status':
   if not (root/'raw/first_status').exists():(root/'raw/first_status').write_text(str(time.monotonic()))
   body=json.dumps({'mode':'local','root':str(root),'port':a.port,'pid':os.getpid()}).encode();kind='application/json'
  elif self.path=='/':
   if n<=config.get('truncated_attempts',0):
    self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length','200');self.end_headers()
    self.wfile.write(b'<html>');self.wfile.flush();self.connection.shutdown(socket.SHUT_WR)
    threading.Timer(.1,lambda:os._exit(23)).start();return
   body=b'<html><script src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css"></html>';kind='text/html'
  elif self.path=='/assets/app.js':body=b'console.log("ready")';kind='text/javascript'
  elif self.path=='/assets/app.css':body=b'body{color:black}';kind='text/css'
  else:self.send_error(404);return
  if config.get('bad_asset') and self.path.startswith('/assets/'):
   body=b'<html>SPA fallback</html>';kind='text/html'
  if config.get('truncated_asset') and self.path=='/assets/app.js':
   self.send_response(200);self.send_header('Content-Type','text/javascript');self.send_header('Content-Length','200');self.end_headers()
   self.wfile.write(b'let a');self.wfile.flush();self.connection.shutdown(socket.SHUT_WR);return
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  self.send_response(202);self.send_header('Content-Length','0');self.end_headers()
  threading.Thread(target=server.shutdown,daemon=True).start()
server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
if n<=config.get('brief_attempts',0):
 threading.Timer(.7,lambda:os._exit(19)).start()
try:server.serve_forever()
finally:server.server_close()
'''


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        base=sync.ROOT/'temp';base.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)
        (self.root/'frontend').mkdir()
        (self.root/'frontend/server.py').write_text(FIXTURE,encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.service=sync.LocalService(self.root,self.port)
        self.service.start_timeout=6
        self.service.stable_time=1
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.stop)
        self.configure()

    def configure(self,**config):
        (self.root/'raw').mkdir(exist_ok=True)
        (self.root/'raw/config.json').write_text(json.dumps(config))

    def stop(self):
        try:
            if self.service.running():self.service.stop()
        except (RuntimeError,OSError):pass

    def attempts(self):return int((self.root/'raw/attempts').read_text())

    def test_success_requires_stable_http_and_assets(self):
        self.service.restart()
        self.assertGreaterEqual(time.monotonic()-float((self.root/'raw/first_status').read_text()),1)
        self.assertTrue(self.service.running())

    def test_immediate_exit_is_retried(self):
        self.configure(exit_attempts=2)
        self.service.restart()
        self.assertEqual(self.attempts(),3)
        self.assertTrue(self.service.running())

    def test_brief_readiness_then_exit_is_retried(self):
        self.configure(brief_attempts=1)
        self.service.restart()
        self.assertEqual(self.attempts(),2)
        self.assertTrue(self.service.running())

    def test_exit_mid_http_response_is_retried(self):
        self.configure(truncated_attempts=1)
        self.service.restart()
        self.assertEqual(self.attempts(),2)
        self.assertTrue(self.service.healthy())

    def test_slow_live_instance_is_not_duplicated(self):
        self.configure(delay=1.2)
        self.service.restart()
        self.assertEqual(self.attempts(),1)
        self.assertTrue(self.service.running())

    def test_dead_instances_exhaust_three_retries_with_exit_code_and_log(self):
        self.configure(exit_attempts=20)
        with self.assertRaisesRegex(RuntimeError,r'17.*日志'):
            self.service.restart()
        self.assertEqual(self.attempts(),4)
        self.assertFalse(self.service.occupied())

    def test_html_fallback_for_asset_never_reports_success_or_duplicates(self):
        self.configure(bad_asset=True);self.service.start_timeout=2
        with self.assertRaisesRegex(RuntimeError,'健康检查'):
            self.service.restart()
        self.assertEqual(self.attempts(),1)
        self.assertTrue(self.service.running())

    def test_truncated_asset_never_reports_success_or_duplicates(self):
        self.configure(truncated_asset=True);self.service.start_timeout=2
        with self.assertRaisesRegex(RuntimeError,'健康检查'):self.service.restart()
        self.assertEqual(self.attempts(),1)
        self.assertTrue(self.service.running())

    def test_existing_unhealthy_service_is_checked_without_duplicate(self):
        self.service.restart();self.service.start_timeout=2
        with patch.object(self.service,'healthy',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'健康检查'):self.service.restart()
        self.assertEqual(self.attempts(),1)

    def test_second_restart_after_timeout_reuses_alive_unbound_child(self):
        self.configure(delay=8);self.service.start_timeout=.4
        try:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'健康检查'):self.service.restart()
            self.assertEqual(self.attempts(),1,'timed-out live child was duplicated')
        finally:
            # Let the deliberately slow fixture bind so cleanup can stop it safely.
            time.sleep(8)

    @unittest.skipUnless(os.name=='nt','Windows Job Object lifetime')
    def test_server_survives_publisher_job_and_process_exit(self):
        # DETACHED_PROCESS detaches the console, but still inherits a Windows job.
        code=r'''
import ctypes, sys, os
from ctypes import wintypes as w
sys.path.insert(0,sys.argv[1]);from local_sync import LocalService
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE
k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
k.GetCurrentProcess.restype=w.HANDLE
class Basic(ctypes.Structure):
 _fields_=[('time1',ctypes.c_longlong),('time2',ctypes.c_longlong),('flags',w.DWORD),('min',ctypes.c_size_t),('max',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class Info(ctypes.Structure):
 _fields_=[('basic',Basic),('io',ctypes.c_ulonglong*6),('process_mem',ctypes.c_size_t),('job_mem',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
job=k.CreateJobObjectW(None,None);info=Info();info.basic.flags=0x2000|0x800
assert k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)),ctypes.get_last_error()
assert k.AssignProcessToJobObject(job,k.GetCurrentProcess()),ctypes.get_last_error()
s=LocalService(sys.argv[2],int(sys.argv[3]));s.stable_time=1;s.start_timeout=10;s.restart()
os._exit(0)
'''
        result=subprocess.run([sys.executable,'-c',code,str(sync.ROOT/'deploy'),str(self.root),str(self.port)],
                              capture_output=True,text=True,encoding='utf-8',timeout=25,env=sync.child_environment())
        self.assertEqual(result.returncode,0,result.stderr)
        time.sleep(.5)
        self.assertTrue(self.service.running(),'server died with publisher job despite DETACHED_PROCESS')

    @unittest.skipUnless(os.name=='nt','Windows publisher console lifetime')
    def test_server_survives_closing_publisher_console(self):
        import ctypes
        from ctypes import wintypes
        code=r'''
import ctypes,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from local_sync import LocalService
s=LocalService(sys.argv[2],int(sys.argv[3]));s.stable_time=1;s.start_timeout=10;s.restart()
k=ctypes.WinDLL('kernel32');k.GetConsoleWindow.restype=ctypes.c_void_p
Path(sys.argv[2],'raw/console.json').write_text(json.dumps({'hwnd':k.GetConsoleWindow(),'pid':os.getpid()}))
while True:time.sleep(.1)
'''
        startup=subprocess.STARTUPINFO()
        startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        publisher=subprocess.Popen([sys.executable,'-X','utf8','-c',code,str(sync.ROOT/'deploy'),str(self.root),str(self.port)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,startupinfo=startup,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def cleanup():
            if publisher.poll() is None:publisher.kill()
            publisher.wait(timeout=5)
        self.addCleanup(cleanup)
        ready=self.root/'raw/console.json'
        deadline=time.monotonic()+20
        while not ready.exists() and publisher.poll() is None and time.monotonic()<deadline:time.sleep(.1)
        self.assertTrue(ready.exists(),'publisher did not finish service recovery')
        window=json.loads(ready.read_text())['hwnd'];self.assertTrue(window)
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.assertTrue(user.PostMessageW(window,0x10,0,0))  # WM_CLOSE, as closing the terminal window.
        publisher.wait(timeout=10)
        self.assertTrue(self.service.healthy(),'server died when publisher console closed')


class RealPublishRecoveryTests(unittest.TestCase):
    """Real Git publish/pull plus a real HTTP process, with no external remote."""
    def setUp(self):
        import test_local_sync
        self.fixture=test_local_sync.LocalSyncTests()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        (self.root/'frontend/server.py').write_text(FIXTURE,encoding='utf-8')
        self.fixture.git(self.root,'add','frontend/server.py')
        self.fixture.git(self.root,'commit','-m','HTTP fixture')
        self.fixture.git(self.root,'push','origin','master')
        (self.root/'raw').mkdir();(self.root/'raw/config.json').write_text('{}')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.service=sync.LocalService(self.root,port)
        self.service.stable_time=.5;self.service.start_timeout=10
        self.addCleanup(self.stop)
        self.service.restart()
        self.manager=self.fixture.manager();self.manager.service=self.service

    def stop(self):
        if self.service.running():self.service.stop()

    def test_publish_success_restores_http_after_pushing_to_temporary_remote(self):
        (self.root/'frontend/feature.py').write_text('# publish fixture')
        self.assertEqual(self.manager.publish()['state'],'published')
        self.assertTrue(self.service.healthy())
        self.assertEqual(self.fixture.git(self.root,'rev-parse','HEAD'),
                         self.fixture.git(self.fixture.origin,'rev-parse','master'))

    def test_validation_failure_still_restores_http(self):
        (self.root/'knowledge/players/one.json').write_text('{"body":"invalid"}')
        with self.assertRaisesRegex(ValueError,'invalid formal index'):self.manager.publish()
        self.assertTrue(self.service.healthy())

    def test_push_failure_still_restores_http(self):
        hook=self.fixture.origin/'hooks/pre-receive'
        hook.write_bytes(b'#!/bin/sh\necho "fixture push rejected" >&2\nexit 1\n')
        hook.chmod(0o755)
        (self.root/'frontend/feature.py').write_text('# rejected publish')
        with self.assertRaisesRegex(RuntimeError,'fixture push rejected'):self.manager.publish()
        self.assertTrue(self.service.healthy())

    def test_pull_updates_and_restores_http(self):
        self.fixture.remote_note('online')
        self.assertEqual(self.manager.pull()['state'],'updated')
        self.assertTrue(self.service.healthy())


class RealApplicationTests(unittest.TestCase):
    def test_actual_application_survives_three_restart_cycles(self):
        fixture=RecoveryTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        root=fixture.root
        (root/'frontend/server.py').write_text(
            'import runpy\nrunpy.run_path('+repr(str(sync.ROOT/'frontend/server.py'))+',run_name="__main__")\n',
            encoding='utf-8')
        (root/'knowledge').mkdir()
        (root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
        # Exercise the real server lifecycle without scheduling external fetches.
        (root/'raw/official-sync').mkdir()
        (root/'raw/official-sync/state.json').write_text('{"enabled":false}')
        (root/'raw/lineup-usage').mkdir()
        (root/'raw/lineup-usage/state.json').write_text('{"state":"idle","retry_at":"2099-01-01T00:00:00+08:00"}')
        # The production topic worker intentionally outlives HTTP. Keep its
        # singleton lock for this empty fixture so it exits instead of leaking.
        from processing_lock import file_lock
        (root/'raw/crawler').mkdir()
        topic_lock=file_lock(root/'raw/crawler/topic-runtime.lock')
        topic_lock.__enter__();self.addCleanup(topic_lock.__exit__,None,None,None)
        service=fixture.service
        service.start_timeout=120;service.stable_time=5
        try:
            service.restart()
            for _ in range(3):
                service.stop();service.restart()
                self.assertTrue(service.healthy())
        except Exception as exc:
            logs='\n'.join(p.read_text(encoding='utf-8',errors='replace')[-4000:]
                           for p in (root/'raw/local-sync').glob('server*.log'))
            self.fail(f'{exc}\n{logs}')


if __name__=='__main__':unittest.main()
