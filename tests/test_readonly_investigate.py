"""Synthetic offline tests: the target repository's code is never executed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / 'agents' / 'readonly_investigate.py'
sys.path.insert(0, str(PATH.parent))
spec = importlib.util.spec_from_file_location('readonly_investigate', PATH)
bee = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bee)


class InvestigatorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.hive = self.root / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        for name, value in {'HIVE': self.hive, 'WORK': self.repo,
                            'STOP': self.hive / 'STOP', 'REPORTS': self.hive / 'proposals',
                            'LOGS': self.hive / 'logs'}.items():
            previous = getattr(bee, name)
            setattr(bee, name, value)
            self.addCleanup(setattr, bee, name, previous)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.repo / 'server').mkdir()
        (self.repo / 'server' / 'room-checkpoints.ts').write_text(
            'export function checkpointRoom(room: string) {\n'
            '  return room.toUpperCase(); // recovery checkpoint\n'
            '}\n')
        (self.repo / 'server' / 'secrets.ts').write_text('const api_key = "NEVER_SHOW";\n')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
        self.git('switch', '-qc', 'bee/test')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def sample(self):
        return {'summary': 'Code uppercases room IDs.', 'suspected_cause': 'Could normalize unexpectedly.',
                'suggested_change': 'Review normalization needs.', 'confidence': 'low',
                'citations': [{'path': 'server/room-checkpoints.ts', 'line': 2}]}

    def test_evidence_has_real_lines_and_commit(self):
        result = bee.evidence('recovery checkpoint')
        self.assertEqual(result['commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertIn('server/room-checkpoints.ts', result['source_paths'])
        self.assertTrue(all(x['line'] > 0 for x in result['evidence']))
        self.assertNotIn('NEVER_SHOW', json.dumps(result))
        self.assertFalse(result['partial_scan'])

    def test_model_response_with_grounded_citation(self):
        report = bee.investigate('recovery checkpoint', 'qwen2.5-coder:1.5b',
                                 ask=lambda model, src: json.dumps(self.sample()))
        self.assertEqual(report['analysis']['citations'][0]['line'], 2)
        self.assertFalse(report['partial_scan'])
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_invented_line_rejected(self):
        fake = self.sample()
        fake['citations'][0]['line'] = 999
        with self.assertRaisesRegex(bee.InvestigationError, 'invented'):
            bee.investigate('recovery checkpoint', 'qwen2.5-coder:1.5b',
                            ask=lambda model, src: json.dumps(fake))

    def test_model_non_json_rejected(self):
        with self.assertRaisesRegex(bee.InvestigationError, 'valid JSON'):
            bee.investigate('recovery checkpoint', 'qwen2.5-coder:1.5b',
                            ask=lambda model, src: 'Run this shell script')

    def test_block_dirty_and_unsafe_branch(self):
        (self.repo / 'new.txt').write_text('worktree')
        with self.assertRaises(bee.InvestigationError):
            bee.evidence('recovery checkpoint')
        (self.repo / 'new.txt').unlink()
        self.git('switch', '-qc', 'main-other')
        with self.assertRaises(bee.InvestigationError):
            bee.evidence('recovery checkpoint')

    def test_stop_prevents_scan_and_report(self):
        bee.STOP.write_text('disabled\n')
        with self.assertRaises(bee.InvestigationError):
            bee.evidence('recovery checkpoint')

    def test_secret_question_rejected(self):
        with self.assertRaises(bee.InvestigationError):
            bee.evidence('Find api_key in source')

    def test_does_not_send_secret_file_to_model(self):
        with self.assertRaisesRegex(bee.InvestigationError, 'No sufficiently safe'):
            bee.evidence('NEVER_SHOW')

    def test_report_log_contains_hashes_not_source(self):
        report = bee.investigate('recovery checkpoint', 'qwen2.5-coder:1.5b',
                                 ask=lambda model, src: json.dumps(self.sample()))
        name = bee.save_report(report, 'qwen2.5-coder:1.5b')
        self.assertTrue((bee.REPORTS / name).exists())
        audit = (bee.LOGS / 'audit.jsonl').read_text()
        self.assertNotIn('room.toUpperCase', audit)
        self.assertNotIn('recovery checkpoint', audit)

    def test_local_model_allowlist(self):
        with self.assertRaises(bee.InvestigationError):
            bee._ask_local('cloud-model', {})


if __name__ == '__main__':
    unittest.main()
