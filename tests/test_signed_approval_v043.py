"""Synthetic Ed25519 approval tests; never execute generated code or Docker."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import signed_approval as signed

SRC = ('export function checkpointRoom(room: string) {\n'
       '  return room.toUpperCase(); // recovery checkpoint\n'
       '}\n')
DIFF = ('--- a/server/room-checkpoints.ts\n'
        '+++ b/server/room-checkpoints.ts\n'
        '@@ -1,3 +1,3 @@\n'
        ' export function checkpointRoom(room: string) {\n'
        '-  return room.toUpperCase(); // recovery checkpoint\n'
        '+  return room.trim().toUpperCase(); // recovery checkpoint\n'
        ' }\n')


class SignedApprovalTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.hive = self.root / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        self.source = self.repo / 'server' / 'room-checkpoints.ts'
        self.source.parent.mkdir()
        self.source.write_text(SRC, encoding='utf-8')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
        self.git('switch', '-qc', 'bee/test')
        self.commit = self.git('rev-parse', 'HEAD')
        inv = signed.legacy.bridge.investigation
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'STOP': self.hive / 'STOP', 'REPORTS': self.hive / 'proposals',
                           'LOGS': self.hive / 'logs'}.items():
            old = getattr(inv, key)
            setattr(inv, key, value)
            self.addCleanup(setattr, inv, key, old)
        (self.hive / 'proposals').mkdir()
        self.name = 'guided-20261102T170000Z-abc123abc123'
        self.diff_path = self.hive / 'proposals' / (self.name + '.diff')
        self.report_path = self.hive / 'proposals' / (self.name + '.json')
        self.diff_path.write_text(DIFF, encoding='utf-8')
        self.report = {'source_commit': self.commit, 'diff_sha256': hashlib.sha256(DIFF.encode()).hexdigest(),
                       'target': 'server/room-checkpoints.ts', 'partial_scan': False}
        self.write_report()
        self.secret_directory = self.root / 'separate-protected-signer'
        self.secret_directory.mkdir(mode=0o700)
        self.private_path = self.secret_directory / 'private.key'
        self.public_path = self.secret_directory / 'public.key'
        self.new_keys()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def new_keys(self):
        key = Ed25519PrivateKey.generate()
        self.private_path.write_bytes(key.private_bytes(serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        self.private_path.chmod(0o600)
        self.public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.Raw,
                            serialization.PublicFormat.Raw))
        self.trusted = signed.fingerprint(self.public_path)

    def write_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding='utf-8')

    def approve(self, action='apply_disposable_patch', **kw):
        return signed.sign(self.name, action, private_key_file=kw.get('private_key_file', self.private_path),
            confirmation=kw.get('confirmation', f'SIGN {signed.legacy.ACTIONS[action]} '
              f'{self.report["diff_sha256"][:12]} {self.commit[:12]}'),
            interactive=kw.get('interactive', True))

    def verify(self, action='apply_disposable_patch', **kw):
        return signed.verify(self.name, action, public_key_file=kw.get('public_key_file', self.public_path),
              trusted_fingerprint=kw.get('trusted_fingerprint', self.trusted))

    def record_path(self, action='apply_disposable_patch'):
        return self.hive / 'approvals' / signed._filename(self.name, action)

    def mutate_record(self, updater):
        p = self.record_path()
        obj = json.loads(p.read_text())
        updater(obj)
        p.write_text(json.dumps(obj), encoding='utf-8')

    def test_valid_signature_binds_exact_proposal_without_worktree_change(self):
        self.approve()
        result = self.verify()
        self.assertTrue(result['signed'])
        self.assertEqual(result['key_sha256'], self.trusted)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_signature_record_can_be_verified_with_public_only(self):
        self.approve()
        self.private_path.unlink()
        self.assertTrue(self.verify()['signed'])

    def test_two_actions_need_independent_signatures(self):
        self.approve()
        with self.assertRaises(signed.SignedApprovalError): self.verify('run_isolated_tests')
        self.approve('run_isolated_tests')
        self.assertTrue(self.verify('run_isolated_tests')['signed'])

    def test_local_legacy_json_record_never_counts(self):
        raw = signed.legacy.inspect(self.name)
        signed.legacy.issue(self.name, 'apply_disposable_patch', typed='APPROVE APPLY ' + raw['diff_sha256'][:12], terminal=True)
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_false_or_missing_interactive_refused(self):
        with self.assertRaises(signed.SignedApprovalError): self.approve(interactive=False)
        self.assertFalse(self.record_path().exists())

    def test_wrong_phrase_rejected(self):
        with self.assertRaises(signed.SignedApprovalError): self.approve(confirmation='SIGN APPLY')

    def test_wrong_key_pinning_rejected(self):
        self.approve()
        with self.assertRaises(signed.SignedApprovalError): self.verify(trusted_fingerprint='0'*64)
        with self.assertRaises(signed.SignedApprovalError): self.verify(trusted_fingerprint='')

    def test_different_public_key_rejected(self):
        self.approve()
        self.new_keys()
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_changed_signature_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r.__setitem__('signature', base64.b64encode(b'0'*64).decode()))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_changed_action_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r['payload'].__setitem__('action', 'run_isolated_tests'))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_changed_expiry_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r['payload'].__setitem__('expires_at', (datetime.now(timezone.utc)+timedelta(days=10)).isoformat()))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_changed_target_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r['payload'].__setitem__('target', 'server/fake.ts'))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_invalid_base64_and_length_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r.__setitem__('signature', '@@@'))
        with self.assertRaises(signed.SignedApprovalError): self.verify()
        self.mutate_record(lambda r: r.__setitem__('signature', base64.b64encode(b'x').decode()))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_unrecognized_json_fields_rejected(self):
        self.approve()
        self.mutate_record(lambda r: r.__setitem__('approved', True))
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_duplicate_record_refused(self):
        self.approve()
        with self.assertRaises(signed.SignedApprovalError): self.approve()

    def test_revoked_proposal_refuses_signature_verification(self):
        self.approve()
        signed.legacy.close(self.name, 'revoked')
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_stop_prevents_signing_and_verification(self):
        self.approve()
        (self.hive / 'STOP').write_text('STOP')
        with self.assertRaises(signed.legacy.ApprovalError): self.verify()
        with self.assertRaises(signed.legacy.ApprovalError): self.approve('run_isolated_tests')

    def test_changed_source_commit_refused(self):
        self.approve()
        self.source.write_text(SRC + '// new\n')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'changed')
        with self.assertRaises(signed.legacy.ApprovalError): self.verify()

    def test_dirty_worktree_refused(self):
        self.approve()
        self.source.write_text(SRC + '\n')
        with self.assertRaises(signed.legacy.ApprovalError): self.verify()

    def test_tampered_report_invalidates_signed_approval(self):
        self.approve()
        self.report['partial_scan'] = True
        self.write_report()
        with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_key_inside_hive_refused(self):
        inside = self.hive / 'secrets.key'
        inside.write_bytes(self.private_path.read_bytes())
        inside.chmod(0o600)
        with self.assertRaises(signed.SignedApprovalError): self.approve(private_key_file=inside)

    def test_weak_private_directory_permissions_refused(self):
        self.secret_directory.chmod(0o755)
        with self.assertRaises(signed.SignedApprovalError): self.approve()

    def test_private_key_parent_symlink_refused(self):
        alias = self.root / 'linked-dir'
        alias.symlink_to(self.secret_directory, target_is_directory=True)
        with self.assertRaises(signed.SignedApprovalError): self.approve(private_key_file=alias / 'private.key')

    def test_weak_private_key_permissions_refused(self):
        self.private_path.chmod(0o644)
        with self.assertRaises(signed.SignedApprovalError): self.approve()

    def test_private_key_symlink_refused(self):
        alias = self.root / 'alias.key'
        alias.symlink_to(self.private_path)
        with self.assertRaises(signed.SignedApprovalError): self.approve(private_key_file=alias)

    def test_private_key_hardlink_refused(self):
        alias = self.root / 'copy.key'
        os.link(self.private_path, alias)
        with self.assertRaises(signed.SignedApprovalError): self.approve()

    def test_public_key_symlink_refused(self):
        self.approve()
        alias = self.root / 'public-link.key'
        alias.symlink_to(self.public_path)
        with self.assertRaises(signed.SignedApprovalError): self.verify(public_key_file=alias)

    def test_expired_even_with_valid_signature(self):
        self.approve()
        with patch.object(signed, 'datetime') as fake_dt:
            fake_dt.now.return_value = datetime.now(timezone.utc) + timedelta(minutes=16)
            with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_future_clock_even_with_valid_signature(self):
        self.approve()
        with patch.object(signed, 'datetime') as fake_dt:
            fake_dt.now.return_value = datetime.now(timezone.utc) - timedelta(minutes=2)
            with self.assertRaises(signed.SignedApprovalError): self.verify()

    def test_signed_decision_never_executes(self):
        self.approve()
        self.verify()
        self.assertEqual(self.git('status', '--porcelain'), '')
        source = Path(signed.__file__).read_text()
        self.assertNotIn('docker run', source)
        self.assertNotIn('git apply -', source)


if __name__ == '__main__':
    unittest.main()
