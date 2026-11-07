# Step 3B — full checkout/edit/test isolation (review only)

**DRAFT, not merged, not deployed. No real container or hostile repository
has been executed.** This separate public Baby Vision branch is built on the
earlier Step 3 partial-container PR #33 without modifying that PR.

## What changed

For the first bounded npm-alias task, the two user-facing CLIs now have two
**mutually exclusive** modes:

1. `--allow-trusted-host-tests`: the historical flow, permitted **only** for
   an owner-reviewed trustworthy local Git fixture. It still runs host Git and
   host npm. This mode must never be presented as safe for unfamiliar code.
2. `--sandbox-image <approved-image@sha256:64-hex-digest>`: the new **whole
   repository pipeline**. The host requests only the fixed, bounded model
   proposal; this step cannot execute source repository code. It then launches
   a single local offline container that performs the remaining operations.

In full-container mode the host **does not call `git` or `npm`** on the
chosen source repo. The source repo is exposed read-only at `/source`; the
trusted entrypoint is a *separate* read-only bind mount. Within one container,
the Python entrypoint locally clones, resolves the chosen HEAD or full commit
SHA, checks out a disposable copy, reads/validates `package.json`, runs the
baseline `npm test`, writes the approved package-only alias, runs `git diff
--check` and verifies exactly `package.json` changed, runs the post-change
`npm test`, and emits a bounded JSON review packet. No host worktree is ever
created, patched, executed or removed. No model-generated shell commands are
run. The test code itself is still untrusted and runs **inside** the container.

The image must be a **previously cached, human-reviewed** Linux image with
`python3`, `git`, `node`, and `npm` already present. We do **not** build,
fetch, choose or install one in this change. Docker must be installed and
configured independently by the owner; missing Docker/image/capabilities fails
closed. Using an immutable digest is necessary, but not sufficient, to trust
an image. The image must also be audited for its OS, runtime and entrypoint.

## Isolation boundary and evidence

The local daemon is restricted to `unix://` or Windows Docker Desktop
`npipe://` endpoints. Explicit remote/context overrides are refused. The
container uses `--network=none`, `--pull=never`, a read-only root filesystem,
read-only source/entrypoint mounts, an unprivileged numeric UID/GID, dropped
capabilities, no-new-privileges, 64 processes, 512 MiB RAM, limited CPU, and
bounded scratch tmpfs. No Docker socket, host home directory, SSH keys, Git
credentials, Ollama token, or other host bind mount is intentionally supplied;
only the **selected source repository** and the reviewed entrypoint are
mounted. The selected repository itself may contain secrets, so review the
contents before exposing it to any image.

Container Git is configured without system/global Git config, templates,
interactive prompts or network protocols. Git fetch of submodules/dependencies
is not attempted. Npm dependencies must already be present in the checkout,
because the container has no network and never runs `npm install`. Test
stdout/stderr are discarded; the entrypoint emits capped structured JSON,
and the host drains stdout with bounded retained memory. Container cleanup is
attempted on success/error/timeout/STOP and must be confirmed by Docker
`inspect` before any review-ready evidence is returned.

**No automatic merge, deployment, public listener, Tailscale integration,
device control, background task, paid cloud CI, or image download.**

## Critical limitations / release HOLD

- This is a **container-design candidate, not proof of sandbox security**.
  Docker shares a kernel with its host Linux VM; Docker Desktop on Windows
  includes additional virtualization, but its precise security properties
  require owner-machine configuration and penetration testing.
- A compromised Docker daemon, malicious approved image, mount implementation
  flaw, kernel/container escape, or an overly broad selected repo can still
  expose data. Do not assert complete protection against adversarial code.
- An existing legacy Python API `run_task` and explicitly opted-in
  `--allow-trusted-host-tests` continue to run trusted fixture code through
  host Git/npm. Callers must select the **new whole-container path** for an
  unfamiliar source repository. Old partial-container npm-only functions are
  retained for compatibility and must not be misdescribed as full isolation.
- The source is a **pre-existing local Git repository path**. The host validates
  its pathname and local daemon but does not clone remote repos or run Git on
  this path. No automatic GitHub URL importing or remote network is supported.
- The host sends the **static, fixed model task** before the container is
  entered; it does not disclose source files or run repo code. Actual source
  analysis remains deliberately minimal, limited to one package.json edit.
- An honest, bounded review packet is not an authorization to merge, and
  result verification still depends on the trusted image/entrypoint.
- No physical emergency stop, actual Ollama request interruption, durable
  job completion recovery, different-UUID semantic deduplication, or real
  Windows Docker escape/permission tests are provided.
- The older ZBook smoke launcher still clones historical review branches and
  verifies historical gateway source; that command is **not** proof of this
  new mode and may intentionally block on changed source fingerprints.
  A dedicated, explicit trusted image/Windows acceptance process is needed.

## Synthetic tests and release plan

`tests/test_full_isolation_boundary.py` mocks every host Docker call and
asserts no host Git/npm operations, exact read-only mounts, no network/image
pull, local daemon policy, refusal of unpinned images, fail-closed cleanup,
bounded/untrusted output validation, and explicit dispatch into the
full-container coordinator. It separately tests the internal package-only
entrypoint logic with mock Git and npm and temporary fixture files.

`tests/test_container_test_runner.py` verifies legacy partial-container
mode remains unchanged and now checks the new CLI routing.

**Before making this runnable on unfamiliar repositories:** security review
of both new source files and their pinned SHA-1 Git blobs; all public Python,
Node, and Windows/Linux synthetic CI; real offline owner-local test using a
specifically reviewed and preinstalled Docker Desktop image; inspection of
container/host logs and mounts; adversarial test fixtures; and final human
approval. None of this authorizes automatic deployment or merging.
