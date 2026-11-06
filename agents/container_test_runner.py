"""Opt-in, fail-closed Docker test runner for reviewed local Git worktrees.

This protects the npm test invocation only. The caller still creates/removes
a Git worktree on the HOST, so it must NEVER handle an untrusted Git repository.
No installation, image pull, remote daemon, shell, or host npm fallback.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4


IMAGE_PATTERN = re.compile(
    r"(?:[a-z0-9]+(?:[._/-][a-z0-9]+)*(?::[0-9]+)?/)*"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}\Z"
)


class SandboxUnavailable(RuntimeError):
    """Sanitized refusal; host secrets, image and paths are never included."""


def run_container_npm_test(checkout, *, image, timeout=90):
    """Run fixed npm test without network, host writes, or Docker socket mount.

    Uses only a previously loaded, digest-pinned Linux Node image. All stdout
    and stderr is intentionally discarded, bounding hostile output on the host.
    Stop/timeout removes the named container; does not promise process-level
    or hypervisor-grade security against malicious code.
    """
    if not isinstance(image, str) or not IMAGE_PATTERN.fullmatch(image):
        raise SandboxUnavailable("A digest-pinned local image is required")
    if type(timeout) not in (int, float) or not 0 < timeout <= 120:
        raise SandboxUnavailable("Invalid container timeout")
    if any(os.environ.get(k) for k in (
            "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH", "DOCKER_API_VERSION")):
        raise SandboxUnavailable("Explicit Docker remote/context overrides are not permitted")
    binary = shutil.which("docker")
    if not binary:
        raise SandboxUnavailable("Local Docker CLI unavailable; no host fallback")
    path = Path(checkout).resolve(strict=True)
    if not path.is_dir() or "," in str(path) or "\n" in str(path) or "\r" in str(path):
        raise SandboxUnavailable("Invalid container worktree path")
    try:
        context = subprocess.run(
            [binary, "context", "inspect", "--format",
             "{{json .Endpoints.docker.Host}}"],
            check=True, capture_output=True, text=True, timeout=8)
        endpoint = json.loads(context.stdout.strip())
        if not isinstance(endpoint, str) or not endpoint.startswith(("npipe://", "unix://")):
            raise ValueError("Nonlocal engine")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        raise SandboxUnavailable("Docker engine must use a local socket") from None

    # Deliberately use an unpredictable name and force cleanup even on timeout.
    name = "bv-reviewed-test-" + uuid4().hex
    cmd = [
        binary, "run", "--rm", "--name", name, "--pull=never",
        "--network=none", "--read-only",
        "--user=65534:65534", "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=512m", "--cpus=1",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--mount", "type=bind,source=" + str(path)
            + ",target=/workspace,readonly",
        "--workdir=/workspace",
        "--env=CI=1", "--env=HOME=/tmp",
        "--env=NPM_CONFIG_CACHE=/tmp/.npm",
        "--entrypoint=npm",
        image, "test",
    ]
    try:
        # No PIPE capture: a malicious script could otherwise exhaust RAM
        # with unbounded output. Return code is enough for this first task.
        result = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout + 10, check=False)
        return subprocess.CompletedProcess(cmd, result.returncode, "", "")
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        raise SandboxUnavailable("Isolated npm test unavailable") from None
    finally:
        # A killed Docker CLI does not necessarily kill its container.
        try:
            subprocess.run(
                [binary, "rm", "-f", name], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
