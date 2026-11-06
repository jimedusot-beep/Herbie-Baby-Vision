"""Read-only local readiness check for Baby Vision's opt-in ZBook smoke test.

Does not clone, install, run model inference, launch servers, execute source,
write files, read credentials, or contact anything except localhost /api/tags.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.request

MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}\Z")
MAX_TAG_BYTES = 262144
EXPECTED_BLOBS = {
    "agents/herbie_gateway_client.py": "d8720b138cd754ada11174e14c141f2ef8ace3ab",
    "agents/first_task.py": "e8353df8f46ac632a30d93af177da2440d5462e4",
    "agents/gateway_first_task.py": "7e7890ddd8e198b6b1a54855fe97baad8a52d323",
    "integration/live_ollama_smoke.py": "1eaffa35b5638f076ecc6c825bf3139e5264e857",
}


class PreflightBlocked(ValueError):
    """Sanitized refusal (never includes network responses or local paths)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def git_blob(data):
    normalized = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(
        b"blob " + str(len(normalized)).encode("ascii") + b"\x00" + normalized
    ).hexdigest()


def sources_match(root):
    """Validate the reviewed files without importing or executing them."""
    root = Path(root)
    try:
        if root.is_symlink() or not root.is_dir():
            return False
        base = root.resolve(strict=True)
        for rel, expected in EXPECTED_BLOBS.items():
            path = root / rel
            if path.is_symlink() or not path.is_file():
                return False
            if any(parent.is_symlink() for parent in (path.parent, path.parent.parent)):
                return False
            if not path.resolve(strict=True).is_relative_to(base):
                return False
            if path.stat().st_size > 262144 or git_blob(path.read_bytes()) != expected:
                return False
    except (OSError, ValueError):
        return False
    return True


def local_model_tags():
    """Loopback GET of installed model names only; no inference or downloads."""
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/tags", method="GET",
        headers={"Accept": "application/json"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(req, timeout=4) as response:
            if response.status != 200:
                raise ValueError("Unexpected status")
            raw = response.read(MAX_TAG_BYTES + 1)
        if len(raw) > MAX_TAG_BYTES:
            raise ValueError("Oversize response")
        models = json.loads(raw)["models"]
        if not isinstance(models, list) or len(models) > 1000:
            raise ValueError("Invalid list")
        names = set()
        for item in models:
            if not isinstance(item, dict):
                raise ValueError("Invalid model")
            name = item.get("name") or item.get("model")
            if not isinstance(name, str) or not MODEL_PATTERN.fullmatch(name):
                raise ValueError("Invalid model name")
            names.add(name)
        return names
    except (OSError, TimeoutError, ValueError, TypeError, KeyError,
            urllib.error.URLError, PreflightBlocked):
        raise PreflightBlocked("ollama_tags_unavailable_or_invalid") from None


def readiness(model, *, root=None, platform=None, version=None,
              find_program=None, fetch_tags=None):
    """Only fixed result codes; injectable checks are synthetic test hooks."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    platform = sys.platform if platform is None else platform
    version = sys.version_info[:2] if version is None else version
    find_program = shutil.which if find_program is None else find_program
    fetch_tags = local_model_tags if fetch_tags is None else fetch_tags
    checks = {
        "windows": "ok" if platform == "win32" else "blocked",
        "python_3_12": "ok" if tuple(version)[:2] == (3, 12) else "blocked",
        "reviewed_public_sources": "ok" if sources_match(root) else "blocked",
    }
    executables = {
        "git": "git", "node": "node", "npm": "npm.cmd", "ollama_cli": "ollama",
    }
    for name, program in executables.items():
        checks[name] = "ok" if find_program(program) else "blocked"
    checks["model_tag"] = "blocked"
    if (not isinstance(model, str) or not MODEL_PATTERN.fullmatch(model)
            or "://" in model):
        checks["model_tag"] = "invalid"
    elif (checks["windows"] == "ok" and checks["python_3_12"] == "ok"
          and checks["reviewed_public_sources"] == "ok"
          and all(checks[name] == "ok" for name in executables)):
        try:
            checks["model_tag"] = "ok" if model in fetch_tags() else "not_installed"
        except (PreflightBlocked, OSError, ValueError, TypeError):
            checks["model_tag"] = "unavailable"
    ready = all(value == "ok" for value in checks.values())
    return {
        "status": "ready_for_manual_smoke" if ready else "blocked",
        "checks": checks, "mode": "read_only_preflight",
        "inference_performed": False, "code_executed": False,
        "remote_network_used": False, "merge_allowed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma3:1b",
                        help="Exact installed model tag; no inference")
    args = parser.parse_args(argv)
    try:
        result = readiness(args.model)
    except Exception:
        result = {
            "status": "blocked", "reason": "unexpected_preflight_failure",
            "inference_performed": False, "merge_allowed": False,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ready_for_manual_smoke" else 2


if __name__ == "__main__":
    raise SystemExit(main())
