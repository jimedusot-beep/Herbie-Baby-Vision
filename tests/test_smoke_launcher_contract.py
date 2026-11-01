"""Guard the Windows smoke launcher against stale source pins and branch drift.

Static contract only. Does not clone private Herbie or call local Ollama.
"""
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def git_blob(path):
    data = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class WindowsSmokeLauncherTests(unittest.TestCase):
    def test_launcher_pins_match_the_exact_reviewed_baby_sources(self):
        cmd = (ROOT / 'scripts' / 'run_zbook_local_smoke.cmd').read_text()
        self.assertIn(f'if /I not "%CLIENT_SHA%"=="{git_blob("agents/herbie_gateway_client.py")}"', cmd)
        self.assertIn(f'if /I not "%SMOKE_SHA%"=="{git_blob("integration/live_ollama_smoke.py")}"', cmd)

    def test_herbie_gateway_pin_matches_live_loader_and_launcher(self):
        smoke = (ROOT / 'integration' / 'live_ollama_smoke.py').read_text()
        cmd = (ROOT / 'scripts' / 'run_zbook_local_smoke.cmd').read_text()
        match = re.search(r'REVIEWED_GATEWAY_GIT_BLOB_SHA = "([0-9a-f]{40})"', smoke)
        self.assertIsNotNone(match, 'The reviewed gateway source pin must be explicit')
        self.assertIn(f'if /I not "%GATEWAY_SHA%"=="{match.group(1)}"', cmd)

    def test_launcher_uses_only_the_merged_candidate_checkout_and_opt_in_smoke(self):
        cmd = (ROOT / 'scripts' / 'run_zbook_local_smoke.cmd').read_text()
        self.assertIn('--branch codex/v02d-real-ollama-local-smoke', cmd)
        self.assertIn('--branch integration/herbie-engineering-20261031', cmd)
        self.assertIn('--run-live', cmd)
        self.assertIn('--gateway-file', cmd)
        self.assertNotIn('--branch codex/v02b-worker-inference-gateway', cmd)
        self.assertNotIn('HERBIE_WORKER_GATEWAY_ENABLED=1', cmd)


if __name__ == '__main__':
    unittest.main()
