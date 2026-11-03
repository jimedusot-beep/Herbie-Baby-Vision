"""STOP marker lifecycle regressions: never overwrite canary files via symlinks.

Synthetic temp directories only. No Git clone, model, patch application, or
network access. The STOP sentinel is deliberately separate from all outputs.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import artifact_io
import coding_bee


class StopSentinelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.hive = self.root / 'hive'
        self.hive.mkdir()
        self.stop = self.hive / 'STOP'
        self.canary = self.root / 'owner-file.txt'
        self.canary.write_text('ORIGINAL_OWNER_CONTENT', encoding='utf-8')
        for attr, value in {'HIVE': self.hive, 'STOP': self.stop}.items():
            old = getattr(coding_bee, attr)
            setattr(coding_bee, attr, value)
            self.addCleanup(setattr, coding_bee, attr, old)

    def symlink(self, link, target):
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('File symlinks unavailable on this test platform: ' + str(exc))

    def test_normal_stop_and_resume_are_idempotent(self):
        self.assertFalse(artifact_io.stop_present(self.hive))
        self.assertTrue(artifact_io.set_stop(self.hive))
        self.assertEqual(self.stop.read_text(), 'disabled\n')
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.ensure_running()
        self.assertFalse(artifact_io.set_stop(self.hive))
        self.assertEqual(self.stop.read_text(), 'disabled\n')
        self.assertTrue(artifact_io.clear_stop(self.hive))
        self.assertFalse(artifact_io.clear_stop(self.hive))
        coding_bee.ensure_running()

    def test_stop_command_cannot_overwrite_symlink_target(self):
        self.symlink(self.stop, self.canary)
        with self.assertRaises(artifact_io.ArtifactError):
            coding_bee.cmd_stop(None)
        self.assertEqual(self.canary.read_text(), 'ORIGINAL_OWNER_CONTENT')
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.ensure_running()
        with self.assertRaises(artifact_io.ArtifactError):
            coding_bee.cmd_resume(None)
        self.assertEqual(self.canary.read_text(), 'ORIGINAL_OWNER_CONTENT')
        self.assertTrue(self.stop.is_symlink())

    def test_dangling_stop_link_also_disables_the_bee(self):
        nowhere = self.root / 'nonexistent-owner-file'
        self.symlink(self.stop, nowhere)
        self.assertTrue(artifact_io.stop_present(self.hive))
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.ensure_running()
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.set_stop(self.hive)
        self.assertFalse(nowhere.exists())
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.clear_stop(self.hive)

    def test_hardlinked_stop_is_not_modified_or_silently_removed(self):
        try:
            os.link(self.canary, self.stop)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('Hardlinks unavailable: ' + str(exc))
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.set_stop(self.hive)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.clear_stop(self.hive)
        self.assertEqual(self.canary.read_text(), 'ORIGINAL_OWNER_CONTENT')
        self.assertEqual(self.stop.read_text(), 'ORIGINAL_OWNER_CONTENT')

    def test_directory_named_stop_is_not_deleted(self):
        self.stop.mkdir()
        self.assertTrue(artifact_io.stop_present(self.hive))
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.set_stop(self.hive)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.clear_stop(self.hive)
        self.assertTrue(self.stop.is_dir())

    def test_stop_cli_returns_safe_refusal_when_marker_redirected(self):
        self.symlink(self.stop, self.canary)
        self.assertEqual(coding_bee.main(['stop']), 2)
        self.assertEqual(coding_bee.main(['resume']), 2)
        self.assertEqual(self.canary.read_text(), 'ORIGINAL_OWNER_CONTENT')

    def test_stop_cli_success_and_repeat_preserve_existing_marker(self):
        self.assertEqual(coding_bee.main(['stop']), 0)
        self.assertEqual(coding_bee.main(['stop']), 0)
        self.assertEqual(self.stop.read_text(), 'disabled\n')
        self.assertEqual(coding_bee.main(['resume']), 0)
        self.assertEqual(coding_bee.main(['resume']), 0)
        self.assertFalse(self.stop.exists())

    def test_stop_does_not_overwrite_existing_regular_user_content(self):
        self.stop.write_text('EXISTING_OPERATOR_STOP_MARKER', encoding='utf-8')
        self.assertFalse(artifact_io.set_stop(self.hive))
        self.assertEqual(self.stop.read_text(), 'EXISTING_OPERATOR_STOP_MARKER')
        self.assertTrue(artifact_io.clear_stop(self.hive))

    def test_redirected_hive_root_fails_closed(self):
        linked = self.root / 'hive-redirect'
        self.symlink(linked, self.hive)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.stop_present(linked)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.set_stop(linked)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.clear_stop(linked)

    def test_dangling_stop_refuses_investigation_proposal_and_approval(self):
        import readonly_investigate
        import proposal_bridge
        import approval_gate
        old = readonly_investigate.HIVE
        readonly_investigate.HIVE = self.hive
        self.addCleanup(setattr, readonly_investigate, 'HIVE', old)
        self.symlink(self.stop, self.root / 'missing-stop-target')
        with self.assertRaises(readonly_investigate.InvestigationError):
            readonly_investigate.stopped()
        with self.assertRaises(proposal_bridge.ProposalError):
            proposal_bridge.stopped()
        with self.assertRaises(approval_gate.ApprovalError):
            approval_gate._guard()


if __name__ == '__main__':
    unittest.main()
