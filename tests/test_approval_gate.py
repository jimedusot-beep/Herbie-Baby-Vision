"""V0.4 synthetic approval workflow tests; no models, Docker or target writes."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import approval_gate as gate

SOURCE = ('export function checkpointRoom(room: string) {\n'
          '  return room.toUpperCase(); // recovery checkpoint\n'
          '}\n')
PATCH = ('--- a/server/room-checkpoints.ts\n'
         '+++ b/server/room-checkpoints.ts\n'
         '@@ -1,3 +1,3 @@\n'
         ' export function checkpointRoom(room: string) {\n'
         '-  return room.toUpperCase(); // recovery checkpoint\n'
         '+  return room.trim().toUpperCase(); // recovery checkpoint\n'
         ' }\n')


class ApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hive = Path(self.temp.name) / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        self.file = self.repo / 'server' / 'room-checkpoints.ts'
        self.file.parent.mkdir()
        self.file.write_text(SOURCE, encoding='utf-8')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
        self.git('switch', '-qc', 'bee/test')
        self.commit = self.git('rev-parse', 'HEAD')
        investigation = gate.bridge.investigation
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'STOP': self.hive / 'STOP', 'REPORTS': self.hive / 'proposals',
                           'LOGS': self.hive / 'logs'}.items():
            old = getattr(investigation, key)
            setattr(investigation, key, value)
            self.addCleanup(setattr, investigation, key, old)
        (self.hive / 'proposals').mkdir()
        self.name = 'guided-20261102T170000Z-abc123abc123'
        self.report_path = self.hive / 'proposals' / (self.name + '.json')
        self.diff_path = self.hive / 'proposals' / (self.name + '.diff')
        self.diff_path.write_text(PATCH, encoding='utf-8')
        self.report = {'source_commit': self.commit, 'diff_sha256': hashlib.sha256(PATCH.encode()).hexdigest(),
                       'target': 'server/room-checkpoints.ts', 'partial_scan': False,
                       'model': 'qwen2.5-coder:1.5b', 'query': 'checkpoint recovery'}
        self.save_report()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args],
                              text=True, capture_output=True, check=True).stdout.strip()

    def save_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding='utf-8')

    def permit(self, action='apply_disposable_patch'):
        result = gate.inspect(self.name)
        return gate.issue(self.name, action,
                          typed=f'APPROVE {gate.ACTIONS[action]} {result["diff_sha256"][:12]}',
                          terminal=True)

    def test_review_does_not_modify_target_or_create_approval(self):
        result = gate.inspect(self.name)
        self.assertEqual(result['source_commit'], self.commit)
        self.assertEqual(result['target'], 'server/room-checkpoints.ts')
        self.assertFalse((self.hive / 'approvals').exists())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_apply_and_test_approvals_are_independent(self):
        self.permit()
        gate.verify(self.name, 'apply_disposable_patch')
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'run_isolated_tests')
        self.permit('run_isolated_tests')
        gate.verify(self.name, 'run_isolated_tests')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_bad_confirmation_and_noninteractive_refuse(self):
        with self.assertRaises(gate.ApprovalError):
            gate.issue(self.name, 'apply_disposable_patch', typed='APPROVE', terminal=True)
        with self.assertRaises(gate.ApprovalError):
            gate.issue(self.name, 'apply_disposable_patch', typed='APPROVE APPLY ' + self.report['diff_sha256'][:12], terminal=False)
        self.assertFalse((self.hive / 'approvals').exists())

    def test_reject_unknown_action(self):
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'git_push')

    def test_prevent_duplicate_and_one_time_consume(self):
        self.permit()
        with self.assertRaises(gate.ApprovalError):
            self.permit()
        gate.consume(self.name, 'apply_disposable_patch')
        with self.assertRaises(gate.ApprovalError):
            gate.consume(self.name, 'apply_disposable_patch')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_tampered_diff_invalidates_decision(self):
        self.permit()
        self.diff_path.write_text(PATCH.replace('trim().toUpperCase', 'trimEnd().toUpperCase'))
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')

    def test_tampered_report_invalidates_decision(self):
        self.permit()
        self.report['query'] = 'different task'
        self.save_report()
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')

    def test_stale_commit_rejected(self):
        self.permit()
        self.file.write_text(SOURCE + '// updated\n')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'new source')
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')

    def test_dirty_worktree_rejected(self):
        self.permit()
        self.file.write_text('changed\n')
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')

    def test_stop_blocks_approval_and_verification(self):
        self.permit()
        (self.hive / 'STOP').write_text('halt\n')
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')
        with self.assertRaises(gate.ApprovalError):
            self.permit('run_isolated_tests')

    def test_revoke_blocks_all_actions(self):
        self.permit()
        gate.close(self.name, 'revoked')
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')
        with self.assertRaises(gate.ApprovalError):
            self.permit('run_isolated_tests')

    def test_reject_blocks_new_approval(self):
        gate.close(self.name, 'rejected')
        with self.assertRaises(gate.ApprovalError):
            self.permit()

    def test_expired_record_is_invalid(self):
        self.permit()
        path = gate._record_path(self.name, 'apply_disposable_patch')
        value = json.loads(path.read_text())
        value['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        path.write_text(json.dumps(value))
        with self.assertRaises(gate.ApprovalError):
            gate.verify(self.name, 'apply_disposable_patch')

    def test_path_traversal_rejected(self):
        for name in ['../../etc/passwd', self.name + '/..', 'other.json', '/tmp/x']:
            with self.subTest(name=name), self.assertRaises(gate.ApprovalError):
                gate.inspect(name)

    def test_proposal_symlink_rejected(self):
        self.diff_path.unlink()
        elsewhere = Path(self.temp.name) / 'outside.diff'
        elsewhere.write_text(PATCH)
        self.diff_path.symlink_to(elsewhere)
        with self.assertRaises(gate.ApprovalError):
            gate.inspect(self.name)

    def test_control_directory_symlink_rejected(self):
        elsewhere = Path(self.temp.name) / 'control'
        elsewhere.mkdir()
        (self.hive / 'approvals').symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(gate.ApprovalError):
            gate.inspect(self.name)

    def test_malformed_patch_refused(self):
        self.diff_path.write_text('GIT binary patch\n')
        self.report['diff_sha256'] = hashlib.sha256(self.diff_path.read_bytes()).hexdigest()
        self.save_report()
        with self.assertRaises(gate.ApprovalError):
            gate.inspect(self.name)

    def test_no_execution_tools_imported(self):
        src = Path(gate.__file__).read_text()
        self.assertNotIn('docker run', src)
        self.assertNotIn('git apply -', src)
        self.assertEqual(self.git('status', '--porcelain'), '')


if __name__ == '__main__':
    unittest.main()
