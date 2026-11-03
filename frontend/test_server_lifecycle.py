"""Server exits must leave useful diagnostics and close background workers."""
import logging
import http.client
from http.server import BaseHTTPRequestHandler
import os
import socket
import sys
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
