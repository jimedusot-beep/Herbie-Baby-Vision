# V0.2d — Real local Ollama smoke test on the ZBook

**Review-only. Not deployed.** This stage prepares an **explicitly opt-in** test of a real installed Ollama model using the actual Baby Vision client and H.E.R.B.I.E. gateway code. A synthetic local test or passing CI is **not** proof that the ZBook has run the live model.

## Dependencies

- Baby Vision PR #3 (client): https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/3
- Baby Vision PR #4 (client integration): https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/4
- H.E.R.B.I.E. PR #86 (gateway): https://github.com/jimedusot-beep/Herbie/pull/86

This V0.2d branch is stacked on Baby Vision PR #4. The PRs remain independent and unmerged.

**Do not use a live Companion V2.1 working tree.** Use separate fresh clones of the two review branches. Importing a Python module executes its code, so verify that the `worker_gateway.py` file is really the reviewed PR #86 source before using it. The script checks its reviewed Git blob SHA and executes those same verified bytes, with any unknown revision blocked until separately reviewed and re-pinned.

## Simpler Windows option — one reviewed CMD launcher

If you prefer not to type the clone/test commands below, open the
[ZBook smoke-test launcher](../scripts/run_zbook_local_smoke.cmd) on this same
draft branch, inspect its source, then use GitHub's **Raw** / **Download raw**
to save it as `run_zbook_local_smoke.cmd`.

On your ZBook, open **Command Prompt** and run the saved file, for example:

```bat
"%USERPROFILE%\\Downloads\\run_zbook_local_smoke.cmd"
```

The launcher requires Git, Python 3.12, and an already-running Ollama installation
with `gemma3:1b`. It creates a new review directory under your Windows profile,
clones the two dedicated branches into that directory, checks the committed
Git blob IDs of the approved client, smoke harness and gateway, and then calls
the existing sanitized local-only test. **It will refuse a changed/unreviewed
source version.** It never modifies `C:\\Users\\jimso\\Herbie`, stores a
gateway token, starts a remote listener, merges, or deploys. Review copies are
left on disk so you can inspect them.

If Git asks you to sign in, use your normal GitHub credential manager; do not
paste credentials into the command file or chat. Windows may warn about
downloaded command files—inspect before allowing execution, rather than
blindly bypassing security controls. This convenience launcher has **not been
run on your physical ZBook**, so its Windows execution is still unverified.

## On the Windows ZBook — PowerShell

Use a PowerShell terminal (not CMD). Start from a new directory to avoid disturbing any existing H.E.R.B.I.E. work. Commands do not merge, reset, or deploy anything:

```powershell
mkdir "$HOME\AI-Network-Review" -ErrorAction SilentlyContinue
cd "$HOME\AI-Network-Review"

git clone --branch codex/v02d-real-ollama-local-smoke --single-branch https://github.com/jimedusot-beep/Herbie-Baby-Vision.git BabyVision-V02d
git clone --branch integration/herbie-engineering-20261031 --single-branch https://github.com/jimedusot-beep/Herbie.git Herbie-Gateway-Review

ollama list

cd .\BabyVision-V02d
py -3.12 -m unittest discover -s tests -p 'test_*.py' -v

py -3.12 integration/live_ollama_smoke.py --run-live --model gemma3:1b --gateway-file "$HOME\AI-Network-Review\Herbie-Gateway-Review\socratic-agent\socratic_agent\worker_gateway.py"
```

**Important:** `gemma3:1b` is an example based on the earlier ZBook setup; use the exact model currently shown by `ollama list`. The script will **not** install or download an uninstalled model. Git cloning requires your normal GitHub authorization for the private H.E.R.B.I.E. repository.

If Ollama isn't listening at `http://127.0.0.1:11434`, the script reports a blocked check. Start your locally installed Ollama service separately, then retry. The smoke test does not start, install or reconfigure Ollama for you.

## Reviewed gateway source protection

The ZBook harness now requires the **hardened** H.E.R.B.I.E. gateway Git blob
`feb3910ab8feab8210db03dff3a7d2a007a526b0`. That corresponds to the
gateway changes in H.E.R.B.I.E. draft PR #86: bounded connection handlers,
HTTP header/JSON ambiguity rejection, UTF-8 response limits and a 60,000-byte serialized-response cap.

After hashing, the harness compiles and executes **the verified bytes in
memory**, rather than importing the same pathname a second time. This prevents
a modified source file or stale Python bytecode from being used after the
verification check. The hash is a version pin, not a guarantee against
malicious code in an untrusted source; only reviewed branch content should be
run. Future gateway modifications require a new review and pin update.

## What runs and what does not

- The tool requires an explicit `--run-live` flag.
- The gateway is loaded from a reviewed local file and started in-process on **127.0.0.1 with an ephemeral port**.
- It uses a freshly generated in-memory bearer token and a model allowlist containing only the specified installed model.
- The authenticated health request must pass.
- A deliberately incorrect token must fail authentication.
- Baby Vision sends one short, non-private testing prompt through the real gateway to Ollama. No tools or private memories are sent.
- The temporary server is shut down in a `finally` block.
- The report contains only a pass/blocked status, the model identifier, a response length, and elapsed seconds; it does **not** contain response text, prompt text, credentials, or raw HTTP bodies.
- It does not expose a LAN port, enable Tailscale, contact an iPhone, or let any generated answer run as code.

Run without `--run-live` to confirm the tool refuses to start anything:

```powershell
py -3.12 integration/live_ollama_smoke.py
```

Expected output: `{"status":"blocked","reason":"explicit_run_live_flag_required","merge_allowed":false}` (field order may differ).

### Typical output after an actual successful model call

```json
{"status":"completed","mode":"real_model_localhost","gateway_health":"passed","incorrect_token_rejected":true,"inference":"nonempty_reply","model":"gemma3:1b","network_access":"loopback_only","real_remote_devices_tested":false,"merge_allowed":false,"latency_seconds":0.0,"reply_characters":0}
```

The numeric fields here are **illustrative placeholders**, not measured results; in a real successful run, `reply_characters` will be greater than zero.

Failure outputs use controlled reason codes, such as `ollama_not_reachable_on_loopback`, `requested_model_not_installed`, or `real_model_inference_failed`. The script does not claim successful inference when a request fails.

## Test separation

To run synthetic cross-repository tests (no real model):

```powershell
$env:HERBIE_WORKER_GATEWAY_PY = "$HOME\AI-Network-Review\Herbie-Gateway-Review\socratic-agent\socratic_agent\worker_gateway.py"
py -3.12 -m unittest discover -s integration -p 'test_cross_repo_gateway.py' -v
Remove-Item Env:HERBIE_WORKER_GATEWAY_PY
```

The new `tests/test_live_ollama_smoke.py` checks preflight, no-opt-in behavior, model detection, redirect refusal, and sanitized reporting with fixtures. **It never calls the real model.**

## Acceptance criteria for the next real-device milestone

The first success is an actual **local** ZBook run returning `status: completed`, positive `reply_characters`, and measured latency, after correctly rejecting the wrong token.

Before connecting an older PC or iPhone, separately review:
1. The local Companion V2.1 changes and their interaction with the gateway.
2. The Herbie gateway PR #86 CI failures; do not certify code solely from unit fixtures.
3. Tailscale HTTPS settings and token revocation, with real enrolled-device checks.
4. Power/CPU and memory usage under concurrent requests.
5. A safe, authenticated Windows worker execution environment with restricted tools and no production credentials.

**No merges, remote access enablement, private memory access, or live robotics actions are authorized by this test.**

## Connection contract hardening (November 1, 2026)

- Gateway code on PR #86 now rejects **empty and whitespace-only model output**, including a fake or injected inference result. The Baby Vision client independently rejects the same.
- Normal client timeout is **60 seconds**, giving the gateway's **45-second Ollama socket timeout** a 15-second allowance for overhead. This is a per-operation socket limit, **not a guaranteed total wall-clock or cancellation budget**; slow trickle responses and network failures still require explicit acceptance tests.
- The synthetic cross-repository test now calls the **same reviewed-bytes loader** as the opt-in live smoke harness. It refuses unknown gateway source and never imports an unverified pathname.
- Both the live harness and the Windows launcher have updated expected Git blobs. **Do not remove the source checks** to get a green test: review any changed gateway source and update pins only after code review.
- Existing constraints remain: loopback-only, one synthetic/real inference at a time, no private memories, no tools, no remote port, no GitHub merge, no hardware controls.

**Remaining**: Run the full Python suites and the reviewed cross-repo tests on exact current SHAs; a real ZBook Ollama call has not been executed here. There is still no server-side client-disconnect cancellation, idempotent duplicate-request registry or approved remote two-PC test. These gaps are tracked in the diagnostic issues.

**November 1 integration note:** The ZBook examples now clone the unified [H.E.R.B.I.E. #93](https://github.com/jimedusot-beep/Herbie/pull/93) candidate rather than isolated #86. The gateway source bytes are identical and still pinned; the broader H.E.R.B.I.E. runtime does **not** automatically start. This is a local smoke test, not release approval.

## Worker Bee #1 full local fixture acceptance (November 1, 2026)

The reviewed Windows launcher now opts into **two real local model requests**, not only the original liveness smoke: (1) authenticated gateway inference with an intentionally wrong-token check, then (2) a JSON proposal from the installed model for the existing bounded `npm test` task.

The second test creates a **new disposable, trusted Git repository fixture** containing a known tiny `package.json` and Node test, calls `agents/gateway_first_task.py` through the reviewed gateway, and checks that the proposal only adds the approved `npm test` alias, that the fixed Node test passes, and that the source checkout remains unchanged. It never clones a third-party codebase or runs model-supplied commands. It deliberately sends **no private H.E.R.B.I.E. source or personal memory** into the model.

The fixture repo and intermediate test evidence are cleaned up. Output is a sanitized summary with `worker_fixture: "review_ready"` and `worker_tests: "passed"` **only after real checks pass**. Invalid model JSON, missing Node/Git, bad credentials, or test failures report blocked, never success. A small installed model may not reliably return the required JSON; that is a measurement we need to make on the actual ZBook, not a reason to weaken validation.

To run the same combined acceptance manually, add `--run-fixture-task` to the local `integration/live_ollama_smoke.py --run-live ...` command. This **still has not been run on your physical ZBook** in this development session and does not prove multi-PC networking, physical movement, natural voice or a general coding agent.

## Windows failure-category diagnostics (November 1, 2026)

A physical ZBook with Python 3.12.10, Node 26 and Ollama 0.40.12 completed the local H.E.R.B.I.E. verifier, and its Baby Vision gateway returned a real model response, but the separate bounded worker fixture initially reported `bounded_worker_fixture_failed`. A confirmed Windows `npm` subprocess resolution failure was fixed by selecting `npm.cmd` on Windows; the fixture still blocked afterward with both `gemma3:1b` and `gemma3:4b`. The root cause of the remaining worker failure has **not** yet been established.

The local smoke harness now reports distinct, **non-sensitive** reason codes instead of echoing the model reply or tracebacks:

- `bounded_worker_model_proposal_not_json`: The local model's reply was not valid standalone JSON.
- `bounded_worker_model_proposal_unapproved`: JSON parsed, but the fixed allowlist rejected its contents.
- `bounded_worker_gateway_request_failed`: The gateway inference request was unsuccessful.
- `bounded_worker_trusted_command_failed` / `bounded_worker_trusted_command_timeout`: A fixed trusted Git/npm command failed or timed out.
- `bounded_worker_fixture_local_error`: Another local fixture/validation error occurred; do not assume the model is responsible.
- `bounded_worker_post_edit_tests_failed` / `bounded_worker_review_contract_failed`: The approved test/review invariants did not pass.

These labels do not weaken proposal validation or authorize execution of model-supplied commands. The Windows launcher must be **re-downloaded and Git-blob verified** after the diagnostic script is changed because its hard-pinned smoke source SHA also changes. Do not hand-edit the expected SHA or bypass the source verification. The updated diagnostic path still requires actual on-ZBook confirmation before any claim of success or merge readiness.

## Structured output for the first real Worker Bee proposal (November 1, 2026)

Physical ZBook diagnostic verification established `bounded_worker_model_proposal_not_json` with installed `gemma3:4b`. This is specific evidence that the model's coding response, transported through the gateway, was not standalone parseable JSON. It is **not** evidence that the local Ollama inference, Windows npm invocation, or Baby Vision's fake-model fixture failed.

The updated review-only H.E.R.B.I.E. gateway adds an **explicit task type** `npm_test_alias_v1` using Ollama's local API `/api/chat` `format` JSON schema parameter. The server supplies one immutable schema: `script` must equal `npm run test:unit`; `reason` must be a nonempty string of at most 500 characters; no other keys are permitted. The model cannot select the schema, supply tools, or choose runnable commands. The request uses temperature 0 and bounded output tokens. Other task types continue to use ordinary free-form generation without a JSON schema.

Baby Vision's bounded task now uses `npm_test_alias_v1`; it **still** performs independent `json.loads` and `validate_proposal` checks before editing the disposable trusted fixture. Git/npm execution remains hardcoded and the result stays review-only, never automatically merged or deployed. The browser/voice/memory and physical robot integrations are not affected by this isolated smoke test.

Both review branches and the Windows launcher pins changed. The latest launcher verifies the Baby Vision client, smoke harness, first task, gateway task adapter and the H.E.R.B.I.E. gateway against reviewed Git blob IDs before live execution. Local ZBook checkouts must be fast-forwarded and Git hashes rechecked before the live smoke; an old downloaded launcher cannot be presumed current.

Automated synthetic tests are necessary but not sufficient. **Acceptance remains pending** until the user runs the updated local command with a real installed model and sees `status: completed`, `worker_fixture: review_ready` and `worker_tests: passed`. On schema/validation failures, do not strip Markdown, salvage arbitrary embedded JSON, weaken the allowlist or invent successful evidence.

Reference: https://docs.ollama.com/capabilities/structured-outputs
