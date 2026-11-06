"""Explicit, localhost-only smoke test against an INSTALLED Ollama model.

Requires an explicitly reviewed Herbie PR #93 gateway module file. This script
never installs models, opens a LAN port, starts background services, executes AI
output, or sends prompts/responses/secrets to logs. Unlike synthetic integration
tests, --run-live *does* ask a real local Ollama model to generate one reply.

PowerShell example (from this repository's checkout):
    py -3.12 integration/live_ollama_smoke.py --run-live \
      --model gemma3:1b \
      --gateway-file C:/Review/Herbie/socratic-agent/socratic_agent/worker_gateway.py
"""
import argparse
import hashlib
import types
import json
import subprocess
import tempfile
from pathlib import Path
import secrets
import sys
import threading
from time import monotonic
import urllib.error
import urllib.request
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from herbie_gateway_client import GatewayError, HerbieGatewayClient
from gateway_first_task import run_gateway_task, ModelProposalRejected

MAX_TAGS_BYTES = 262_144
# Reviewed Git blob SHA of Herbie PR #93's worker_gateway.py.
# Re-review and update this pin whenever the gateway module changes.
REVIEWED_GATEWAY_GIT_BLOB_SHA = "df729520d94aa214e6920a471bdece289987bafb"
# Opt-in review-only logical cancellation gateway branch; not merged into #93.
REVIEWED_GATEWAY_GIT_BLOB_SHA_LOGICAL_STOP = "701717ed2a364b7c6c2c255485cd079e79be1a36"
# Separate private Step 2 durable replay candidate; explicit review-only source.
REVIEWED_GATEWAY_GIT_BLOB_SHA_DURABLE_IDS = "d930904a535830a098efbd8ff6eda40d825feb91"
# Earlier reviewed snapshots remain usable for reproducing those runs.
REVIEWED_GATEWAY_GIT_BLOB_SHA_ORIGINAL = "eef2eebc43fc7aaec67ebd3cc652ee3b0dd7d9c4"
REVIEWED_GATEWAY_GIT_BLOB_SHA_RETRY_ORDER = "570a7d3077675e34ecae36f0abcdc76a7a5df7cb"
TEST_PROMPT = "In one short sentence, explain what a Python unit test checks."


class SmokeBlocked(RuntimeError):
    """A safe, non-sensitive reason a live smoke test cannot proceed."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def reviewed_git_blob_sha(source):
    """Hash normalized Git blob bytes, tolerating Windows CRLF checkout conversion."""
    normalized = source.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(normalized)).encode("ascii")
                        + b"\0" + normalized).hexdigest()


def load_gateway_module(path):
    path = Path(path).expanduser() if path else None
    if path is None or not path.is_file() or path.name != "worker_gateway.py":
        raise SmokeBlocked("reviewed_gateway_source_unavailable")
    source = path.read_bytes()
    git_blob = reviewed_git_blob_sha(source)
    if git_blob not in (
        REVIEWED_GATEWAY_GIT_BLOB_SHA,
        REVIEWED_GATEWAY_GIT_BLOB_SHA_LOGICAL_STOP,
        REVIEWED_GATEWAY_GIT_BLOB_SHA_DURABLE_IDS,
        REVIEWED_GATEWAY_GIT_BLOB_SHA_ORIGINAL,
        REVIEWED_GATEWAY_GIT_BLOB_SHA_RETRY_ORDER,
    ):
        raise SmokeBlocked("gateway_source_revision_unreviewed")
    # Execute the EXACT bytes checked above. Importing by pathname instead
    # could read a modified file or use a stale .pyc after the hash check.
    module = types.ModuleType("herbie_v02b_smoke_gateway")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def installed_models(ollama_url, validate_url):
    """Read only /api/tags from an explicit loopback endpoint; no downloads."""
    base_url = validate_url(ollama_url)
    req = urllib.request.Request(base_url + "/api/tags", method="GET",
                                 headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(req, timeout=8) as response:
            raw = response.read(MAX_TAGS_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SmokeBlocked("ollama_not_reachable_on_loopback") from None
    if len(raw) > MAX_TAGS_BYTES:
        raise SmokeBlocked("ollama_tags_response_oversize")
    try:
        body = json.loads(raw.decode("utf-8"))
        entries = body["models"]
        if not isinstance(entries, list):
            raise ValueError()
        names = set()
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError()
            for key in ("name", "model"):
                if isinstance(item.get(key), str):
                    names.add(item[key])
        return names
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise SmokeBlocked("ollama_tags_response_invalid") from None



def run_trusted_fixture_task(model, gateway_url, token):
    """Exercise the bounded coding worker on NEW generated source, never owner's files.

    This runs fixed Git/npm commands against a fixture authored by this test.
    It is NOT an OS sandbox suitable for untrusted repository code.
    """
    def git(repo, *args):
        subprocess.run(['git', '-C', str(repo), *args], check=True, timeout=20,
                       capture_output=True, text=True)

    try:
        with tempfile.TemporaryDirectory(prefix='baby-worker-acceptance-') as tmp:
            repo = Path(tmp) / 'trusted_fixture'
            repo.mkdir()
            git(repo, 'init', '-q')
            git(repo, 'config', 'user.name', 'Worker fixture')
            git(repo, 'config', 'user.email', 'worker@example.invalid')
            package = json.dumps({'name': 'baby-worker-fixture', 'private': True,
                'scripts': {'test:unit': 'node --test tests/*.test.cjs'}},
                indent=2) + '\n'
            (repo / 'package.json').write_text(package, encoding='utf-8')
            (repo / 'tests').mkdir()
            (repo / 'tests' / 'basic.test.cjs').write_text(
                "const {test}=require('node:test');"
                "const assert=require('node:assert/strict');"
                "test('fixed fixture',()=>assert.equal(2+2,4));\n",
                encoding='utf-8')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'Generated trusted fixture')
            evidence = run_gateway_task(repo, model, gateway_url, token)
            if (evidence.get('status') != 'ready_for_human_review'
                    or evidence.get('test_exit_code') != 0):
                raise SmokeBlocked('bounded_worker_post_edit_tests_failed')
            if (evidence.get('merge_allowed') is not False
                    or evidence.get('allowed_files') != ['package.json']
                    or (repo / 'package.json').read_text(encoding='utf-8') != package):
                raise SmokeBlocked('bounded_worker_review_contract_failed')
            return {'worker_fixture': 'review_ready',
                    'worker_tests': 'passed',
                    'source_checkout_unchanged': True,
                    'review_packet_saved': False,
                    'generated_commands_executed': False}
    except SmokeBlocked:
        raise
    except ModelProposalRejected as exc:
        # Report a fixed category, never the model text or a prompt excerpt.
        raise SmokeBlocked('bounded_worker_' + exc.code) from None
    except GatewayError:
        raise SmokeBlocked('bounded_worker_gateway_request_failed') from None
    except subprocess.TimeoutExpired:
        raise SmokeBlocked('bounded_worker_trusted_command_timeout') from None
    except subprocess.CalledProcessError:
        raise SmokeBlocked('bounded_worker_trusted_command_failed') from None
    except (OSError, ValueError, KeyError):
        raise SmokeBlocked('bounded_worker_fixture_local_error') from None

def run_live(model, gateway_file, ollama_url="http://127.0.0.1:11434", *, run_fixture_task=False):
    """One local inference call, preceded by an authentication-negative check."""
    gateway = load_gateway_module(gateway_file)
    if not isinstance(model, str) or not gateway.MODEL_PATTERN.fullmatch(model):
        raise SmokeBlocked("invalid_model_name")
    available = installed_models(ollama_url, gateway.validate_local_ollama)
    if model not in available:
        raise SmokeBlocked("requested_model_not_installed")

    token = secrets.token_urlsafe(40)
    server = gateway.WorkerGatewayServer(
        ("127.0.0.1", 0),
        token=token,
        allowed_models=(model,),
        ollama_url=ollama_url,
        max_requests_per_minute=4,
    )
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        client = HerbieGatewayClient(url, token, model, timeout=75)
        if client.health() is not True:
            raise SmokeBlocked("gateway_health_unavailable")

        wrong_token_client = HerbieGatewayClient(
            url, secrets.token_urlsafe(40), model, timeout=5)
        try:
            wrong_token_client.health()
        except GatewayError:
            pass
        else:
            raise SmokeBlocked("authentication_negative_check_failed")

        before = monotonic()
        try:
            reply = client.infer("testing", TEST_PROMPT, str(uuid4()))
        except GatewayError:
            raise SmokeBlocked("real_model_inference_failed") from None
        elapsed = round(monotonic() - before, 2)
        if not reply.strip():
            raise SmokeBlocked("real_model_returned_empty_reply")

        # Do not print, retain, write, or upload the actual prompt or reply.
        worker_evidence = (run_trusted_fixture_task(model, url, token)
                           if run_fixture_task else {"worker_fixture": "not_run"})
        return {
            **worker_evidence,
            "status": "completed",
            "mode": "real_model_localhost",
            "model": model,
            "gateway_health": "passed",
            "incorrect_token_rejected": True,
            "inference": "nonempty_reply",
            "latency_seconds": elapsed,
            "reply_characters": len(reply),
            "network_access": "loopback_only",
            "real_remote_devices_tested": False,
            "merge_allowed": False,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true",
                        help="Explicit authorization for a REAL local model test")
    parser.add_argument("--run-fixture-task", action="store_true",
                        help="Also run the one allowed coding worker task on a newly generated trusted Git fixture")
    parser.add_argument("--model", help="Exact installed model name from ollama list")
    parser.add_argument("--gateway-file",
                        help="Path to reviewed Herbie PR #93 worker_gateway.py checkout")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434",
                        help="Loopback-only Ollama URL (never a LAN or public address)")
    args = parser.parse_args(argv)

    if not args.run_live:
        print(json.dumps({"status": "blocked",
                          "reason": "explicit_run_live_flag_required",
                          "merge_allowed": False}))
        return 2
    try:
        result = run_live(args.model, args.gateway_file, args.ollama_url,
                          run_fixture_task=args.run_fixture_task)
    except (SmokeBlocked, ValueError) as exc:
        # Only controlled reason codes from this module are exposed.
        reason = str(exc) if isinstance(exc, SmokeBlocked) else "invalid_local_endpoint"
        result = {"status": "blocked", "reason": reason,
                  "merge_allowed": False}
    except Exception:
        result = {"status": "blocked", "reason": "unexpected_local_test_error",
                  "merge_allowed": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
