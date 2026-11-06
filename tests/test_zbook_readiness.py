"""Synthetic ZBook readiness tests: never connect to or run real Ollama."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "zbook_readiness_tests", ROOT / "scripts" / "zbook_readiness.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ZBookReadinessTests(unittest.TestCase):
    def readiness(self, **overrides):
        options = dict(
            root=ROOT, platform="win32", version=(3, 12),
            find_program=lambda executable: "synthetic-found",
            fetch_tags=lambda: {"gemma3:1b"},
        )
        options.update(overrides)
        return probe.readiness("gemma3:1b", **options)

    def test_reviewed_baby_vision_files_match_pins(self):
        self.assertTrue(probe.sources_match(ROOT))
        self.assertEqual(len(probe.EXPECTED_BLOBS), 4)

    def test_ready_is_readiness_only_and_does_not_certify_model_execution(self):
        result = self.readiness()
        self.assertEqual(result["status"], "ready_for_manual_smoke")
        self.assertFalse(result["inference_performed"])
        self.assertFalse(result["code_executed"])
        self.assertFalse(result["merge_allowed"])

    def test_non_windows_blocks_without_local_model_query(self):
        requests = []
        result = self.readiness(platform="linux",
                                fetch_tags=lambda: requests.append("called"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(requests, [])

    def test_python_mismatch_and_missing_tools_block_without_network(self):
        requests = []
        self.assertEqual(self.readiness(
            version=(3, 13), fetch_tags=lambda: requests.append(1),
        )["checks"]["python_3_12"], "blocked")
        self.assertEqual(self.readiness(
            find_program=lambda _: None,
            fetch_tags=lambda: requests.append(1),
        )["status"], "blocked")
        self.assertEqual(requests, [])

    def test_uninstalled_model_tag_is_reported_without_listing_other_models(self):
        result = self.readiness(fetch_tags=lambda: {"qwen2.5-coder:1.5b"})
        self.assertEqual(result["checks"]["model_tag"], "not_installed")
        self.assertNotIn("qwen2.5", json.dumps(result))

    def test_invalid_model_and_unavailable_ollama_fail_closed(self):
        result = probe.readiness(
            "http://attacker.invalid", root=ROOT, platform="win32",
            version=(3, 12), find_program=lambda _: "yes",
            fetch_tags=lambda: {"gemma3:1b"},
        )
        self.assertEqual(result["checks"]["model_tag"], "invalid")
        result = self.readiness(fetch_tags=lambda:
                                (_ for _ in ()).throw(probe.PreflightBlocked("synthetic")))
        self.assertEqual(result["checks"]["model_tag"], "unavailable")

    def test_tags_only_use_fixed_loopback_get_and_no_proxy(self):
        accessed = []
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, n): return b'{"models":[{"name":"gemma3:1b"}]}'
        class FakeOpener:
            def open(self, request, timeout):
                accessed.append((request.full_url, request.get_method(), timeout))
                return Response()
        with patch.object(urllib.request, "build_opener", return_value=FakeOpener()) as build:
            self.assertEqual(probe.local_model_tags(), {"gemma3:1b"})
        self.assertEqual(accessed, [("http://127.0.0.1:11434/api/tags", "GET", 4)])
        self.assertIsInstance(build.call_args.args[0], urllib.request.ProxyHandler)
        self.assertIsInstance(build.call_args.args[1], probe._NoRedirect)

    def test_oversized_or_malformed_model_list_blocks(self):
        for raw in (b'{"models":"bad"}', b'{"models":[{}]}',
                    b'{"models":[{"name":"bad tag"}]}', b'{"models":[1]}',
                    b'x' * (probe.MAX_TAG_BYTES + 1)):
            class Response:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *_): return None
                def read(self, n): return raw
            class FakeOpener:
                def open(self, request, timeout): return Response()
            with patch.object(urllib.request, "build_opener", return_value=FakeOpener()):
                with self.assertRaises(probe.PreflightBlocked):
                    probe.local_model_tags()

    def test_modified_reviewed_source_blocks_without_import_or_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for rel in probe.EXPECTED_BLOBS:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / rel).read_bytes())
            self.assertTrue(probe.sources_match(root))
            (root / "agents" / "first_task.py").write_text(
                "raise RuntimeError('MUST_NOT_EXECUTE')\n"
            )
            self.assertFalse(probe.sources_match(root))
            self.assertEqual(self.readiness(root=root)["status"], "blocked")

    def test_launcher_runs_preflight_before_real_model_smoke(self):
        launch = (ROOT / "scripts" / "run_zbook_local_smoke.cmd").read_text()
        self.assertIn("scripts\\zbook_readiness.py", launch)
        self.assertLess(launch.index("scripts\\zbook_readiness.py"),
                        launch.index("--run-live"))
        self.assertIn("if errorlevel 1 (", launch)

    def test_source_has_no_model_generation_or_code_execution_calls(self):
        source = (ROOT / "scripts" / "zbook_readiness.py").read_text()
        self.assertNotIn("/api/chat", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn("os.system(", source)


if __name__ == "__main__":
    unittest.main()
