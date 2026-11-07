"""Synthetic full-pipeline isolation regressions; no real Docker/Git/npm/Ollama.

The selected repo is represented by a disposable empty directory. Host
subprocesses are replaced with fake Docker, never executed. Container Git
and npm phases are separately exercised with mocked commands and tmp data.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
import first_task
import isolated_repo_runner as runner
import isolated_worker_entry as entry

IMAGE = "docker.io/library/approved-worker@sha256:" + "b" * 64
PROPOSAL = {"script": "npm run test:unit", "reason": "approved bounded alias"}


def success_packet():
    return {
        "schema_version": 1, "status": "ready_for_human_review",
        "merge_allowed": False, "test_exit_code": 0,
        "baseline_test_exit_code": 1, "source_commit": "a" * 40,
        "patch": "diff --git a/package.json b/package.json\n+  \"test\": \"npm run test:unit\"",
        "proposal": PROPOSAL, "host_git_executed": False,
        "host_npm_executed": False, "execution_mode": "full_container",
        "untrusted_repository_approved": False,
    }


class _FakeProcess:
    def __init__(self, argv, *, output, **kwargs):
        self.argv = argv
        self.stdout = io.BytesIO(output)
        self.stdin = io.BytesIO()
        self._status = 0
        self._killed = False

    def wait(self, timeout=None):
        return self._status

    def poll(self):
        return self._status

    def kill(self):
        self._killed = True
        self._status = -9


class FullPipelineHostBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bv-full-isolation-test-")
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "unfamiliar-source"
        self.source.mkdir()
        self.host_calls = []
        self.payload = success_packet()

    def docker_command(self, argv, **kwargs):
        self.host_calls.append((list(argv), kwargs))
        if argv[1:3] == ["context", "inspect"]:
            return subprocess.CompletedProcess(
                argv, 0, b'"npipe:////./pipe/docker_engine"\n', b'')
        if argv[1:3] == ["rm", "-f"]:
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[1] == "inspect":
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        raise AssertionError("Unexpected host command")

    def run_fake(self):
        output = json.dumps(self.payload).encode()
        processes = []
        def popen(argv, **kwargs):
            self.host_calls.append((list(argv), kwargs))
            process = _FakeProcess(argv, output=output, **kwargs)
            processes.append(process)
            return process
        with patch.object(runner.shutil, "which", return_value="C:/Program Files/Docker/docker.exe"), \
             patch.object(runner.subprocess, "run", side_effect=self.docker_command), \
             patch.object(runner.subprocess, "Popen", side_effect=popen), \
             patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": "",
                     "DOCKER_TLS_VERIFY": "", "DOCKER_CERT_PATH": "",
                     "DOCKER_CONFIG": "", "DOCKER_API_VERSION": ""}):
            packet = runner.run_isolated_repo_task(
                self.source, image=IMAGE, proposal=PROPOSAL)
        return packet, processes

    def test_only_docker_commands_on_host_and_git_npm_inside_container(self):
        packet, processes = self.run_fake()
        self.assertEqual(packet["status"], "ready_for_human_review")
        self.assertEqual(len(processes), 1)
        self.assertEqual(len(self.host_calls), 4)
        self.assertEqual([c[0][1] for c in self.host_calls],
                         ["context", "run", "rm", "inspect"])
        args, kwargs = self.host_calls[1]
        for choice in ("--pull=never", "--network=none", "--read-only",
                       "--user=65534:65534", "--cap-drop=ALL",
                       "--security-opt=no-new-privileges",
                       "--memory=512m", "--cpus=1"):
            self.assertIn(choice, args)
        self.assertIn("--entrypoint=python3", args)
        self.assertEqual(args[-3:], [IMAGE, "-I", "/runner/isolated_worker_entry.py"])
        mounts = [args[i+1] for i, val in enumerate(args[:-1]) if val == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(all("readonly" in mount for mount in mounts))
        self.assertTrue(any("target=/source" in mount for mount in mounts))
        self.assertTrue(any("target=/runner/isolated_worker_entry.py" in mount
                            for mount in mounts))
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--publish", args)
        self.assertNotIn("--volume", args)
        self.assertNotIn("git", [c[0][0] for c in self.host_calls])
        self.assertNotIn("npm", [c[0][0] for c in self.host_calls])
        self.assertNotIn("HERBIE_WORKER_TOKEN", kwargs["env"])
        self.assertEqual(
            json.loads(processes[0].stdin.getvalue() if not processes[0].stdin.closed else
                       json.dumps({"base": "HEAD", "proposal": PROPOSAL})),
            {"base": "HEAD", "proposal": PROPOSAL})

    def test_no_docker_means_no_host_git_fallback(self):
        with patch.object(runner.shutil, "which", return_value=None), \
             patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaises(runner.IsolationBlocked):
                runner.run_isolated_repo_task(
                    self.source, image=IMAGE, proposal=PROPOSAL)
        spawn.assert_not_called()

    def test_remote_docker_context_fails_before_launch(self):
        def fake(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, b'"ssh://unsafe.invalid"\n', b"")
        with patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(runner.subprocess, "run", side_effect=fake), \
             patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaises(runner.IsolationBlocked):
                runner.run_isolated_repo_task(self.source, image=IMAGE, proposal=PROPOSAL)
        spawn.assert_not_called()

    def test_unpinned_image_blocks_before_engine(self):
        with patch.object(runner.shutil, "which") as locate:
            for image in ("node:latest", IMAGE + " && calc.exe", IMAGE[:-1],
                          "localhost:5000/node:20"):
                with self.subTest(image=image), self.assertRaises(runner.IsolationBlocked):
                    runner.run_isolated_repo_task(self.source, image=image, proposal=PROPOSAL)
            locate.assert_not_called()

    def test_rejected_evidence_fails_closed(self):
        for field, bad in (("merge_allowed", True),
                           ("status", "ready_to_merge"),
                           ("host_git_executed", True),
                           ("execution_mode", "trusted_host"),
                           ("patch", "diff --git a/.git/config b/.git/config")):
            self.payload = success_packet()
            self.payload[field] = bad
            with self.subTest(field=field), self.assertRaises(runner.IsolationBlocked):
                self.run_fake()

    def test_oversized_output_fails_and_attempts_cleanup(self):
        self.payload = {"oversize": "x" * 80000}
        with self.assertRaises(runner.IsolationBlocked):
            self.run_fake()
        self.assertEqual([x[0][1] for x in self.host_calls][-2:],
                         ["rm", "inspect"])

    def test_cleanup_not_verified_never_releases_result(self):
        def unsafe_cleanup(argv, **kwargs):
            self.host_calls.append((list(argv), kwargs))
            if argv[1] == "context":
                return subprocess.CompletedProcess(argv, 0,
                    b'"unix:///var/run/docker.sock"', b"")
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        with patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), \
             patch.object(runner.subprocess, "run", side_effect=unsafe_cleanup), \
             patch.object(runner.subprocess, "Popen",
                          side_effect=lambda argv, **kwargs: _FakeProcess(
                              argv, output=json.dumps(self.payload).encode(), **kwargs)):
            with self.assertRaises(runner.IsolationBlocked):
                runner.run_isolated_repo_task(self.source, image=IMAGE, proposal=PROPOSAL)

    def test_stop_before_launch_fails_closed(self):
        stop = threading.Event()
        stop.set()
        with patch.object(runner.shutil, "which") as locate, \
             self.assertRaises(runner.IsolationBlocked):
            runner.run_isolated_repo_task(self.source, image=IMAGE,
                                          proposal=PROPOSAL, cancel_event=stop)
        locate.assert_not_called()

    def test_host_coordinator_only_requests_proposal_then_container(self):
        result = success_packet()
        with patch.object(first_task, "git") as host_git, \
             patch.object(first_task, "run_task") as host_worker, \
             patch.object(first_task, "run_isolated_repo_task",
                          return_value=result) as container:
            evidence = first_task.run_wholly_isolated_task(
                self.source, "fixture:1b", sandbox_image=IMAGE,
                proposer=lambda *_: PROPOSAL)
        host_git.assert_not_called()
        host_worker.assert_not_called()
        container.assert_called_once()
        self.assertFalse(evidence["merge_allowed"])
        self.assertFalse(evidence["host_git_executed"])

    def test_invalid_model_proposal_does_not_touch_container_or_host_git(self):
        with patch.object(first_task, "git") as host_git, \
             patch.object(first_task, "run_isolated_repo_task") as sandbox:
            with self.assertRaises(ValueError):
                first_task.run_wholly_isolated_task(
                    self.source, "fixture:1b", sandbox_image=IMAGE,
                    proposer=lambda *_: {"script": "rm -rf /", "reason": "bad"})
        host_git.assert_not_called()
        sandbox.assert_not_called()


class ContainerEntrypointContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bv-entrypoint-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.git_calls = []
        self.test_calls = []

    def fake_git(self, argv, **kwargs):
        self.git_calls.append(argv)
        if "clone" in argv:
            dest = self.workspace / "checkout"
            dest.mkdir()
            (dest / "package.json").write_text(
                json.dumps({"name": "fixture", "scripts": {
                    "test:unit": entry.UNIT_SCRIPT}}))
        return subprocess.CompletedProcess(argv, 0)

    def fake_output(self, argv, **kwargs):
        if "rev-parse" in argv:
            return "a" * 40
        if "--name-only" in argv:
            return "package.json"
        if "diff" in argv:
            return "diff --git a/package.json b/package.json\n+  test alias"
        raise AssertionError("Unreviewed Git operation")

    def test_isolated_entrypoint_performs_git_edit_diff_and_two_tests(self):
        def test(checkout):
            self.test_calls.append(checkout)
            return 1 if len(self.test_calls) == 1 else 0
        with patch.object(entry, "_run", side_effect=self.fake_git), \
             patch.object(entry, "_output", side_effect=self.fake_output), \
             patch.object(entry, "_test", side_effect=test):
            evidence = entry.execute({"base": "HEAD", "proposal": PROPOSAL},
                                     _test_workspace=self.workspace)
        self.assertEqual(len(self.test_calls), 2)
        self.assertEqual(evidence["status"], "ready_for_human_review")
        self.assertFalse(evidence["merge_allowed"])
        self.assertEqual(evidence["execution_mode"], "full_container")
        package = json.loads(
            (self.workspace / "checkout" / "package.json").read_text())
        self.assertEqual(package["scripts"]["test"], "npm run test:unit")
        self.assertIn("clone", self.git_calls[0])

    def test_wrong_proposal_rejected_before_clone(self):
        with patch.object(entry, "_run") as git:
            with self.assertRaises(ValueError):
                entry.execute({"base": "HEAD", "proposal":
                    {"script": "npm install; arbitrary", "reason": "bad"}},
                    _test_workspace=self.workspace)
        git.assert_not_called()

    def test_unapproved_revision_rejected_before_clone(self):
        with patch.object(entry, "_run") as git:
            with self.assertRaises(ValueError):
                entry.execute({"base": "--exec=sh", "proposal": PROPOSAL},
                              _test_workspace=self.workspace)
        git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
