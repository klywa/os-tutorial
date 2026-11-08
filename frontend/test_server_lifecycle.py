"""Server exits must leave useful diagnostics and close background workers."""
import logging
import http.client
from http.server import BaseHTTPRequestHandler
import os
import socket
import sys
import json
from pathlib import Path
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import server


class LifecycleTests(unittest.TestCase):
    def run_server(self,error=None):
        closed=[]
        def serve():
            if error:raise error
        http=SimpleNamespace(serve_forever=serve,server_close=lambda:closed.append(True))
        with patch.object(sys,'argv',['server.py']),patch.object(server.workspace,'migrate'), \
                patch('player_identity.migrate'),patch.object(server,'create_server',return_value=http):
            with self.assertLogs('local-server',level=logging.INFO) as logs:
                code=server.main()
        self.assertEqual(closed,[True])
        return code,'\n'.join(logs.output)

    def test_normal_shutdown_records_process_and_exit(self):
        code,logs=self.run_server()
        self.assertEqual(code,0)
        self.assertIn('pid=',logs)
        self.assertIn('exit_code=0',logs)

    def test_uncaught_exception_records_traceback_and_closes_workers(self):
        code,logs=self.run_server(RuntimeError('runtime fixture crash'))
        self.assertEqual(code,1)
        self.assertIn('runtime fixture crash',logs)
        self.assertIn('Traceback',logs)
        self.assertIn('exit_code=1',logs)

    def test_keyboard_interrupt_is_logged_and_closes_workers(self):
        code,logs=self.run_server(KeyboardInterrupt())
        self.assertEqual(code,130)
        self.assertIn('exit_code=130',logs)


class LocalControlTests(unittest.TestCase):
    def test_direct_stop_persists_pause_before_acknowledging_safe_shutdown(self):
        events=[]
        module=SimpleNamespace(notify_stop=lambda root,**kwargs:events.append(('paused',kwargs)))
        listener=server.LocalServer(('127.0.0.1',0),server.Handler)
        listener.root=Path(__file__).parent/'isolated-control-fixture'
        thread=threading.Thread(target=listener.serve_forever,daemon=True)
        try:
            with patch('site_access.actor',return_value={'role':'admin'}),patch.object(server,'local_supervisor_module',return_value=module):
                thread.start()
                connection=http.client.HTTPConnection('127.0.0.1',listener.server_port,timeout=3)
                connection.request('POST','/api/local-service/stop',body='{}',headers={'Content-Type':'application/json'})
                response=connection.getresponse();self.assertEqual(response.status,202)
                self.assertTrue(json.loads(response.read())['ok']);connection.close()
                self.assertEqual(events,[('paused',{'supervisor_instance':None})])
                thread.join(timeout=3);self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():listener.shutdown()
            listener.server_close()

    def test_public_server_never_loads_local_supervisor(self):
        self.assertIsNone(server.local_supervisor_module(SimpleNamespace(public_origin='https://example.test')))


@unittest.skipUnless(os.name=='nt','Windows local listener binding')
class WindowsBindingTests(unittest.TestCase):
    def test_local_listener_rebinds_after_health_connection_and_remains_exclusive(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'ok')
        port=0
        for _ in range(3):
            listener=server.LocalServer(('127.0.0.1',port),Handler)
            port=listener.server_port
            try:
                with socket.socket() as duplicate:
                    duplicate.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    with self.assertRaises(OSError):duplicate.bind(('127.0.0.1',port))
                thread=threading.Thread(target=listener.serve_forever,daemon=True);thread.start()
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                connection.request('GET','/')
                self.assertEqual(connection.getresponse().read(),b'ok');connection.close()
            finally:
                listener.shutdown();listener.server_close()
            thread.join(timeout=3)


if __name__=='__main__':unittest.main()
