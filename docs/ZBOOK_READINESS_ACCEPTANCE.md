# ZBook manual acceptance — staged, read-only first

This work is staged in **Baby Vision draft PR #5**, not merged, deployed or running on your ZBook.

## Step A — read-only preflight
When at your own ZBook, use a **reviewed checkout** of branch `codex/v02d-real-ollama-local-smoke`. The new preflight command is:

```powershell
py -3.12 scripts/zbook_readiness.py --model gemma3:1b
```

The preflight reads the versions **by availability**, not by running installers: it checks Windows, Python **3.12**, Git, Node, npm.cmd and the Ollama CLI; validates exact reviewed SHA-1 **Git blob IDs** of four Baby Vision source files; and makes one read-only loopback GET to `http://127.0.0.1:11434/api/tags` to see whether the exact model tag is already installed. It performs **no model generation** and no private source import, cloning, installation, approvals, tests, edits or remote requests. It prints one sanitized JSON status with fixed check codes only. If missing dependencies, model or wrong source, status is `blocked` and exit code 2.

**Reminder:** The complete CMD launcher performs the *Git clones* first, verifies exact hashes (including the **private** H.E.R.B.I.E. gateway), then invokes this preflight. Preflight alone cannot confirm that the private gateway source is legitimate; the launcher must still verify its hard-coded pin before importing it.

## Step B — real opt-in local acceptance, only once the preflight is ready

Run the reviewed `scripts/run_zbook_local_smoke.cmd` on the ZBook. It clones two review branches (private H.E.R.B.I.E. clone requires **your own** existing authorized GitHub access), verifies fixed Git blob hashes, invokes Step A, then deliberately requests **real local Ollama** inference and executes the fixed Node test only in a newly generated **trusted synthetic fixture**. This is not a sandbox for arbitrary downloaded repositories. No generated model command can execute.

Do **not** upload credentials, private Herbie source, prompts, or unredacted debug logs. Share only the sanitized result JSON or fixed reason code and rough total duration. If the model is not installed, the preflight **blocks**; it never downloads a model.

## Step C — release barriers

Even a successful real-model smoke **does not prove**:
- Cancellable/stale responses after client disconnect or service restart.
- Persistent idempotency or durable replay prevention.
- Secure remote/Tailscale two-device operation.
- Isolation of user/untrusted repository test scripts, device safety, or permission boundary.

Keep public Baby Vision PR #5 and audit issue #6 open until those decisions are explicitly reviewed. The private H.E.R.B.I.E. gateway is still on draft PR #93's branch, not private main.

GitHub CI checks the preflight and launcher on a **hosted Windows runner with mocks** and the existing Python suite. It does not test your actual ZBook, installed Ollama, or real inference.

## 2026-11-06 host-execution opt-in audit (separate, unmerged branch)

The historical `agents/first_task.py` and `agents/gateway_first_task.py` **command-line** entry points now refuse to run host npm tests by default. An owner must explicitly supply `--allow-trusted-host-tests` for a repository they have personally reviewed. The gateway CLI records a sanitized blocked result without calling the worker when the flag is absent. The original reviewed `run_zbook_local_smoke.cmd` still uses an internally generated, known trusted fixture through the Python API; the new CLI gate does not add a sandbox or authorize untrusted repositories.

This audit branch repins source integrity SHA-1 Git blobs and temporarily points its separate launcher at the audit branch, to avoid running unreviewed files. **Before integrating** into PR #5's named branch, restore the launcher target to `codex/v02d-real-ollama-local-smoke`, update its matching blob pins if sources change again, and run full exact-head local checks and Windows smoke acceptance. Do not combine this with deployment or merge.

**Not fixed:** process-restart duplicate request IDs, cancellation of in-flight Ollama calls, stale responses after client disconnect, and OS isolation of trusted repository test scripts. These remain release blockers for any general-purpose or remote Worker Bee. No Tailscale/mobile/hardware acceptance is implied.
