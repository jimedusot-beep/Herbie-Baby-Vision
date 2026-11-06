"""Synthetic STOP regression for the trusted worker stage boundary.

Runs only an in-test generated Git/Node fixture. No AI, private code, remote
services or untrusted repositories. A running OS subprocess is NOT preempted.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from first_task import TaskCancelled, run_task, require_active


class StopBoundaryTests(unittest.TestCase):
    def test_stop_set_before_task_does_not_open_git_or_execute_commands(self):
        stop = threading.Event()
        stop.set()
        with patch("first_task.git") as git_cmd, self.assertRaises(TaskCancelled):
            run_task("not-a-repository", "fixture:1b", cancel_event=stop)
        git_cmd.assert_not_called()

    def test_stop_set_by_proposer_discards_patch_before_post_edit_tests(self):
        with tempfile.TemporaryDirectory(prefix="bv-stop-fixture-") as tmp:
            repo = Path(tmp) / "fixture"
            repo.mkdir()
            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True,
                               capture_output=True, text=True)
            git("init", "-q")
            git("config", "user.name", "Synthetic fixture")
            git("config", "user.email", "fixture@example.invalid")
            package = json.dumps({"name": "bv-stop-fixture", "private": True,
                "scripts": {"test:unit": "node --test tests/*.test.cjs"}},
                indent=2) + "\n"
            (repo / "package.json").write_text(package)
            tests = repo / "tests"
            tests.mkdir()
            (tests / "basic.test.cjs").write_text(
                "const {test}=require('node:test');"
                "test('fixture',()=>{});\n")
            git("add", ".")
            git("commit", "-qm", "Trusted generated fixture")
            stop = threading.Event()
            calls = []
            def proposer(model, base_url, timeout):
                calls.append("inference")
                stop.set()
                return {"script": "npm run test:unit", "reason": "Approved alias."}
            with self.assertRaises(TaskCancelled):
                run_task(repo, "fixture:1b", proposer=proposer, cancel_event=stop)
            self.assertEqual(calls, ["inference"])
            self.assertEqual((repo / "package.json").read_text(), package)
            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(status.stdout.strip(), "")

    def test_invalid_cancel_signal_is_rejected(self):
        with self.assertRaises(TypeError):
            require_active(object())


if __name__ == "__main__":
    unittest.main()
