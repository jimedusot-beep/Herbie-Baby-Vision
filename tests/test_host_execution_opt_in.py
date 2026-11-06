"""Fail-closed CLI opt-in tests for unsandboxed trusted host npm scripts.

Mocks the worker function; never executes npm, Git, Ollama or any repository tests.
The opt-in is an explicit human gate, NOT an operating-system sandbox.
"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import first_task
import gateway_first_task

TOKEN = "t" * 48
MODEL = "fixture-model:1b"


class HostExecutionOptInTests(unittest.TestCase):
    def test_historical_cli_requires_opt_in_before_running_host_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            args = [
                "first_task.py", "--repo", tmp, "--model", MODEL,
                "--output", str(output),
            ]
            with patch.object(sys, "argv", args), \
                 patch.object(first_task, "run_task") as worker, \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    first_task.main()
            self.assertEqual(caught.exception.code, 2)
            worker.assert_not_called()
            self.assertFalse(output.exists())

    def test_gateway_cli_requires_opt_in_without_touching_worker_or_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gateway-result.json"
            args = [
                "--repo", tmp, "--model", MODEL,
                "--gateway-url", "http://127.0.0.1:8787",
                "--output", str(output),
            ]
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task") as worker, \
                 redirect_stdout(io.StringIO()):
                status = gateway_first_task.main(args)
            self.assertEqual(status, 1)
            worker.assert_not_called()
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["merge_allowed"])
            self.assertEqual(result["error_type"], "PermissionError")
            self.assertNotIn(TOKEN, json.dumps(result))

    def test_explicit_gateway_cli_opt_in_preserves_bounded_review_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gateway-result.json"
            args = [
                "--repo", tmp, "--model", MODEL,
                "--gateway-url", "http://127.0.0.1:8787",
                "--output", str(output),
                "--allow-trusted-host-tests",
                "--request-id", str(uuid4()),
            ]
            expected_id = args[-1]
            evidence = {
                "status": "ready_for_human_review",
                "test_exit_code": 0,
                "merge_allowed": False,
            }
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task",
                              return_value=evidence) as worker, \
                 redirect_stdout(io.StringIO()):
                status = gateway_first_task.main(args)
            self.assertEqual(status, 0)
            worker.assert_called_once()
            self.assertEqual(worker.call_args.kwargs["request_id"], expected_id)
            self.assertEqual(json.loads(output.read_text()), evidence)


    def test_opted_in_cli_without_stable_request_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            args = ["--repo", tmp, "--model", MODEL,
                    "--gateway-url", "http://127.0.0.1:8787",
                    "--output", str(output), "--allow-trusted-host-tests"]
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task") as worker, \
                 redirect_stdout(io.StringIO()):
                status = gateway_first_task.main(args)
            self.assertEqual(status, 1)
            worker.assert_not_called()
            packet = json.loads(output.read_text())
            self.assertEqual(packet["status"], "blocked")
            self.assertEqual(packet["error_type"], "ValueError")
            self.assertNotIn(TOKEN, json.dumps(packet))

    def test_opted_in_cli_rejects_malformed_replay_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            args = ["--repo", tmp, "--model", MODEL,
                    "--gateway-url", "http://127.0.0.1:8787",
                    "--output", str(output), "--allow-trusted-host-tests",
                    "--request-id", "not-a-uuid"]
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task") as worker, \
                 redirect_stdout(io.StringIO()):
                status = gateway_first_task.main(args)
            self.assertEqual(status, 1)
            worker.assert_not_called()
            self.assertEqual(json.loads(output.read_text())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
