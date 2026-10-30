"""Exercise real disposable snapshots and fail-closed coordinator reports."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('coordinator', Path(__file__).resolve().parents[1] / 'agents/validate_repositories.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CoordinatorTests(unittest.TestCase):
    def fixture(self, root, body='self.assertEqual(2+2, 4)'):
        repo = Path(root) / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / 'tests').mkdir()
        (repo / 'tests/test_sample.py').write_text('import unittest\nclass Sample(unittest.TestCase):\n def test_sample(self):\n  ' + body + '\n')
        c.git(repo, 'add', '.')
        c.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        return repo

    def test_success_preserves_dirty_source_and_reports_no_logs(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            (repo / 'local-private.txt').write_text('PRIVATE_SENTINEL')
            before = c.git(repo, 'status', '--porcelain')
            result = c.validate(repo, 'hardware', trusted=True)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(c.git(repo, 'status', '--porcelain'), before)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
            self.assertFalse(result['merge_allowed'])
            self.assertTrue(all(value == 'unverified' for value in result['capabilities'].values()))

    def test_failure_and_output_do_not_leak_into_report(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root, "self.fail('PRIVATE_SENTINEL')")
            result = c.validate(repo, 'hardware', trusted=True)
            self.assertEqual(result['status'], 'failed')
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_no_trust_or_unknown_profile_never_executes(self):
        with patch.object(c, 'snapshot') as snapshot:
            self.assertEqual(c.validate('/missing', 'hardware')['status'], 'blocked')
            self.assertEqual(c.validate('/missing', 'arbitrary', trusted=True)['status'], 'blocked')
            snapshot.assert_not_called()

    def test_missing_revision_blocks_and_next_run_recovers(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            self.assertEqual(c.validate(repo, 'hardware', 'missing', trusted=True)['status'], 'blocked')
            self.assertEqual(c.validate(repo, 'hardware', trusted=True)['status'], 'completed')

    def test_timeout_cleans_snapshot_and_next_run_recovers(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            paths = []
            def timeout(command, checkout, seconds):
                paths.append(checkout)
                raise subprocess.TimeoutExpired(command, seconds)
            with patch.object(c, 'execute', side_effect=timeout):
                result = c.validate(repo, 'hardware', trusted=True)
            self.assertEqual(result['reason'], 'timeout')
            self.assertFalse(paths[0].exists())
            self.assertEqual(c.validate(repo, 'hardware', trusted=True)['status'], 'completed')

    def test_links_to_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            (repo / 'escape').symlink_to(repo)
            c.git(repo, 'add', 'escape')
            c.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'link')
            self.assertEqual(c.validate(repo, 'hardware', trusted=True)['status'], 'blocked')

    def test_no_tests_blocks_instead_of_passing(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            self.assertEqual(c.validate(repo, 'vision', trusted=True)['reason'], 'no_tests')

    def test_process_environment_drops_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            checkout = Path(root) / 'checkout'
            checkout.mkdir()
            with patch.dict(os.environ, {'GITHUB_TOKEN': 'PRIVATE_SENTINEL', 'PYTHONPATH': '/private'}):
                code = c.execute([c.sys.executable, '-c',
                    "import os; assert 'GITHUB_TOKEN' not in os.environ; assert 'PYTHONPATH' not in os.environ"], checkout, 5)
            self.assertEqual(code, 0)

    def test_permission_denial_is_blocked_without_raw_error(self):
        with patch.object(c, 'snapshot', side_effect=PermissionError('PRIVATE_SENTINEL')):
            result = c.validate('/private', 'hardware', trusted=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_runtime_dependencies_block_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self.fixture(root)
            (repo / 'package.json').write_text(json.dumps({'dependencies': {'three': '0.180.0'}}))
            c.git(repo, 'add', '.')
            c.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'dependencies')
            with patch.object(c, 'execute') as execute:
                result = c.validate(repo, 'vision', trusted=True)
            self.assertEqual(result['reason'], 'dependencies_not_provisioned')
            execute.assert_not_called()

    def test_real_timeout_kills_process(self):
        with tempfile.TemporaryDirectory() as root:
            checkout = Path(root) / 'checkout'
            checkout.mkdir()
            with self.assertRaises(subprocess.TimeoutExpired):
                c.execute([c.sys.executable, '-c', 'import time; time.sleep(30)'], checkout, .1)


if __name__ == '__main__':
    unittest.main()
