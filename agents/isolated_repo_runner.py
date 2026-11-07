"""Full-pipeline local container boundary for review-only repository tasks.

Host does NOT invoke Git, npm, or untrusted Python. The approved container
executes all source checkout, edit, patch and npm subprocesses. This requires
an already-present, operator-reviewed image with Python 3, Git, Node and npm.
No install, pull, remote daemon, fallback, or user-code stdout passthrough.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

IMAGE = re.compile(
    r"(?:[a-z0-9]+(?:[._/-][a-z0-9]+)*(?::[0-9]+)?/)*"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}\Z"
)
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
LIMIT = 65536
TIME_LIMIT = 320


class IsolationBlocked(RuntimeError):
    """Generic fail-closed status; never includes untrusted source or paths."""


def _environment():
    # The local Docker CLI receives no Ollama/Herbie bearer credentials,
    # HTTP proxy configuration, Git config overrides, or other app secrets.
    allowed = ("PATH", "SystemRoot", "WINDIR", "USERPROFILE", "HOME",
               "TEMP", "TMP", "TMPDIR", "XDG_RUNTIME_DIR")
    return {k: os.environ[k] for k in allowed if k in os.environ}


def _validate(repo, image, base, proposal):
    if not isinstance(image, str) or not IMAGE.fullmatch(image):
        raise IsolationBlocked("Approved digest-pinned local image required")
    if base != "HEAD" and (not isinstance(base, str) or not COMMIT.fullmatch(base)):
        raise IsolationBlocked("An exact commit or HEAD is required")
    if (not isinstance(proposal, dict) or set(proposal) != {"script", "reason"}
            or proposal["script"] != "npm run test:unit"
            or not isinstance(proposal["reason"], str)
            or not proposal["reason"].strip() or len(proposal["reason"]) > 500):
        raise IsolationBlocked("Unapproved proposal")
    try:
        original = Path(repo)
        if original.is_symlink():
            raise IsolationBlocked("Source path must not be a symbolic link")
        source = original.resolve(strict=True)
        runner = (Path(__file__).resolve().parent / "isolated_worker_entry.py")
        if (not source.is_dir() or not runner.is_file()
                or runner.is_symlink() or
                any("," in str(p) or "\n" in str(p) or "\r" in str(p)
                    for p in (source, runner))):
            raise IsolationBlocked("Invalid source or trusted runner path")
    except (OSError, ValueError, TypeError, RuntimeError):
        raise IsolationBlocked("Invalid source or trusted runner path") from None
    return source, runner


def _check_local_docker(binary, env):
    try:
        result = subprocess.run(
            [binary, "context", "inspect", "--format",
             "{{json .Endpoints.docker.Host}}"],
            capture_output=True, timeout=8, check=True, env=env)
        if len(result.stdout) > 2048:
            raise ValueError()
        target = json.loads(result.stdout)
        if (not isinstance(target, str)
                or not target.startswith(("unix://", "npipe://"))):
            raise ValueError()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise IsolationBlocked("Local container engine unavailable") from None


def _check_result(raw):
    try:
        if len(raw) > LIMIT:
            raise ValueError()
        result = json.loads(raw.decode("utf-8"))
        if (not isinstance(result, dict) or
                result.get("schema_version") != 1 or
                result.get("status") != "ready_for_human_review" or
                result.get("merge_allowed") is not False or
                result.get("test_exit_code") != 0 or
                type(result.get("baseline_test_exit_code")) is not int or
                result["baseline_test_exit_code"] == 0 or
                not isinstance(result.get("source_commit"), str) or
                not COMMIT.fullmatch(result["source_commit"]) or
                not isinstance(result.get("patch"), str) or
                len(result["patch"].encode("utf-8")) > 12000 or
                not result["patch"].startswith(
                    "diff --git a/package.json b/package.json") or
                result.get("host_git_executed") is not False or
                result.get("host_npm_executed") is not False or
                result.get("execution_mode") != "full_container" or
                result.get("untrusted_repository_approved") is not False):
            raise ValueError()
        return result
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise IsolationBlocked("Isolated worker blocked or returned invalid evidence") from None


def run_isolated_repo_task(repo, *, image, proposal, base="HEAD",
                           cancel_event=None):
    """Only Docker CLI calls occur on host; all Git and npm remain contained."""
    source, runner = _validate(repo, image, base, proposal)
    if (cancel_event is not None and
            (not callable(getattr(cancel_event, "is_set", None))
             or cancel_event.is_set())):
        raise IsolationBlocked("Worker STOP recorded before isolated execution")
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH", "DOCKER_API_VERSION", "DOCKER_CONFIG"):
        if os.environ.get(key):
            raise IsolationBlocked("Docker endpoint overrides are not permitted")
    binary = shutil.which("docker")
    if not binary:
        raise IsolationBlocked("Local container runtime missing; no host fallback")
    env = _environment()
    _check_local_docker(binary, env)
    ident = "bv-full-review-" + uuid.uuid4().hex
    cmd = [
        binary, "run", "-i", "--rm", "--name", ident,
        "--pull=never", "--network=none", "--read-only",
        "--user=65534:65534", "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=512m", "--memory-swap=512m",
        "--cpus=1", "--ulimit=nofile=128:128",
        "--tmpfs=/work:rw,nosuid,nodev,size=256m",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m",
        "--mount", "type=bind,source=" + str(source)
            + ",target=/source,readonly",
        "--mount", "type=bind,source=" + str(runner)
            + ",target=/runner/isolated_worker_entry.py,readonly",
        "--workdir=/work", "--env=CI=1", "--env=HOME=/tmp",
        "--env=NPM_CONFIG_CACHE=/tmp/.npm",
        "--entrypoint=python3", image,
        "-I", "/runner/isolated_worker_entry.py",
    ]
    payload = json.dumps({"base": base, "proposal": proposal},
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > 4096:
        raise IsolationBlocked("Isolated request too large")
    output = bytearray()
    overflow = [False]
    proc = None
    status = None
    reader = None
    clean = False
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env)
        def drain():
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                if len(output) + len(chunk) <= LIMIT:
                    output.extend(chunk)
                else:
                    overflow[0] = True
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
        except OSError:
            raise IsolationBlocked("Could not deliver isolated task") from None
        deadline = time.monotonic() + TIME_LIMIT
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise IsolationBlocked("Isolated task cancelled; container cleanup required")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IsolationBlocked("Isolated task timed out; container cleanup required")
            try:
                status = proc.wait(timeout=min(0.5, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        reader.join(timeout=6)
        if reader.is_alive() or overflow[0] or status != 0:
            raise IsolationBlocked("Isolated task failed or emitted oversized evidence")
    except (OSError, subprocess.SubprocessError):
        raise IsolationBlocked("Isolated container failed") from None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.SubprocessError:
                pass
        # --rm may have removed the container already. Force remove otherwise.
        # Never release success if the Docker daemon cannot confirm it is gone.
        try:
            subprocess.run([binary, "rm", "-f", ident], env=env,
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
            remaining = subprocess.run([binary, "inspect", ident], env=env,
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
            clean = remaining.returncode != 0
        except (OSError, subprocess.SubprocessError):
            clean = False
    if not clean:
        raise IsolationBlocked("Unable to verify container cleanup")
    return _check_result(bytes(output))
