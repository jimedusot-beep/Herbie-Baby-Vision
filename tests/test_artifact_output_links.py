"""Artifact writers must not follow a linked output filename, even if dangling.

These are synthetic filesystem tests; no model inference or repository writes.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import artifact_io


class ArtifactOutputLinkTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.hive = self.root / 'hive'
        self.hive.mkdir()
        self.output = self.hive / 'proposals'
        self.output.mkdir()

    def link(self, name, target):
        link = self.output / name
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('Symlinks unavailable: ' + str(exc))
        return link

    def test_dangling_output_link_does_not_create_external_file(self):
        outside = self.root / 'missing-owner-file'
        link = self.link('proposed.diff', outside)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.write_exclusive(self.hive, 'proposals', 'proposed.diff', b'NEVER_WRITE')
        self.assertFalse(outside.exists())
        self.assertTrue(link.is_symlink())

    def test_existing_output_link_does_not_overwrite_external_content(self):
        outside = self.root / 'owner-file'
        outside.write_text('KEEP_ORIGINAL', encoding='utf-8')
        link = self.link('proposed.json', outside)
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.write_exclusive(self.hive, 'proposals', 'proposed.json', b'NEVER_WRITE')
        self.assertEqual(outside.read_text(), 'KEEP_ORIGINAL')
        self.assertTrue(link.is_symlink())

    def test_existing_regular_output_file_does_not_get_overwritten(self):
        target = self.output / 'existing.diff'
        target.write_text('KEEP_ORIGINAL', encoding='utf-8')
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.write_exclusive(self.hive, 'proposals', 'existing.diff', b'NEVER_WRITE')
        self.assertEqual(target.read_text(), 'KEEP_ORIGINAL')

    def test_fresh_output_file_succeeds_and_stays_exclusive(self):
        dest = artifact_io.write_exclusive(self.hive, 'proposals', 'fresh.diff', b'SYNTHETIC')
        self.assertEqual(dest.read_bytes(), b'SYNTHETIC')
        with self.assertRaises(artifact_io.ArtifactError):
            artifact_io.write_exclusive(self.hive, 'proposals', 'fresh.diff', b'NO_OVERWRITE')
        self.assertEqual(dest.read_bytes(), b'SYNTHETIC')


if __name__ == '__main__':
    unittest.main()
