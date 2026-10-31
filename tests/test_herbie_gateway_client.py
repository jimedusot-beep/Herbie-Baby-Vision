"""Contract-only tests; no real H.E.R.B.I.E. service or remote access required."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from uuid import uuid4


MODULE = Path(__file__).resolve().parents[1] / 'agents' / 'herbie_gateway_client.py'
spec = importlib.util.spec_from_file_location('herbie_gateway_client', MODULE)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
TOKEN = 'x' * 40
MODEL = 'qwen2.5-coder:1.5b'


class GatewayClientTests(unittest.TestCase):
    def test_allowed_and_disallowed_endpoints(self):
        for endpoint in ('http://127.0.0.1:19134', 'http://localhost:19134',
                         'https://herbie.example-tailnet.ts.net',
                         'https://herbie.example-tailnet.ts.net:443/'):
            self.assertTrue(gateway.validate_gateway_url(endpoint))
        for endpoint in ('http://192.168.1.3:11434', 'http://herbie.ts.net',
                         'http://127.0.0.1:11434@evil.invalid',
                         'https://evil.invalid', 'https://ts.net',
                         'https://herbie.example-tailnet.ts.net:444',
                         'https://herbie.example-tailnet.ts.net/other',
                         'https://herbie.example-tailnet.ts.net?x=1',
                         'https://herbie.example-tailnet.ts.net#fragment',
                         'https://herbie.example-tailnet.ts.net\n.evil.invalid',
                         'http://localhost.evil.invalid:1234'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                gateway.validate_gateway_url(endpoint)

    def test_config_and_task_validation(self):
        for token in ('short', 'bad\nheader', ''):
            with self.assertRaises(ValueError):
                gateway.HerbieGatewayClient('http://127.0.0.1:1234', token, MODEL)
        client = gateway.HerbieGatewayClient('http://127.0.0.1:1234', TOKEN, MODEL)
        request_id = str(uuid4())
        for kind, prompt, ident in [('deploy', 'hi', request_id),
                                     ('coding', '', request_id),
                                     ('coding', 'a' * 12001, request_id),
                                     ('coding', 'hello', 'bad-id')]:
            with self.assertRaises(ValueError):
                client.infer(kind, prompt, ident)

    def server(self, handler):
        seen = []
        class Endpoint(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                seen.append((self.path, dict(self.headers.items()), raw))
                handler(self, json.loads(raw))
            def do_GET(self):
                seen.append((self.path, dict(self.headers.items()), b''))
                handler(self, None)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Endpoint)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}', seen

    def respond(self, handler, body, status=200):
        raw = json.dumps(body).encode()
        handler.send_response(status)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def test_infer_sends_only_scoped_request_and_validates_response(self):
        def responder(handler, incoming):
            self.respond(handler, {'schema_version': 1,
                'request_id': incoming['request_id'], 'model': incoming['model'],
                'reply': 'Review the tests.'})
        url, seen = self.server(responder)
        client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
        ident = str(uuid4())
        self.assertEqual(client.infer('testing', 'Run approved test review', ident), 'Review the tests.')
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], '/v1/worker/infer')
        self.assertEqual(seen[0][1]['Authorization'], 'Bearer ' + TOKEN)
        self.assertEqual(json.loads(seen[0][2]), {'schema_version': 1,
            'request_id': ident, 'task_type': 'testing', 'model': MODEL,
            'prompt': 'Run approved test review'})

    def test_mismatched_response_is_rejected(self):
        def responder(handler, incoming):
            self.respond(handler, {'schema_version': 1, 'request_id': str(uuid4()),
                                  'model': incoming['model'], 'reply': 'Unsafe stale answer'})
        url, _ = self.server(responder)
        with self.assertRaises(gateway.GatewayError):
            gateway.HerbieGatewayClient(url, TOKEN, MODEL).infer('coding', 'Hello', str(uuid4()))

    def test_http_error_has_no_secret_and_no_auto_retry(self):
        def responder(handler, incoming):
            self.respond(handler, {'error': 'token ' + TOKEN}, status=503)
        url, seen = self.server(responder)
        client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
        with self.assertRaises(gateway.GatewayError) as ctx:
            client.infer('research', 'Investigate approved source', str(uuid4()))
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertEqual(len(seen), 1)

    def test_redirect_rejected_without_following(self):
        def responder(handler, incoming):
            handler.send_response(302)
            handler.send_header('Location', 'https://evil.invalid/steal-token')
            handler.send_header('Content-Length', '0')
            handler.end_headers()
        url, seen = self.server(responder)
        client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
        with self.assertRaises(gateway.GatewayError):
            client.infer('review', 'Inspect diff', str(uuid4()))
        self.assertEqual(len(seen), 1)

    def test_oversize_and_invalid_json_are_rejected(self):
        for payload in (b'x' * (gateway.MAX_RESPONSE_BYTES + 10), b'not-json'):
            with self.subTest(length=len(payload)):
                def responder(handler, incoming):
                    handler.send_response(200)
                    handler.send_header('Content-Length', str(len(payload)))
                    handler.end_headers()
                    handler.wfile.write(payload)
                url, _ = self.server(responder)
                client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
                with self.assertRaises(gateway.GatewayError):
                    client.infer('testing', 'Check fixture', str(uuid4()))


    def test_health_checks_auth_and_expected_response(self):
        def responder(handler, incoming):
            self.respond(handler, {'schema_version': 1, 'ok': True})
        url, seen = self.server(responder)
        client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
        self.assertTrue(client.health())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], '/v1/worker/health')
        self.assertEqual(seen[0][1]['Authorization'], 'Bearer ' + TOKEN)

    def test_health_rejects_unexpected_or_oversize_response(self):
        for payload in ({'schema_version': 1, 'ok': False},
                        {'schema_version': True, 'ok': True},
                        {'schema_version': 1, 'ok': True, 'model': MODEL},
                        {'schema_version': 1, 'ok': True, 'padding': 'x' * 2000}):
            with self.subTest(payload=payload.get('ok')):
                def responder(handler, incoming):
                    self.respond(handler, payload)
                url, _ = self.server(responder)
                client = gateway.HerbieGatewayClient(url, TOKEN, MODEL)
                with self.assertRaises(gateway.GatewayError):
                    client.health()


if __name__ == '__main__':
    unittest.main()
