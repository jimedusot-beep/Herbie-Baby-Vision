"""M1 regression tests for a physical disposable clone (no link redirects)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import coding_bee
import readonly_investigate


class DisposableCheckoutBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.hive = self.root / 'hive'
        self.work = self.hive / 'work'
        self.repo = self.work / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        (self.repo / 'sample.ts').write_text('export const checkpoint = 1;\n', encoding='utf-8')
        for key, value in {'HIVE': self.hive, 'WORK': self.repo,
                           'STOP': self.hive / 'STOP',
                           'TASKS': self.hive / 'tasks'}.items():
            if hasattr(coding_bee, key):
                previous = getattr(coding_bee, key)
                setattr(coding_bee, key, value)
                self.addCleanup(setattr, coding_bee, key, previous)
            if hasattr(readonly_investigate, key):
                previous = getattr(readonly_investigate, key)
                setattr(readonly_investigate, key, value)
                self.addCleanup(setattr, readonly_investigate, key, previous)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Synthetic Test')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'synthetic')
        self.git('switch', '-qc', 'bee/safety')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, timeout=15).stdout.strip()

    def symlink(self, link, dest, *, directory=True):
        try:
            link.symlink_to(dest, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'Symlinks unavailable on this runner: {exc}')

    def both_reject(self):
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.validate_work()
        with self.assertRaises(readonly_investigate.InvestigationError):
            readonly_investigate.check_work()

    def test_physical_checkout_still_works(self):
        commit = self.git('rev-parse', 'HEAD')
        self.assertEqual(coding_bee.validate_work(), commit)
        self.assertEqual(readonly_investigate.check_work(), commit)

    def test_refuses_symlinked_work_parent(self):
        # The previous code resolved work/ first, treating the redirect as trusted.
        outside = self.root / 'external'
        outside.mkdir()
        self.repo.rename(outside / 'trivia-lobby')
        self.work.rmdir()
        self.symlink(self.work, outside)
        self.both_reject()

    def test_refuses_symlinked_checkout_leaf(self):
        outside = self.root / 'external'
        outside.mkdir()
        self.repo.rename(outside / 'trivia-lobby')
        self.symlink(self.repo, outside / 'trivia-lobby')
        self.both_reject()

    def test_refuses_symlinked_git_metadata_directory(self):
        moved = self.repo / 'moved-git'
        (self.repo / '.git').rename(moved)
        self.symlink(self.repo / '.git', moved)
        self.both_reject()

    def test_refuses_symlinked_task_file_even_within_tasks_directory(self):
        tasks = self.hive / 'tasks'
        tasks.mkdir()
        regular = tasks / 'regular.md'
        regular.write_text('FILES: sample.ts\nFix the checkpoint\n', encoding='utf-8')
        linked = tasks / 'redirected.md'
        self.symlink(linked, regular, directory=False)
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.safe_task(linked)
        self.assertEqual(coding_bee.safe_task(regular)[0], ['sample.ts'])

    def test_refuses_symlinked_tasks_directory(self):
        real_tasks = self.hive / 'source-tasks'
        real_tasks.mkdir()
        task = real_tasks / 'example.md'
        task.write_text('FILES: sample.ts\nFix the checkpoint\n', encoding='utf-8')
        self.symlink(self.hive / 'tasks', real_tasks)
        with self.assertRaises(coding_bee.BeeError):
            coding_bee.safe_task(self.hive / 'tasks' / 'example.md')


if __name__ == '__main__':
    unittest.main()
