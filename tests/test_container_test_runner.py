"""Synthetic Step 3 containment tests; never start Docker, npm or a model.

Tests the exact Docker argument policy, fail-closed paths, and CLI selection.
A disposable container image/daemon is not available on hosted CI, so these
tests CANNOT claim real untrusted code isolation or VM security.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from uuid import uuid4

AGENTS = Path(__file__).resolve().parents[1] / "agents"
sys.path.insert(0, str(AGENTS))
import container_test_runner as runner
import first_task
import gateway_first_task

IMAGE = "docker.io/library/node@sha256:" + "a" * 64
TOKEN = "s" * 48


class DockerPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="bv-sandbox-fixture-")
        self.addCleanup(temp.cleanup)
        self.checkout = Path(temp.name)
        self.calls = []

    def fake_docker(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[1:3] == ["context", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, '"unix:///var/run/docker.sock"\n', '')
        if argv[1] == "run":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1] == "rm":
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError("Unreviewed container launcher operation")

    def test_fixed_immutable_image_and_isolation_policy(self):
        with patch.object(runner.shutil, "which", return_value="/trusted/docker"), \
             patch.object(runner.subprocess, "run", side_effect=self.fake_docker), \
             patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": "",
                                    "DOCKER_TLS_VERIFY": "", "DOCKER_CERT_PATH": "",
                                    "DOCKER_API_VERSION": ""}):
            result = runner.run_container_npm_test(self.checkout, image=IMAGE)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.calls), 3)
        args, kwargs = self.calls[1]
        self.assertEqual(args[0:2], ["/trusted/docker", "run"])
        for flag in ("--pull=never", "--network=none", "--read-only",
                     "--user=65534:65534", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges", "--pids-limit=64",
                     "--memory=512m", "--cpus=1"):
            self.assertIn(flag, args)
        self.assertTrue(any(x.startswith("--tmpfs=/tmp:") for x in args))
        mount = args[args.index("--mount") + 1]
        self.assertIn("target=/workspace,readonly", mount)
        self.assertIn(str(self.checkout.resolve()), mount)
        self.assertEqual(args[-2:], [IMAGE, "test"])
        self.assertEqual(args[args.index("--entrypoint=npm") + 1], IMAGE)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(self.calls[-1][0][1:3], ["rm", "-f"])
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--publish", args)

    def test_malformed_or_unpinned_image_blocks_before_docker(self):
        with patch.object(runner.shutil, "which") as lookup:
            for img in ("node:latest", "node@sha256:bad", IMAGE + "; echo pwn",
                        "docker.io/library/node"):
                with self.subTest(img=img), self.assertRaises(runner.SandboxUnavailable):
                    runner.run_container_npm_test(self.checkout, image=img)
            lookup.assert_not_called()

    def test_missing_docker_never_falls_back_to_host_npm(self):
        with patch.object(runner.shutil, "which", return_value=None), \
             patch.object(runner.subprocess, "run") as subprocess_call:
            with self.assertRaises(runner.SandboxUnavailable):
                runner.run_container_npm_test(self.checkout, image=IMAGE)
            subprocess_call.assert_not_called()

    def test_remote_context_rejected_without_container_run(self):
        def remote(argv, **kwargs):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, '"ssh://remote.invalid"\n', '')
        with patch.object(runner.shutil, "which", return_value="/trusted/docker"), \
             patch.object(runner.subprocess, "run", side_effect=remote):
            with self.assertRaises(runner.SandboxUnavailable):
                runner.run_container_npm_test(self.checkout, image=IMAGE)
        self.assertEqual(len(self.calls), 1)

    def test_explicit_remote_override_blocked(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote.invalid:2375"}), \
             patch.object(runner.shutil, "which") as lookup:
            with self.assertRaises(runner.SandboxUnavailable):
                runner.run_container_npm_test(self.checkout, image=IMAGE)
            lookup.assert_not_called()

    def test_failed_container_start_never_counts_as_failed_baseline(self):
        def fake(argv, **kwargs):
            self.calls.append(argv)
            if argv[1] == "context":
                return subprocess.CompletedProcess(argv, 0, '"npipe:////./pipe/docker_engine"\n', '')
            if argv[1] == "run":
                return subprocess.CompletedProcess(argv, 125)
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(runner.shutil, "which", return_value="/trusted/docker"), \
             patch.object(runner.subprocess, "run", side_effect=fake), \
             self.assertRaises(runner.SandboxUnavailable):
            runner.run_container_npm_test(self.checkout, image=IMAGE)
        self.assertEqual(self.calls[-1][1:3], ["rm", "-f"])

    def test_timeout_attempts_force_removal(self):
        def fake(argv, **kwargs):
            self.calls.append(argv)
            if argv[1] == "context":
                return subprocess.CompletedProcess(argv, 0, '"unix:///var/run/docker.sock"\n', '')
            if argv[1] == "run":
                raise subprocess.TimeoutExpired(argv, 95)
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(runner.shutil, "which", return_value="/trusted/docker"), \
             patch.object(runner.subprocess, "run", side_effect=fake), \
             self.assertRaises(runner.SandboxUnavailable):
            runner.run_container_npm_test(self.checkout, image=IMAGE)
        self.assertEqual(self.calls[-1][1:3], ["rm", "-f"])

    def test_executor_is_used_instead_of_host_npm(self):
        sandbox = []
        def executor(checkout):
            sandbox.append(checkout)
            return subprocess.CompletedProcess(["synthetic"], 0, "", "")
        with patch.object(first_task.subprocess, "run") as host:
            result = first_task._npm_tests(self.checkout, executor)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(sandbox, [self.checkout])
            host.assert_not_called()


class ContainerCliTests(unittest.TestCase):
    def test_gateway_cli_sandbox_mode_passes_image_without_trusted_host_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "review.json"
            argv = ["--repo", temp, "--model", "synthetic:1b",
                    "--gateway-url", "http://127.0.0.1:8787",
                    "--output", str(output), "--request-id", str(uuid4()),
                    "--sandbox-image", IMAGE]
            evidence = {"status": "ready_for_human_review",
                        "test_exit_code": 0, "merge_allowed": False}
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task",
                              return_value=evidence) as task, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(gateway_first_task.main(argv), 0)
            self.assertEqual(task.call_args.kwargs["sandbox_image"], IMAGE)
            self.assertEqual(json.loads(output.read_text()), evidence)

    def test_gateway_worker_routes_sandbox_to_full_isolation_not_host_worktree(self):
        evidence = {"status": "ready_for_human_review",
                    "merge_allowed": False, "test_exit_code": 0}
        with patch.object(gateway_first_task, "run_task") as legacy, \
             patch.object(gateway_first_task, "run_wholly_isolated_task",
                          return_value=evidence) as isolated:
            result = gateway_first_task.run_gateway_task(
                "unused-unfamiliar-repo", "synthetic:1b",
                "http://127.0.0.1:8787", TOKEN, sandbox_image=IMAGE)
        self.assertEqual(result["status"], "ready_for_human_review")
        isolated.assert_called_once()
        legacy.assert_not_called()
        self.assertEqual(isolated.call_args.kwargs["sandbox_image"], IMAGE)
        self.assertFalse(result["merge_allowed"])

    def test_historical_cli_sandbox_path_does_not_require_host_test_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "private-report.json"
            argv = ["first_task.py", "--repo", temp,
                    "--model", "synthetic:1b", "--output", str(output),
                    "--sandbox-image", IMAGE]
            evidence = {"status": "ready_for_human_review", "merge_allowed": False,
                        "test_exit_code": 0}
            with patch.object(sys, "argv", argv), \
                 patch.object(first_task, "run_task") as legacy, \
                 patch.object(first_task, "run_wholly_isolated_task",
                              return_value=evidence) as isolated, \
                 redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    first_task.main()
            self.assertEqual(result.exception.code, 0)
            legacy.assert_not_called()
            isolated.assert_called_once()
            self.assertEqual(isolated.call_args.kwargs["sandbox_image"], IMAGE)
            self.assertEqual(json.loads(output.read_text()), evidence)

    def test_gateway_cli_cannot_use_host_and_sandbox_modes_together(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "blocked.json"
            argv = ["--repo", temp, "--model", "synthetic:1b",
                    "--gateway-url", "http://127.0.0.1:8787",
                    "--output", str(output), "--request-id", str(uuid4()),
                    "--allow-trusted-host-tests", "--sandbox-image", IMAGE]
            with patch.dict(os.environ, {"HERBIE_WORKER_TOKEN": TOKEN}), \
                 patch.object(gateway_first_task, "run_gateway_task") as task, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(gateway_first_task.main(argv), 1)
            task.assert_not_called()
            self.assertEqual(json.loads(output.read_text())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
