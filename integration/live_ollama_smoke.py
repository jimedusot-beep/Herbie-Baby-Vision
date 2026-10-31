"""Explicit, localhost-only smoke test against an INSTALLED Ollama model.

Requires an explicitly reviewed Herbie PR #86 gateway module file. This script
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
import importlib.util
import json
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

MAX_TAGS_BYTES = 262_144
# Reviewed Git blob SHA of Herbie PR #86's worker_gateway.py.
# Re-review and update this pin whenever the gateway module changes.
REVIEWED_GATEWAY_GIT_BLOB_SHA = "05c760aabfb832ff7d69f540bc61b157dd1eec47"
TEST_PROMPT = "In one short sentence, explain what a Python unit test checks."


class SmokeBlocked(RuntimeError):
    """A safe, non-sensitive reason a live smoke test cannot proceed."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_gateway_module(path):
    path = Path(path).expanduser() if path else None
    if path is None or not path.is_file() or path.name != "worker_gateway.py":
        raise SmokeBlocked("reviewed_gateway_source_unavailable")
    source = path.read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(source)).encode("ascii")
                            + b"\0" + source).hexdigest()
    if git_blob != REVIEWED_GATEWAY_GIT_BLOB_SHA:
        raise SmokeBlocked("gateway_source_revision_unreviewed")
    spec = importlib.util.spec_from_file_location("herbie_v02b_smoke_gateway", path)
    if spec is None or spec.loader is None:
        raise SmokeBlocked("reviewed_gateway_source_unavailable")
    module = importlib.util.module_from_spec(spec)
    # Only load an operator-reviewed checkout: importing a Python file executes code.
    spec.loader.exec_module(module)
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


def run_live(model, gateway_file, ollama_url="http://127.0.0.1:11434"):
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
        return {
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
                        help="Explicit authorization for one REAL local inference request")
    parser.add_argument("--model", help="Exact installed model name from ollama list")
    parser.add_argument("--gateway-file",
                        help="Path to reviewed Herbie PR #86 worker_gateway.py checkout")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434",
                        help="Loopback-only Ollama URL (never a LAN or public address)")
    args = parser.parse_args(argv)

    if not args.run_live:
        print(json.dumps({"status": "blocked",
                          "reason": "explicit_run_live_flag_required",
                          "merge_allowed": False}))
        return 2
    try:
        result = run_live(args.model, args.gateway_file, args.ollama_url)
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
