"""Baby Vision -> H.E.R.B.I.E. -> fake Ollama contract verification.

Run only when both repository checkouts are available. No AI, VPN, camera,
GitHub mutation or hardware connection is used. Network: loopback only.

HERBIE_WORKER_GATEWAY_PY=/path/to/Herbie/socratic-agent/socratic_agent/worker_gateway.py \
  python -m unittest discover -s integration -p 'test_*.py' -v
"""

import json
import os
from pathlib import Path
import secrets
import sys
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
from herbie_gateway_client import GatewayCancelled, GatewayError, HerbieGatewayClient
from live_ollama_smoke import SmokeBlocked, load_gateway_module

MODEL = 'qwen2.5-coder:1.5b'  # Synthetic model name, no model download.


def load_real_gateway():
    path = os.environ.get('HERBIE_WORKER_GATEWAY_PY', '')
    if not path or not Path(path).is_file():
        raise RuntimeError('Provide HERBIE_WORKER_GATEWAY_PY pointing to an approved Herbie source checkout')
    try:
        # Execute only the exact reviewed bytes, using the same pin as live smoke.
        return load_gateway_module(path)
    except SmokeBlocked:
        raise RuntimeError('Gateway source is not the reviewed revision') from None


class EndToEndContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_real_gateway()

    def setUp(self):
        self.secret = secrets.token_urlsafe(40)
        self.inference_requests = []
        self.force_ollama_error = False
        self.pause_ollama = False
        self.ollama_entered = threading.Event()
        self.ollama_release = threading.Event()
        case = self

        class FakeOllama(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                assert self.path == '/api/chat'
                size = int(self.headers['Content-Length'])
                request = json.loads(self.rfile.read(size))
                case.inference_requests.append(request)
                if case.pause_ollama:
                    case.ollama_entered.set()
                    case.ollama_release.wait(4)
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
        self.ollama_release.set()
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

    def test_fixed_schema_npm_alias_request_does_not_change_freeform_coding(self):
        result = self.client.infer('npm_test_alias_v1',
                                   'Only approved test alias', str(uuid4()))
        self.assertEqual(result, 'SYNTHETIC: Only approved test alias')
        self.assertEqual(len(self.inference_requests), 1)
        bounded = self.inference_requests[0]
        schema = bounded['format']
        self.assertEqual(schema['properties']['script']['enum'], ['npm run test:unit'])
        self.assertEqual(set(schema['required']), {'script', 'reason'})
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(bounded['options']['temperature'], 0)
        self.assertNotIn('tools', bounded)

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

    def test_cancel_with_real_client_and_fake_ollama_suppresses_stale_reply(self):
        # Requires the reviewed private logical-stop gateway candidate.
        # This exercises actual HTTP auth and Ollama adapter using a fake server.
        self.pause_ollama = True
        request_id = str(uuid4())
        local_stop = threading.Event()
        delivered, rejected = [], []

        def request_worker():
            try:
                delivered.append(self.client.infer(
                    'testing', 'Synthetic slow task', request_id,
                    cancel_event=local_stop))
            except GatewayError as exc:
                rejected.append(type(exc).__name__)

        worker = threading.Thread(target=request_worker)
        worker.start()
        try:
            self.assertTrue(self.ollama_entered.wait(2))
            wrong = HerbieGatewayClient(
                self.client.base_url, 'z' * 48, MODEL, timeout=3)
            with self.assertRaises(GatewayError):
                wrong.cancel(request_id)
            self.assertEqual(self.client.cancel(request_id),
                             'cancellation_recorded')
            local_stop.set()
        finally:
            self.ollama_release.set()
            worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(delivered, [])
        self.assertEqual(rejected, ['GatewayCancelled'])
        self.assertEqual(len(self.inference_requests), 1)
        with self.assertRaises(GatewayError):
            self.client.infer('testing', 'Attempt repeated task', request_id)

    def test_duplicate_id_is_denied_after_gateway_restart_without_second_inference(self):
        # The accepted-ID journal exists only for the newer reviewed private
        # gateway candidate. This executes synthetic HTTP/Ollama, no real AI.
        with tempfile.TemporaryDirectory(prefix="bv-replay-fixture-") as folder:
            journal = str(Path(folder) / "accepted.sqlite3")
            request_id = str(uuid4())

            def start():
                server = self.module.WorkerGatewayServer(
                    ('127.0.0.1', 0), token=self.secret,
                    allowed_models=(MODEL,),
                    ollama_url=f'http://127.0.0.1:{self.ollama.server_port}',
                    max_requests_per_minute=20, request_registry_path=journal)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                client = HerbieGatewayClient(
                    f'http://127.0.0.1:{server.server_port}',
                    self.secret, MODEL, timeout=3)
                return server, thread, client

            first, first_thread, first_client = start()
            try:
                self.assertEqual(first_client.infer('testing', 'One accepted task',
                                                    request_id),
                                 'SYNTHETIC: One accepted task')
                self.assertEqual(len(self.inference_requests), 1)
            finally:
                first.shutdown()
                first.server_close()
                first_thread.join(timeout=3)

            second, second_thread, second_client = start()
            try:
                with self.assertRaises(GatewayError):
                    second_client.infer('testing', 'Replay must be denied', request_id)
                self.assertEqual(len(self.inference_requests), 1)
                self.assertEqual(second_client.infer('testing', 'New UUID task',
                                                     str(uuid4())),
                                 'SYNTHETIC: New UUID task')
                self.assertEqual(len(self.inference_requests), 2)
            finally:
                second.shutdown()
                second.server_close()
                second_thread.join(timeout=3)

    def test_retry_is_not_automatic_for_an_unavailable_server(self):
        self.force_ollama_error = True
        with self.assertRaises(GatewayError):
            self.client.infer('coding', 'No retry', str(uuid4()))
        self.assertEqual(len(self.inference_requests), 1)


if __name__ == '__main__':
    unittest.main()
