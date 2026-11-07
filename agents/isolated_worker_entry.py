"""Trusted entrypoint executed INSIDE a preapproved offline Linux container.

All source-repository Git, checkout, package edits, diff and npm commands
remain inside this same container. This module never runs on the host.
Its only stdout is bounded machine-readable JSON (no arbitrary test logs).
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


SCRIPT = "npm run test:unit"
UNIT_SCRIPT = "node --test tests/*.test.cjs"
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
MAX_PACKAGE_BYTES = 65_536
MAX_PATCH_BYTES = 12_000


def _run(argv, *, cwd=None, timeout=30):
    result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            check=False, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError("Isolated command failed")
    return result


def _output(argv, *, cwd=None, limit=MAX_PATCH_BYTES, timeout=30):
    # Spool into container-only tmpfs, rather than capture unbounded hostile data.
    with tempfile.TemporaryFile() as file:
        result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=file, stderr=subprocess.DEVNULL,
                                check=False, timeout=timeout)
        if result.returncode != 0 or file.tell() > limit:
            raise RuntimeError("Isolated output invalid or oversized")
        file.seek(0)
        return file.read(limit + 1).decode("utf-8", errors="strict").strip()


def _test(checkout):
    # No shell invocation, installs, network, or test-log collection.
    try:
        result = subprocess.run(["npm", "test"], cwd=checkout,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                check=False, timeout=90)
        return result.returncode
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("Isolated npm test unavailable") from None


def _proposal(body):
    if not isinstance(body, dict) or set(body) != {"base", "proposal"}:
        raise ValueError("Invalid isolated task")
    base = body["base"]
    if not isinstance(base, str) or (base != "HEAD" and not COMMIT.fullmatch(base)):
        raise ValueError("Invalid requested revision")
    proposal = body["proposal"]
    if (not isinstance(proposal, dict) or set(proposal) != {"script", "reason"}
            or proposal["script"] != SCRIPT or not isinstance(proposal["reason"], str)
            or not proposal["reason"].strip() or len(proposal["reason"]) > 500):
        raise ValueError("Invalid approved proposal")
    return base, proposal


def _eligible(package):
    if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
        raise ValueError("Invalid package")
    scripts = package["scripts"]
    if (scripts.get("test:unit") != UNIT_SCRIPT or
            any(k in scripts for k in ("test", "pretest", "posttest",
                                       "pretest:unit", "posttest:unit"))):
        raise ValueError("Repository is not eligible")


def execute(body, *, _test_workspace=None):
    base, proposal = _proposal(body)
    # Production uses /work, a container-only bounded tmpfs. The optional
    # test workspace is a unit-test dependency only; it is NOT read from input.
    checkout = (Path("/work") if _test_workspace is None
                else Path(_test_workspace)) / "checkout"
    env = dict(os.environ)
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TEMPLATE_DIR": "/dev/null", "GIT_ALLOW_PROTOCOL": "file",
                "GIT_TERMINAL_PROMPT": "0"})
    # The entrypoint's process environment is fixed by the Docker runner;
    # subprocesses inherit only container values, never host environment.
    os.environ.update(env)
    _run(["git", "-c", "core.hooksPath=/dev/null", "-c",
          "safe.directory=/source", "clone", "--no-local", "--no-checkout",
          "--", "/source", str(checkout)], timeout=45)
    commit = _output(["git", "-C", str(checkout), "rev-parse", "--verify",
                      "--end-of-options", base + "^{commit}"], limit=100)
    if not COMMIT.fullmatch(commit):
        raise ValueError("Invalid resolved commit")
    _run(["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null",
          "checkout", "--detach", commit], timeout=30)

    file = checkout / "package.json"
    if (file.is_symlink() or not file.is_file()
            or file.stat().st_size > MAX_PACKAGE_BYTES):
        raise ValueError("Invalid package file")
    package = json.loads(file.read_text(encoding="utf-8"))
    _eligible(package)

    baseline = _test(checkout)
    if baseline == 0:
        raise ValueError("Baseline already succeeds")

    package["scripts"]["test"] = SCRIPT
    file.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    _run(["git", "-C", str(checkout), "diff", "--check"], timeout=20)
    changed = _output(["git", "-C", str(checkout), "diff",
                       "--name-only"], limit=1024)
    if changed != "package.json":
        raise ValueError("Edit escaped the approved package file")
    patch = _output(["git", "-C", str(checkout), "diff", "--",
                     "package.json"], limit=MAX_PATCH_BYTES)
    if not patch.startswith("diff --git a/package.json b/package.json"):
        raise ValueError("Invalid patch")

    result = _test(checkout)
    return {"schema_version": 1,
            "status": "ready_for_human_review" if result == 0 else "blocked",
            "merge_allowed": False,
            "test_exit_code": result,
            "baseline_test_exit_code": baseline,
            "source_commit": commit,
            "patch": patch,
            "test_output": "",
            "baseline_test_output": "",
            "proposal": proposal,
            "host_git_executed": False,
            "host_npm_executed": False,
            "execution_mode": "full_container",
            "untrusted_repository_approved": False}


def main():
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("Isolated task exceeds input bound")
        outcome = execute(json.loads(raw.decode("utf-8")))
    except Exception:
        # Never emit Git, npm, source, credentials, paths or test messages.
        outcome = {"schema_version": 1, "status": "blocked",
                   "merge_allowed": False, "reason": "isolated_task_blocked"}
    print(json.dumps(outcome, separators=(",", ":"), ensure_ascii=True))


if __name__ == "__main__":
    main()
