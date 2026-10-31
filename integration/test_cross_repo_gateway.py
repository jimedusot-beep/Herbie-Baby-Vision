"""Baby Vision -> H.E.R.B.I.E. -> fake Ollama contract verification.

Run only when both repository checkouts are available. No AI, VPN, camera,
GitHub mutation or hardware connection is used. Network: loopback only.

HERBIE_WORKER_GATEWAY_PY=/path/to/Herbie/socratic-agent/socratic_agent/worker_gateway.py \
  python -m unittest discover -s integration -p 'test_*.py' -v
"""

import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
from herbie_gateway_client import GatewayError, HerbieGatewayClient

MODEL = 'qwen2.5-coder:1.5b'  # Synthetic model name, no model download.


def load_real_gateway():
    path = os.environ.get('HERBIE_WORKER_GATEWAY_PY', '')
    if not path or not Path(path).is_file():
        raise RuntimeError('Provide HERBIE_WORKER_GATEWAY_PY pointing to an approved Herbie source checkout')
    spec = importlib.util.spec_from_file_location('herbie_worker_gateway_v02b', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EndToEndContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_real_gateway()

    def setUp(self):
        self.secret = secrets.token_urlsafe(40)
        self.inference_requests = []
        self.force_ollama_error = False
        case = self

        class FakeOllama(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                assert self.path == '/api/chat'
                size = int(self.headers['Content-Length'])
                request = json.loads(self.rfile.read(size))
                case.inference_requests.append(request)
                if case.force_ollama_error:
                    self.send_response(503)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                # The reply is synthetic and contains no model-generated content.
                reply = {'message': {'content': 'SYNTHETIC: ' + request['messages'][-1]['content']}}
                raw = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.ollama = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
        self.gateway = self.module.WorkerGatewayServer(
            ('127.0.0.1', 0), token=self.secret, allowed_models=(MODEL,),
            ollama_url=f'http://127.0.0.1:{self.ollama.server_port}',
            max_requests_per_minute=20)
        self.threads = [threading.Thread(target=server.serve_forever, daemon=True)
                        for server in (self.ollama, self.gateway)]
        for thread in self.threads:
            thread.start()
        url = f'http://127.0.0.1:{self.gateway.server_port}'
        self.client = HerbieGatewayClient(url, self.secret, MODEL, timeout=3)

    def tearDown(self):
        for server in (self.gateway, self.ollama):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=3)

    def test_real_client_gateway_and_fake_ollama_roundtrip(self):
        text = self.client.infer('coding', 'Explain the synthetic test', str(uuid4()))
        self.assertEqual(text, 'SYNTHETIC: Explain the synthetic test')
        self.assertEqual(len(self.inference_requests), 1)
        upstream = self.inference_requests[0]
        self.assertEqual(upstream['model'], MODEL)
        self.assertEqual(len(upstream['messages']), 2)
        self.assertIn('coding assistant', upstream['messages'][0]['content'])
        self.assertEqual(upstream['messages'][1]['content'], 'Explain the synthetic test')
        self.assertNotIn('tools', upstream)

    def test_health_uses_auth_and_has_no_model_details(self):
        self.assertTrue(self.client.health())
        self.assertEqual(self.inference_requests, [])
        wrong = HerbieGatewayClient(self.client.base_url, 'z' * 48, MODEL, timeout=3)
        with self.assertRaises(GatewayError):
            wrong.health()

    def test_bad_token_is_denied_before_upstream_call(self):
        wrong = HerbieGatewayClient(self.client.base_url, 'z' * 48, MODEL, timeout=3)
        with self.assertRaises(GatewayError) as error:
            wrong.infer('testing', 'Do not process', str(uuid4()))
        self.assertNotIn(self.secret, str(error.exception))
        self.assertEqual(self.inference_requests, [])

    def test_disallowed_model_and_task_are_denied(self):
        wrong_model = HerbieGatewayClient(self.client.base_url, self.secret, 'other:latest', timeout=3)
        with self.assertRaises(GatewayError):
            wrong_model.infer('coding', 'Denied model', str(uuid4()))
        with self.assertRaises(ValueError):
            self.client.infer('deploy', 'Forbidden task', str(uuid4()))
        self.assertEqual(self.inference_requests, [])

    def test_separate_calls_do_not_share_conversation_history(self):
        self.client.infer('research', 'Synthetic first query', str(uuid4()))
        self.client.infer('review', 'Synthetic second query', str(uuid4()))
        self.assertEqual(len(self.inference_requests), 2)
        first, second = self.inference_requests
        self.assertEqual(first['messages'][-1]['content'], 'Synthetic first query')
        self.assertEqual(second['messages'][-1]['content'], 'Synthetic second query')
        self.assertNotIn('Synthetic first query', json.dumps(second))

    def test_upstream_failure_does_not_return_a_fake_success(self):
        self.force_ollama_error = True
        with self.assertRaises(GatewayError):
            self.client.infer('coding', 'Synthetic failure', str(uuid4()))
        self.assertEqual(len(self.inference_requests), 1)

    def test_retry_is_not_automatic_for_an_unavailable_server(self):
        self.force_ollama_error = True
        with self.assertRaises(GatewayError):
            self.client.infer('coding', 'No retry', str(uuid4()))
        self.assertEqual(len(self.inference_requests), 1)


if __name__ == '__main__':
    unittest.main()
