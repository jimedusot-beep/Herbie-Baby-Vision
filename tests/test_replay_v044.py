"""V0.4.4 isolated POSIX replay prototype tests (no generated execution)."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import approval_replay as replay
import test_signed_approval_v043 as fixture


@unittest.skipIf(os.name == 'nt', 'Windows reservation deliberately disabled pending security review')
class ReplayTests(unittest.TestCase):
    # Reuse the *synthetic* fixture without inheriting/re-running its entire suite.
    setUpSource = fixture.SignedApprovalTests.setUp
    git = fixture.SignedApprovalTests.git
    new_keys = fixture.SignedApprovalTests.new_keys
    write_report = fixture.SignedApprovalTests.write_report
    approve = fixture.SignedApprovalTests.approve
    verify = fixture.SignedApprovalTests.verify
    record_path = fixture.SignedApprovalTests.record_path

    def setUp(self):
        self.setUpSource()
        self.ledgerdir = self.root / 'trusted-ledger'
        self.ledgerdir.mkdir(mode=0o700)
        self.ledgerdir.chmod(0o700)
        self.ledger = self.ledgerdir / 'used.sqlite3'
        replay.provision(self.ledger)

    def claim(self, action='apply_disposable_patch', **changes):
        opts = dict(ledger=self.ledger, public_key_file=self.public_path,
                    trusted_fingerprint=self.trusted)
        opts.update(changes)
        return replay.reserve(self.name, action, **opts)

    def test_reserve_once_no_code_change(self):
        self.approve()
        first = self.claim()
        self.assertTrue(first['reserved'])
        self.assertFalse(first['executed'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_independent_actions_need_separate_signatures_and_claims(self):
        self.approve()
        self.claim()
        with self.assertRaises(replay.ReplayError): self.claim('run_isolated_tests')
        self.approve('run_isolated_tests')
        other = self.claim('run_isolated_tests')
        self.assertTrue(other['reserved'])
        with self.assertRaises(replay.ReplayError): self.claim('run_isolated_tests')

    def test_transaction_is_durable_across_connections(self):
        self.approve()
        claim = self.claim()
        with closing(sqlite3.connect(self.ledger)) as db:
            rows = db.execute('SELECT claim_id, proposal, action FROM claims').fetchall()
        self.assertEqual(rows, [(claim['claim_id'], self.name, 'apply_disposable_patch')])
        self.assertFalse((self.hive / 'approvals' / 'approval_replay.sqlite3').exists())

    def test_parallel_reservations_only_one_wins(self):
        self.approve()
        def attempt(_):
            try:
                self.claim()
                return True
            except replay.ReplayError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(results.count(True), 1, results)

    def test_reboot_replay_without_new_signature_refused(self):
        self.approve()
        self.claim()
        # Can't bypass by removing a legacy 'consumed' marker.
        (self.hive / 'approvals' / (self.name + '.apply_disposable_patch.consumed')).unlink(missing_ok=True)
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_stop_refuses_and_does_not_consume(self):
        self.approve()
        (self.hive / 'STOP').write_text('STOP')
        with self.assertRaises(replay.ReplayError): self.claim()
        with closing(sqlite3.connect(self.ledger)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM claims').fetchone()[0], 0)

    def test_modified_proposal_refused(self):
        self.approve()
        self.report['partial_scan'] = True
        self.write_report()
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_wrong_fingerprint_refused(self):
        self.approve()
        with self.assertRaises(replay.ReplayError): self.claim(trusted_fingerprint='0'*64)

    def test_legacy_approval_never_accepted(self):
        prop = replay.signed.legacy.inspect(self.name)
        replay.signed.legacy.issue(self.name, 'apply_disposable_patch',
            typed='APPROVE APPLY ' + prop['diff_sha256'][:12], terminal=True)
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_ledger_in_hive_refused(self):
        with self.assertRaises(replay.ReplayError): replay.provision(self.hive / 'bad.sqlite3')

    def test_parent_group_writable_refused(self):
        self.ledgerdir.chmod(0o770)
        self.approve()
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_ledger_symlink_refused(self):
        link = self.ledgerdir / 'alias.sqlite3'
        link.symlink_to(self.ledger)
        self.approve()
        with self.assertRaises(replay.ReplayError): self.claim(ledger=link)

    def test_ledger_hardlink_refused(self):
        link = self.ledgerdir / 'clone.sqlite3'
        os.link(self.ledger, link)
        self.approve()
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_ledger_file_world_access_refused(self):
        self.ledger.chmod(0o644)
        self.approve()
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_database_corruption_fails_closed(self):
        self.approve()
        self.ledger.write_bytes(b'not an sqlite database')
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_init_exclusive_refuses_overwrite(self):
        with self.assertRaises(replay.ReplayError): replay.provision(self.ledger)

    def test_ledger_cannot_be_created_by_claim(self):
        self.approve()
        self.ledger.unlink()
        with self.assertRaises(replay.ReplayError): self.claim()
        self.assertFalse(self.ledger.exists())

    def test_unsupported_schema_version_refused(self):
        self.approve()
        with closing(sqlite3.connect(self.ledger)) as db: db.execute('PRAGMA user_version=3')
        with self.assertRaises(replay.ReplayError): self.claim()

    def test_windows_branch_is_explicitly_disabled(self):
        with patch.object(replay.os, 'name', 'nt'):
            with self.assertRaisesRegex(replay.ReplayError, 'Windows'):
                replay._check_path('C:/secure/used.sqlite3', must_exist=True)

    def test_no_exec_in_module(self):
        source = Path(replay.__file__).read_text()
        for expression in ('docker run', 'git apply', 'subprocess.run(', 'os.system('):
            self.assertNotIn(expression, source)


if __name__ == '__main__':
    unittest.main()
