"""Fail-closed parsing and remote hostname tests for the Baby Vision gateway client."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from uuid import uuid4

MODULE = Path(__file__).resolve().parents[1] / 'agents' / 'herbie_gateway_client.py'
spec = importlib.util.spec_from_file_location('gateway_client_hardening', MODULE)
clientmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clientmod)
TOKEN = 'q' * 48
MODEL = 'gemma3:1b'


class GatewayClientHardeningTests(unittest.TestCase):
    def test_tailnet_url_rejects_empty_or_malformed_labels(self):
        for host in ('https://.ts.net', 'https://host..ts.net',
                     'https://-host.tailnet.ts.net', 'https://host.-bad.ts.net',
                     'https://host.tailnet.ts.net.evil.invalid'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                clientmod.validate_gateway_url(host)
        self.assertEqual(clientmod.validate_gateway_url('https://herbie.my-tailnet.ts.net'),
                         'https://herbie.my-tailnet.ts.net')

    def test_boolean_schema_version_is_not_accepted_as_integer_one(self):
        class Reply(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                body = json.dumps({'schema_version': True,
                                   'request_id': request['request_id'],
                                   'model': request['model'], 'reply': 'untrusted response'}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Reply)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = clientmod.HerbieGatewayClient(f'http://127.0.0.1:{server.server_port}', TOKEN, MODEL)
            with self.assertRaises(clientmod.GatewayError):
                client.infer('testing', 'harmless fixture', str(uuid4()))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
