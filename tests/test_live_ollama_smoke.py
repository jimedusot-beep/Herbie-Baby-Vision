"""Synthetic tests for the operator-triggered REAL Ollama smoke harness.

No model is downloaded or called by this test file.
"""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import re
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "integration" / "live_ollama_smoke.py"
spec = importlib.util.spec_from_file_location("baby_live_smoke", SOURCE)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class TagFixture:
    def __init__(self, payload=None, redirect=False):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(
            payload if payload is not None else {"models": [{"name": "gemma3:1b"}]}
        ).encode()
        self.redirect = redirect
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if parent.redirect:
                    self.send_response(302)
                    self.send_header("Location", "https://example.invalid/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                raw = parent.payload
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class SmokeHarnessTests(unittest.TestCase):
    def test_script_requires_explicit_run_live(self):
        with patch.object(smoke, "run_live") as runner, patch("builtins.print"):
            self.assertEqual(smoke.main([]), 2)
        runner.assert_not_called()

    def test_unavailable_gateway_file_fails_before_starting(self):
        with self.assertRaises(smoke.SmokeBlocked):
            smoke.load_gateway_module("")
        with self.assertRaises(smoke.SmokeBlocked):
            smoke.load_gateway_module("nonexistent/worker_gateway.py")

    def test_unreviewed_gateway_source_is_refused_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "worker_gateway.py"
            path.write_text("raise RuntimeError('untrusted code should not execute')\\n",
                            encoding="utf-8")
            with self.assertRaisesRegex(smoke.SmokeBlocked,
                                        "gateway_source_revision_unreviewed"):
                smoke.load_gateway_module(path)

    def test_loopback_tags_allowlist_detects_installed_model(self):
        fixture = TagFixture({"models": [{"name": "gemma3:1b"},
                                         {"model": "qwen2.5-coder:1.5b"}]})
        self.addCleanup(fixture.close)
        names = smoke.installed_models(fixture.url, lambda url: url)
        self.assertEqual(names, {"gemma3:1b", "qwen2.5-coder:1.5b"})

    def test_tags_invalid_and_oversize_fail_closed(self):
        for payload in (b'not-json', b'{"models":{}}',
                        b'{' + b'x' * smoke.MAX_TAGS_BYTES + b'}'):
            with self.subTest(size=len(payload)):
                fixture = TagFixture(payload)
                try:
                    with self.assertRaises(smoke.SmokeBlocked):
                        smoke.installed_models(fixture.url, lambda url: url)
                finally:
                    fixture.close()

    def test_tags_redirect_refused(self):
        fixture = TagFixture(redirect=True)
        self.addCleanup(fixture.close)
        with self.assertRaises(smoke.SmokeBlocked):
            smoke.installed_models(fixture.url, lambda url: url)

    def test_missing_model_blocks_without_gateway_server(self):
        fake = SimpleNamespace(
            MODEL_PATTERN=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}\Z"),
            validate_local_ollama=lambda url: url,
            WorkerGatewayServer=lambda *a, **k: self.fail("Never open a server"),
        )
        with patch.object(smoke, "load_gateway_module", return_value=fake), \
             patch.object(smoke, "installed_models", return_value=set()):
            with self.assertRaisesRegex(smoke.SmokeBlocked, "requested_model_not_installed"):
                smoke.run_live("gemma3:1b", "reviewed/worker_gateway.py")

    def test_fake_local_gateway_proves_safe_reporting_and_auth(self):
        events = []
        class FakeGatewayServer(ThreadingHTTPServer):
            def __init__(self, addr, *, token, allowed_models, ollama_url, max_requests_per_minute):
                self.token = token
                self.model = next(iter(allowed_models))

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass
                    def _respond(self, status, body):
                        raw = json.dumps(body).encode()
                        self.send_response(status)
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                    def do_GET(self):
                        events.append(("GET", self.path))
                        if self.headers.get("Authorization") != "Bearer " + self.server.token:
                            return self._respond(403, {"error": "forbidden"})
                        return self._respond(200, {"schema_version": 1, "ok": True})
                    def do_POST(self):
                        events.append(("POST", self.path))
                        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        if self.headers.get("Authorization") != "Bearer " + self.server.token:
                            return self._respond(403, {"error": "forbidden"})
                        return self._respond(200, {"schema_version": 1,
                            "request_id": req["request_id"], "model": self.server.model,
                            "reply": "SYNTHETIC_PRIVATE_REPLY"})

                super().__init__(addr, Handler)

        fake = SimpleNamespace(
            MODEL_PATTERN=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}\Z"),
            validate_local_ollama=lambda url: url,
            WorkerGatewayServer=FakeGatewayServer,
        )
        with patch.object(smoke, "load_gateway_module", return_value=fake), \
             patch.object(smoke, "installed_models", return_value={"gemma3:1b"}):
            report = smoke.run_live("gemma3:1b", "reviewed/worker_gateway.py")
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["incorrect_token_rejected"])
        self.assertEqual([kind for kind, _ in events], ["GET", "GET", "POST"])
        self.assertNotIn("SYNTHETIC_PRIVATE_REPLY", json.dumps(report))
        self.assertNotIn(smoke.TEST_PROMPT, json.dumps(report))
        self.assertFalse(report["merge_allowed"])


if __name__ == "__main__":
    unittest.main()
