"""V0.4.1 adversarial filesystem and malformed-citation tests. No model/network."""
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
import artifact_io
import readonly_investigate as investigation
import proposal_bridge as bridge
import coding_bee
import approval_gate

PATCH = ("--- a/server/room-checkpoints.ts\n+++ b/server/room-checkpoints.ts\n"
         "@@ -1,1 +1,1 @@\n-old\n+new\n")


class HardeningTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.hive = Path(temp.name) / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        self.outside = Path(temp.name) / 'outside'
        self.outside.mkdir()
        self.canary = self.repo / 'canary.txt'
        self.canary.write_text('original\n', encoding='utf-8')
        for module in (investigation, coding_bee):
            for attr, value in ({'HIVE': self.hive, 'WORK': self.repo,
                        'STOP': self.hive / 'STOP', 'REPORTS': self.hive / 'proposals',
                        'LOGS': self.hive / 'logs'} if module is investigation else
                        {'HIVE': self.hive, 'WORK': self.repo, 'STOP': self.hive / 'STOP',
                         'PROPOSALS': self.hive / 'proposals', 'LOGS': self.hive / 'logs'}).items():
                if hasattr(module, attr):
                    original = getattr(module, attr)
                    setattr(module, attr, value)
                    self.addCleanup(setattr, module, attr, original)

    def test_nonstring_and_noninteger_citations_fail_cleanly(self):
        source = {'evidence': [{'path': 'server/room-checkpoints.ts', 'line': 4}]}
        base = {'summary': 's', 'suspected_cause': 'c', 'suggested_change': 'x',
                'confidence': 'medium', 'citations': [{'path': 'server/room-checkpoints.ts', 'line': 4}]}
        self.assertEqual(investigation.validate_report(json.dumps(base), source)['confidence'], 'medium')
        for path, line in [([], 4), ({'unsafe': True}, 4), ('server/room-checkpoints.ts', []),
                           ('server/room-checkpoints.ts', {}), ('server/room-checkpoints.ts', True),
                           ('server/room-checkpoints.ts', 0), ('server/room-checkpoints.ts', 4.0)]:
            with self.subTest(path=path, line=line):
                sample = dict(base, citations=[{'path': path, 'line': line}])
                with self.assertRaises(investigation.InvestigationError):
                    investigation.validate_report(json.dumps(sample), source)

    def test_guided_proposal_fails_closed_if_proposals_symlink_into_repo(self):
        (self.hive / 'proposals').symlink_to(self.repo, target_is_directory=True)
        result = {'source_commit': 'a' * 40, 'diff': PATCH,
                  'diff_sha256': hashlib.sha256(PATCH.encode()).hexdigest(),
                  'target': 'server/room-checkpoints.ts'}
        with patch.object(investigation, 'check_work', return_value='a' * 40), \
             patch.object(bridge, 'validate_patch', return_value='server/room-checkpoints.ts'):
            with self.assertRaises(bridge.ProposalError):
                bridge.save(result)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['canary.txt'])

    def test_guided_proposal_fails_closed_if_proposals_symlink_outside(self):
        (self.hive / 'proposals').symlink_to(self.outside, target_is_directory=True)
        result = {'source_commit': 'a' * 40, 'diff': PATCH,
                  'diff_sha256': hashlib.sha256(PATCH.encode()).hexdigest(),
                  'target': 'server/room-checkpoints.ts'}
        with patch.object(investigation, 'check_work', return_value='a' * 40), \
             patch.object(bridge, 'validate_patch', return_value='server/room-checkpoints.ts'):
            with self.assertRaises(bridge.ProposalError):
                bridge.save(result)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_investigation_report_does_not_follow_symlinked_logs(self):
        (self.hive / 'logs').symlink_to(self.repo, target_is_directory=True)
        report = {'source_commit': 'a' * 40, 'query': 'test'}
        with self.assertRaises(investigation.InvestigationError):
            investigation.save_report(report, 'qwen2.5-coder:1.5b')
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['canary.txt'])
        self.assertFalse((self.hive / 'proposals').exists() and any((self.hive / 'proposals').iterdir()))

    def test_investigation_report_does_not_follow_symlinked_proposals(self):
        (self.hive / 'proposals').symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(investigation.InvestigationError):
            investigation.save_report({'source_commit': 'a'*40}, 'qwen2.5-coder:1.5b')
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['canary.txt'])

    def test_coding_bee_proposal_does_not_follow_symlinked_proposals(self):
        (self.hive / 'proposals').symlink_to(self.repo, target_is_directory=True)
        with patch.object(coding_bee, 'validate_work', return_value='a'*40), \
             patch.object(coding_bee, 'safe_task', return_value=(['server/room-checkpoints.ts'], 'task')), \
             patch.object(coding_bee, 'get_committed_files', return_value=[('server/room-checkpoints.ts', 'old')]), \
             patch.object(coding_bee, 'local_ollama', return_value=PATCH), \
             patch.object(coding_bee, 'validate_diff', return_value='server/room-checkpoints.ts'), \
             patch.object(coding_bee, 'audit'):
            with self.assertRaises(artifact_io.ArtifactError):
                coding_bee.cmd_propose(type('Args', (), {'task': 'task', 'model':'qwen2.5-coder:1.5b'})())
        self.assertEqual(self.canary.read_text(), 'original\n')

    def test_symlinked_log_file_rejected(self):
        logs = self.hive / 'logs'
        logs.mkdir()
        (logs / 'audit.jsonl').symlink_to(self.canary)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.append_log(self.hive, 'audit.jsonl', b'{"event":"test"}\n')
        self.assertEqual(self.canary.read_text(), 'original\n')

    def test_hardlinked_log_file_rejected(self):
        logs = self.hive / 'logs'
        logs.mkdir()
        try:
            os.link(self.canary, logs / 'audit.jsonl')
        except (OSError, NotImplementedError):
            self.skipTest('Hard links unavailable on this filesystem')
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.append_log(self.hive, 'audit.jsonl', b'{"event":"test"}\n')
        self.assertEqual(self.canary.read_text(), 'original\n')

    def test_exclusive_artifact_ignores_symlink_target(self):
        prop = self.hive / 'proposals'
        prop.mkdir()
        (prop / 'test.json').symlink_to(self.canary)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.write_exclusive(self.hive, 'proposals', 'test.json', b'written')
        self.assertEqual(self.canary.read_text(), 'original\n')

    def test_no_parent_or_nested_path_segments(self):
        for name in ['../escape.json', '/tmp/out', 'sub/report.json', '..', '.']:
            with self.subTest(name=name), self.assertRaises(artifact_io.ArtifactError):
                artifact_io.write_exclusive(self.hive, 'proposals', name, b'a')

    def test_approval_records_use_guarded_writer(self):
        (self.hive / 'approvals').symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(approval_gate.ApprovalError):
            approval_gate._safe_write(self.hive / 'approvals' / 'decision.json', 'test')
        self.assertEqual(self.canary.read_text(), 'original\n')

    def test_normal_output_write_and_append(self):
        target = artifact_io.write_exclusive(self.hive, 'proposals', 'sample.diff', PATCH.encode())
        self.assertEqual(target.read_text(), PATCH)
        artifact_io.append_log(self.hive, 'audit.jsonl', b'line1\n')
        artifact_io.append_log(self.hive, 'audit.jsonl', b'line2\n')
        self.assertEqual((self.hive / 'logs' / 'audit.jsonl').read_text(), 'line1\nline2\n')
        self.assertEqual(self.canary.read_text(), 'original\n')


if __name__ == '__main__':
    unittest.main()
