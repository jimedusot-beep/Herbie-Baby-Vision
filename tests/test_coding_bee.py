"""Offline synthetic safety tests: no Ollama, Docker or generated code executed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'agents' / 'coding_bee.py'
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('coding_bee', SOURCE)
bee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bee)

GOOD_DIFF = ("--- a/src/game.js\n"
             "+++ b/src/game.js\n"
             "@@ -1,3 +1,3 @@\n"
             " export function score(x) {\n"
             "-  return x + 1;\n"
             "+  return x + 2;\n"
             " }\n")


class CodingBeeTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.hive = Path(d.name) / 'hive'
        self.hive.mkdir()
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'TASKS': self.hive / 'tasks', 'PROPOSALS': self.hive / 'proposals',
                           'LOGS': self.hive / 'logs', 'STOP': self.hive / 'STOP'}.items():
            original = getattr(bee, key)
            setattr(bee, key, value)
            self.addCleanup(setattr, bee, key, original)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.repo.joinpath('src').mkdir()
        self.src = self.repo / 'src' / 'game.js'
        self.src.write_text('export function score(x) {\n  return x + 1;\n}\n', encoding='utf-8')
        self.repo.joinpath('.env').write_text('password=something\n')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'synthetic')
        self.git('checkout', '-qb', 'bee/test')
        bee.TASKS.mkdir()
        self.task = bee.TASKS / 'sample.md'
        self.task.write_text('FILES: src/game.js\nCorrect the test scoring adjustment.\n', encoding='utf-8')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def test_valid_source_and_branch(self):
        self.assertEqual(bee.validate_work(), self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(bee.safe_task(self.task)[0], ['src/game.js'])

    def test_valid_diff_is_check_only(self):
        self.assertEqual(bee.validate_diff(GOOD_DIFF, ['src/game.js']), 'src/game.js')
        self.assertIn('return x + 1;', self.src.read_text())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_refuses_unapproved_target(self):
        with self.assertRaises(bee.BeeError):
            bee.validate_diff(GOOD_DIFF, ['src/another.js'])

    def test_refuses_filename_traversal_and_secret_files(self):
        for p in ['../private.py', 'src/../private.py', '.env', 'src/private.key', 'src/space name.js']:
            with self.subTest(p=p):
                self.assertFalse(bee.safe_rel(p))

    def test_refuses_altered_file_metadata_rename_and_binary(self):
        for preamble in ['diff --git a/src/game.js b/src/game.js\n',
                         'rename from src/game.js\n', 'GIT binary patch\n',
                         'new file mode 100644\n']:
            with self.subTest(preamble=preamble), self.assertRaises(bee.BeeError):
                bee.validate_diff(preamble + GOOD_DIFF, ['src/game.js'])

    def test_refuses_wrong_hunk_counts(self):
        with self.assertRaises(bee.BeeError):
            bee.validate_diff(GOOD_DIFF.replace('@@ -1,3 +1,3 @@', '@@ -1,4 +1,3 @@'), ['src/game.js'])

    def test_refuses_uncommitted_worktree(self):
        self.src.write_text('changed uncommitted\n')
        with self.assertRaises(bee.BeeError):
            bee.validate_work()

    def test_refuses_non_bee_branch(self):
        self.git('checkout', '-q', '-b', 'unsafe')
        with self.assertRaises(bee.BeeError):
            bee.validate_work()

    def test_refuses_stopped(self):
        bee.STOP.write_text('disabled\n')
        with self.assertRaises(bee.BeeError):
            bee.validate_work()

    def test_refuses_secret_in_ordinary_source(self):
        secret_file = self.repo / 'src' / 'oops.ts'
        secret_file.write_text('const api_key = "sensitive";\n')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'add synthetic bad source')
        commit = bee.validate_work()
        with self.assertRaises(bee.BeeError):
            bee.get_committed_files(commit, ['src/oops.ts'])

    def test_refuses_task_outside_task_directory(self):
        outside = self.hive / 'random.md'
        outside.write_text('FILES: src/game.js\ntest\n')
        with self.assertRaises(bee.BeeError):
            bee.safe_task(outside)

    def test_proposal_uses_stubbed_model_never_applies(self):
        with patch.object(bee, 'local_ollama', return_value=GOOD_DIFF):
            bee.cmd_propose(types.SimpleNamespace(task=str(self.task), model='qwen2.5-coder:3b'))
        patches = list(bee.PROPOSALS.glob('*.diff'))
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0].read_text(), GOOD_DIFF)
        self.assertIn('return x + 1', self.src.read_text())
        self.assertEqual(self.git('status', '--porcelain'), '')
        events = [json.loads(x) for x in (bee.LOGS / 'audit.jsonl').read_text().splitlines()]
        self.assertNotIn('Correct the test scoring adjustment', json.dumps(events))
        self.assertEqual(events[-1]['event'], 'proposal')

    def test_ollama_address_is_fixed_loopback(self):
        self.assertEqual(bee.OLLAMA_HOST, '127.0.0.1')
        self.assertEqual(bee.OLLAMA_PORT, 11434)

    def test_reject_cloud_model_tag(self):
        with self.assertRaises(bee.BeeError):
            bee.local_ollama('some-cloud-model', 'task', [], 'abc123')

    def test_bounded_diff(self):
        with self.assertRaises(bee.BeeError):
            bee.validate_diff('A' * 20000, ['src/game.js'])


if __name__ == '__main__':
    unittest.main()
