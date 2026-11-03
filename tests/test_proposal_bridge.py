"""Offline regression checks; stub both model calls, use synthetic Git repo only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import proposal_bridge as bridge

PATCH = ('--- a/server/room-checkpoints.ts\n'
         '+++ b/server/room-checkpoints.ts\n'
         '@@ -1,3 +1,3 @@\n'
         ' export function checkpointRoom(room: string) {\n'
         '-  return room.toUpperCase(); // recovery checkpoint\n'
         '+  return room.trim().toUpperCase(); // recovery checkpoint\n'
         ' }\n')


class BridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.hive = Path(temp.name) / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        self.file = self.repo / 'server' / 'room-checkpoints.ts'
        self.file.parent.mkdir()
        self.file.write_text('export function checkpointRoom(room: string) {\n'
                             '  return room.toUpperCase(); // recovery checkpoint\n'
                             '}\n')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
        self.git('switch', '-qc', 'bee/test')
        investigation = bridge.investigation
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'STOP': self.hive / 'STOP', 'REPORTS': self.hive / 'proposals',
                           'LOGS': self.hive / 'logs'}.items():
            old = getattr(investigation, key)
            setattr(investigation, key, value)
            self.addCleanup(setattr, investigation, key, old)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args],
                              text=True, capture_output=True, check=True).stdout.strip()

    def ask(self, model, evidence):
        self.assertEqual(model, 'qwen2.5-coder:1.5b')
        return json.dumps({'summary': 'Code uppercases room IDs.',
                           'suspected_cause': 'Whitespace could prevent matching.',
                           'suggested_change': 'Trim before uppercasing.',
                           'confidence': 'medium',
                           'citations': [{'path': 'server/room-checkpoints.ts', 'line': 2}]})

    def write(self, model, task, path, source):
        self.assertEqual(path, 'server/room-checkpoints.ts')
        self.assertIn('room.toUpperCase', source)
        self.assertEqual(task['citations'][0]['line'], 2)
        return PATCH

    def test_proposal_never_modifies_source(self):
        result = bridge.propose('recovery checkpoint', investigator=self.ask, writer=self.write)
        self.assertEqual(result['target'], 'server/room-checkpoints.ts')
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertFalse((self.hive / 'proposals').exists())

    def test_save_is_review_only_and_outside_git(self):
        result = bridge.propose('recovery checkpoint', investigator=self.ask, writer=self.write)
        name = bridge.save(result)
        self.assertEqual((self.hive / 'proposals' / (name + '.diff')).read_text(), PATCH)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(json.loads((self.hive / 'proposals' / (name + '.json')).read_text())['source_commit'], self.git('rev-parse', 'HEAD'))

    def test_reject_invented_citation(self):
        def invented(model, evidence):
            data = json.loads(self.ask(model, evidence)); data['citations'][0]['line'] = 999
            return json.dumps(data)
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=invented, writer=self.write)

    def test_reject_low_confidence(self):
        def low(model, evidence):
            data = json.loads(self.ask(model, evidence)); data['confidence'] = 'low'
            return json.dumps(data)
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=low, writer=self.write)

    def test_reject_other_file_and_metadata(self):
        for bad in [PATCH.replace('room-checkpoints.ts', 'other.ts'),
                    'rename from server/room-checkpoints.ts\n' + PATCH,
                    'GIT binary patch\n' + PATCH,
                    'new file mode 100644\n' + PATCH]:
            with self.subTest(bad=bad[:32]), self.assertRaises(bridge.ProposalError):
                bridge.propose('recovery checkpoint', investigator=self.ask,
                               writer=lambda *args: bad)

    def test_reject_wrong_hunk_count(self):
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=self.ask,
                           writer=lambda *args: PATCH.replace('@@ -1,3 +1,3 @@', '@@ -1,4 +1,3 @@'))

    def test_refuse_stop_file(self):
        (self.hive / 'STOP').write_text('stop')
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=self.ask, writer=self.write)

    def test_refuse_stale_worktree_after_model(self):
        def changed(*args):
            self.file.write_text('changed\n')
            return PATCH
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=self.ask, writer=changed)

    def test_refuse_model_declined(self):
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=self.ask,
                           writer=lambda *args: 'CANNOT_PROPOSE')

    def test_refuse_sensitive_advisory(self):
        def sensitive(model, evidence):
            data = json.loads(self.ask(model, evidence)); data['suggested_change'] = 'Use api_key from settings'
            return json.dumps(data)
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', investigator=sensitive, writer=self.write)

    def test_refuse_cloud_model(self):
        with self.assertRaises(bridge.ProposalError):
            bridge.propose('recovery checkpoint', model='cloud', investigator=self.ask, writer=self.write)


if __name__ == '__main__':
    unittest.main()
