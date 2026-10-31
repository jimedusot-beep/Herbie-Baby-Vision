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
git clone --branch codex/v02b-worker-inference-gateway --single-branch https://github.com/jimedusot-beep/Herbie.git Herbie-Gateway-Review

ollama list

cd .\BabyVision-V02d
py -3.12 -m unittest discover -s tests -p 'test_*.py' -v

py -3.12 integration/live_ollama_smoke.py --run-live --model gemma3:1b --gateway-file "$HOME\AI-Network-Review\Herbie-Gateway-Review\socratic-agent\socratic_agent\worker_gateway.py"
```

**Important:** `gemma3:1b` is an example based on the earlier ZBook setup; use the exact model currently shown by `ollama list`. The script will **not** install or download an uninstalled model. Git cloning requires your normal GitHub authorization for the private H.E.R.B.I.E. repository.

If Ollama isn't listening at `http://127.0.0.1:11434`, the script reports a blocked check. Start your locally installed Ollama service separately, then retry. The smoke test does not start, install or reconfigure Ollama for you.

## Reviewed gateway source protection

The ZBook harness now requires the **hardened** H.E.R.B.I.E. gateway Git blob
`c27250693d9e8593a6ddb66ac567e9a68eeb8e36`. That corresponds to the
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
