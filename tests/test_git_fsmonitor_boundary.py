"""Read-only Git operations must not invoke configured fsmonitor commands.

Uses only a synthetic disposable repository with a harmless local canary hook.
No real user repositories or model inference; no source modifications.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import coding_bee
import readonly_investigate
import repository_search
import proposal_bridge


class FsMonitorBoundaryTests(unittest.TestCase):
    def test_git_callers_explicitly_disable_filesystem_monitor(self):
        """Even Windows Git invocations must include the temporary override."""
        with patch.object(readonly_investigate.subprocess, 'run') as runner:
            runner.return_value.stdout = ''
            readonly_investigate._git('status', '--porcelain')
            command = runner.call_args.args[0]
            self.assertEqual(command[:3], ['git', '-c', 'core.fsmonitor=false'])
            self.assertIn('status', command)

        with patch.object(repository_search.subprocess, 'run') as runner:
            runner.return_value.stdout = b''
            repository_search._git(Path('/synthetic'), 'ls-tree', '-r', 'HEAD')
            self.assertEqual(runner.call_args.args[0][:3],
                             ['git', '-c', 'core.fsmonitor=false'])

        oid = 'a' * 40
        with patch.object(repository_search.subprocess, 'run') as runner:
            runner.return_value.stdout = (oid + ' blob 3\n').encode() + b'abc\n'
            result = repository_search._batch_read_blobs(
                Path('/synthetic'), [('demo.py', oid, 3)])
            self.assertEqual(result, [('demo.py', b'abc')])
            self.assertEqual(runner.call_args.args[0][:3],
                             ['git', '-c', 'core.fsmonitor=false'])

        patch_text = '--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new\n'
        with patch.object(proposal_bridge.subprocess, 'run') as runner:
            runner.return_value.stdout = ''
            self.assertEqual(proposal_bridge.validate_patch(patch_text, 'demo.py'),
                             'demo.py')
            self.assertEqual(runner.call_args.args[0][:3],
                             ['git', '-c', 'core.fsmonitor=false'])

        with patch.object(coding_bee.subprocess, 'run') as runner:
            runner.return_value.stdout = ''
            coding_bee.git_read('status', '--porcelain')
            self.assertEqual(runner.call_args.args[0][:3],
                             ['git', '-c', 'core.fsmonitor=false'])

    @unittest.skipUnless(os.name == 'posix', 'Synthetic shell hook requires POSIX')
    def test_real_configured_fsmonitor_cannot_launch_from_investigator(self):
        """Actual Git would run this hook without the core.fsmonitor override."""
        with tempfile.TemporaryDirectory() as dirname:
            sandbox = Path(dirname)
            hive = sandbox / 'hive'
            repo = hive / 'work' / 'trivia-lobby'
            repo.mkdir(parents=True)
            (repo / 'demo.py').write_text(
                'checkpoint = "synthetic search marker"\n', encoding='utf-8')

            def git(*args):
                return subprocess.run(['git', '-C', str(repo), *args],
                                      capture_output=True, text=True, check=True,
                                      timeout=15).stdout.strip()
            git('init', '-q')
            git('config', 'user.email', 'synthetic@example.invalid')
            git('config', 'user.name', 'Synthetic Fixture')
            git('add', 'demo.py')
            git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
            git('switch', '-qc', 'bee/fsmonitor')

            canary = sandbox / 'configured-hook-ran'
            script = sandbox / 'fsmonitor-hook.sh'
            script.write_text(
                '#!/bin/sh\n'
                + 'printf invoked > "' + str(canary) + '"\n'
                + 'echo ""\n', encoding='utf-8')
            script.chmod(0o700)
            git('config', 'core.fsmonitor', str(script))

            old = [(obj, key, getattr(obj, key))
                   for obj in (readonly_investigate, coding_bee)
                   for key in ('HIVE', 'WORK', 'STOP')]
            for obj, key, value in old:
                setattr(obj, key, {'HIVE': hive, 'WORK': repo,
                                   'STOP': hive / 'STOP'}[key])
                self.addCleanup(setattr, obj, key, value)

            head = git('rev-parse', 'HEAD')
            self.assertEqual(readonly_investigate.check_work(), head)
            self.assertFalse(canary.exists(),
                             'read-only investigation ran configured Git hook')
            search = repository_search.search(
                repo, 'synthetic search marker', mode='literal')
            self.assertEqual(search['source_commit'], head)
            self.assertTrue(search['hits'])
            self.assertFalse(canary.exists(),
                             'read-only search ran configured Git hook')
            self.assertEqual(coding_bee.validate_work(), head)
            self.assertFalse(canary.exists())


if __name__ == '__main__':
    unittest.main()
