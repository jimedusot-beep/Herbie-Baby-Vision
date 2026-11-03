"""Offline unit tests for Baby Vision's committed-only read-only search."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'agents' / 'repository_search.py'
spec = importlib.util.spec_from_file_location('baby_vision_repository_search', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RepositorySearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Offline fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'src').mkdir()
        (self.repo / 'src' / 'reconnect.ts').write_text(
            'export function reconnectPlayer(id: string) {\n'
            '  return sessionStore.find(id); // recover player session\n'
            '}\n', encoding='utf-8')
        (self.repo / 'README.md').write_text('Session recovery uses reconnectPlayer.\n', encoding='utf-8')
        (self.repo / '.env').write_text('TOP_SECRET_TOKEN=must-not-appear\n', encoding='utf-8')
        (self.repo / 'src' / 'secrets.json').write_text('{"password":"must-not-appear"}\n', encoding='utf-8')
        (self.repo / 'src' / 'big.py').write_text('x' * (module.MAX_BLOB_BYTES + 1), encoding='utf-8')
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Offline test fixture')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True, timeout=10).stdout

    def test_manifest_is_pinned_and_excludes_secrets_and_large_files(self):
        inventory = module.manifest(self.repo)
        self.assertEqual(inventory['source_commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertIn('src/reconnect.ts', inventory['paths'])
        self.assertNotIn('.env', inventory['paths'])
        self.assertNotIn('src/secrets.json', inventory['paths'])
        self.assertNotIn('src/big.py', inventory['paths'])
        self.assertGreaterEqual(inventory['excluded_or_oversized'], 3)

    def test_search_returns_real_commit_file_and_line(self):
        result = module.search(self.repo, 'reconnectPlayer', mode='literal')
        self.assertEqual(result['source_commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertTrue(any(h['path'] == 'src/reconnect.ts' and h['line'] == 1 for h in result['hits']))
        self.assertTrue(all('score' in h for h in result['hits']))

    def test_search_supports_natural_language_keywords(self):
        result = module.search(self.repo, 'find the player session reconnect logic')
        self.assertTrue(any('reconnect.ts' in h['path'] for h in result['hits']))

    def test_does_not_read_uncommitted_changes(self):
        (self.repo / 'src' / 'reconnect.ts').write_text('UNCOMMITTED_NEVER_VISIBLE\n', encoding='utf-8')
        result = module.search(self.repo, 'UNCOMMITTED_NEVER_VISIBLE', mode='literal')
        self.assertEqual(result['hits'], [])
        previous = module.search(self.repo, 'reconnectPlayer', mode='literal')
        self.assertGreater(len(previous['hits']), 0)

    def test_excludes_secret_content_even_if_tracked(self):
        result = module.search(self.repo, 'must-not-appear', mode='literal')
        self.assertEqual(result['hits'], [])
        self.assertNotIn('must-not-appear', json.dumps(module.manifest(self.repo)))

    def test_skip_symlink_git_objects(self):
        # Symlinks in committed Git trees are mode 120000; never follow them.
        if hasattr(__import__('os'), 'symlink'):
            link = self.repo / 'src' / 'external.py'
            try:
                link.symlink_to(self.repo / '.env')
            except (OSError, NotImplementedError):
                self.skipTest('Platform does not support symlink creation')
            self.git('add', 'src/external.py')
            self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Add symlink')
            inventory = module.manifest(self.repo)
            self.assertNotIn('src/external.py', inventory['paths'])

    def test_invalid_input_fail_closed(self):
        for query in ('', '  ', 'a' * 161, 'the and for'):
            with self.subTest(query=query), self.assertRaises(module.RepositorySearchError):
                module.search(self.repo, query)
        with self.assertRaises(module.RepositorySearchError):
            module.search(self.repo / 'src', 'reconnect')
        with self.assertRaises(module.RepositorySearchError):
            module.search(self.repo, 'reconnect', mode='regex')
        with self.assertRaises(module.RepositorySearchError):
            module.search(self.repo, 'reconnect', max_hits=100000)

    def test_result_is_bounded_and_deterministic(self):
        one = module.search(self.repo, 'session', max_hits=1)
        two = module.search(self.repo, 'session', max_hits=1)
        self.assertEqual(one, two)
        self.assertLessEqual(len(one['hits']), 1)
        self.assertTrue(one['truncated'])


if __name__ == '__main__':
    unittest.main()
