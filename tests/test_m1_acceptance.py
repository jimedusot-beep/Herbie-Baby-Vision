"""M1 acceptance: source search -> simulated investigation -> valid review-only diff.

This is a synthetic Git fixture, NOT an Ollama, ZBook or real app execution test.
No production code is applied, no tests run against target checkout, and no signing
service is launched. These tests exercise the existing V0.4.4 components together.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import proposal_bridge as bridge

TARGET = 'server/room-checkpoints.ts'
SOURCE = ('export function checkpointRoom(room: string) {\n'
          '  return room.toUpperCase(); // recovery checkpoint\n'
          '}\n')
PATCH = (f'--- a/{TARGET}\n+++ b/{TARGET}\n'
         '@@ -1,3 +1,3 @@\n'
         ' export function checkpointRoom(room: string) {\n'
         '-  return room.toUpperCase(); // recovery checkpoint\n'
         '+  return room.trim().toUpperCase(); // recovery checkpoint\n'
         ' }\n')


class M1EndToEndAcceptance(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.hive = Path(temp.name) / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        (self.repo / 'server').mkdir(parents=True)
        self.target = self.repo / TARGET
        self.target.write_text(SOURCE, encoding='utf-8')
        # Create more than the old 400-file cap; committed source is still small.
        for n in range(410):
            (self.repo / f'module-{n:04d}.ts').write_text(f'export const module{n} = {n};\n')
        self.git('init', '-q')
        self.git('config', 'user.name', 'M1 fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'synthetic fixture')
        self.git('switch', '-qc', 'bee/m1')
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'STOP': self.hive / 'STOP',
                           'REPORTS': self.hive / 'proposals',
                           'LOGS': self.hive / 'logs'}.items():
            obj = bridge.investigation
            old = getattr(obj, key)
            setattr(obj, key, value)
            self.addCleanup(setattr, obj, key, old)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, timeout=15).stdout.strip()

    def investigate(self, model, context):
        self.assertEqual(model, 'qwen2.5-coder:1.5b')
        self.assertEqual(context['commit'], self.git('rev-parse', 'HEAD'))
        self.assertFalse(context['partial_scan'], 'M1 fixture must be fully scanned')
        self.assertGreater(context['searched_files'], 400)
        self.assertTrue(any(h['path'] == TARGET and h['line'] == 2
                            for h in context['evidence']))
        return json.dumps({'summary': 'Room ID uppercased',
                           'suspected_cause': 'Whitespace may survive',
                           'suggested_change': 'Trim room ID first',
                           'confidence': 'medium',
                           'citations': [{'path': TARGET, 'line': 2}]})

    def propose_patch(self, model, task, path, source):
        self.assertEqual(model, 'qwen2.5-coder:1.5b')
        self.assertEqual(path, TARGET)
        self.assertIn('room.toUpperCase()', source)
        return PATCH

    def make_proposal(self, investigator=None, writer=None):
        return bridge.propose('recovery checkpoint',
                              investigator=investigator or self.investigate,
                              writer=writer or self.propose_patch)

    def test_one_complete_review_only_workflow(self):
        before = self.git('rev-parse', 'HEAD')
        result = self.make_proposal()
        self.assertEqual(result['source_commit'], before)
        self.assertEqual(result['target'], TARGET)
        self.assertEqual(hashlib.sha256(PATCH.encode()).hexdigest(), result['diff_sha256'])
        self.assertFalse(result['partial_scan'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        name = bridge.save(result)
        proposal_dir = self.hive / 'proposals'
        self.assertEqual((proposal_dir / f'{name}.diff').read_text(), PATCH)
        evidence = json.loads((proposal_dir / f'{name}.json').read_text())
        self.assertEqual(evidence['diff_sha256'], result['diff_sha256'])
        self.assertEqual(evidence['source_commit'], before)
        self.assertEqual(self.target.read_text(), SOURCE)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertFalse((self.hive / 'approvals').exists())
        self.assertFalse((self.hive / 'logs').exists())

    def test_refuse_invented_citation(self):
        def invented(model, context):
            result = json.loads(self.investigate(model, context))
            result['citations'][0]['line'] = 999
            return json.dumps(result)
        with self.assertRaises(bridge.ProposalError):
            self.make_proposal(investigator=invented)
        self.assertFalse((self.hive / 'proposals').exists())

    def test_refuse_model_declines_to_propose(self):
        with self.assertRaises(bridge.ProposalError):
            self.make_proposal(writer=lambda *_: 'CANNOT_PROPOSE')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_refuse_stale_source_after_model_response(self):
        def change_source(*_):
            self.target.write_text('unexpected local modification\n')
            return PATCH
        with self.assertRaises(bridge.ProposalError):
            self.make_proposal(writer=change_source)
        self.assertFalse((self.hive / 'proposals').exists())

    def test_stop_after_proposal_prevents_save(self):
        result = self.make_proposal()
        (self.hive / 'STOP').write_text('STOP')
        with self.assertRaises(bridge.ProposalError):
            bridge.save(result)
        self.assertFalse((self.hive / 'proposals').exists())

    def test_refuse_redirected_proposal_folder(self):
        result = self.make_proposal()
        (self.hive / 'proposals').symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(bridge.ProposalError):
            bridge.save(result)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_refuse_malformed_patch(self):
        with self.assertRaises(bridge.ProposalError):
            self.make_proposal(writer=lambda *_: PATCH.replace(
                '+++ b/server/room-checkpoints.ts', '+++ b/../outside.ts'))
        self.assertEqual(self.git('status', '--porcelain'), '')


if __name__ == '__main__':
    unittest.main()
