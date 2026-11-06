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

This audit branch repins source integrity SHA-1 Git blobs and retains the review launcher target `codex/v02d-real-ollama-local-smoke` so it is suitable for PR #5 integration after review. The changed first-task source pins are updated for this review branch; source pins must be checked again if source code changes. Run full exact-head tests and Windows smoke acceptance before any rollout. Do not combine this with deployment or merge.

**Not fixed:** process-restart duplicate request IDs, cancellation of in-flight Ollama calls, stale responses after client disconnect, and OS isolation of trusted repository test scripts. These remain release blockers for any general-purpose or remote Worker Bee. No Tailscale/mobile/hardware acceptance is implied.

## 2026-11-06 Step 1 review: logical STOP, not hard model termination

A **separate, unmerged** Baby Vision review branch adds `HerbieGatewayClient.cancel(request_id)` and an optional `cancel_event` for `infer()`. On a local STOP, the client refuses a new request or discards a response received after the STOP signal. The bounded worker can receive a caller-supplied `request_id` and `cancel_event`; it now checks the STOP state between trusted workflow stages and refuses to create a review-ready packet after cancellation.

The matching **private**, separately reviewed gateway candidate adds authenticated `POST /v1/worker/cancel` with body `{"schema_version":1,"request_id":"canonical-uuid"}`. For an accepted running ID it records `status: cancellation_recorded`; for already completed work it returns `status: already_finished`. Both replies explicitly include `inference_stopped: false`. The gateway refuses to publish a successfully completed reply if logical cancellation was recorded while the request was active. Invalid IDs and credentials fail closed. Only exact reviewed source Git blobs are eligible for opt-in local source loading.

**Critical limits:** The cancellation endpoint does **not** interrupt the underlying Ollama HTTP request, kill a running npm subprocess, free the single-inference slot early, persist a cancellation across server restart, or provide a motor emergency stop. A STOP event is a caller-controlled signal; a consumer must set it and use the same request UUID when separately calling `cancel()`. The older pinned H.E.R.B.I.E. #93 gateway does **not** expose the new endpoint; calling `cancel()` against it fails closed. Existing read-only and real-Ollama smoke remains pinned to the original private gateway unless the separate reviewed cancel candidate is explicitly chosen. DO NOT enable remote listeners, automation, or untrusted repository execution based on these tests.

Acceptance before integrating these two branches: review the new private gateway source against its pinned hash, run its local synthetic gateway tests, pass all public client/worker regression and source-pin checks, then reconcile both PRs without publishing any private H.E.R.B.I.E. code to the public repository. Full process interruption and reliable restart behavior remain separate work.
