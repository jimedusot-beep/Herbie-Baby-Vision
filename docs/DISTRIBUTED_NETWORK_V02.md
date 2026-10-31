# Distributed H.E.R.B.I.E. worker network — milestone 0.2a

Status: **client contract prototype only; no LAN, VPN, remote inference, job queue, or worker deployment enabled.**

## Audited baseline (2026-10-30)

- Baby Vision `main` reviewed at `64bb698def7ae8e7408ae7e777458d01b5cd6d2b`.
- H.E.R.B.I.E. `main` reviewed at `b4d307713bfde351ddfa966880e138d4b0de7286`.
- Baby Vision draft PR #2 (supervised validation) head reviewed at `f3a135bd5b4f28ff92a408b1016b348205ce64bb`. Leave it untouched; its validation snapshots are **not OS sandboxes** and Windows host execution is blocked.
- Baby Vision `agents/first_task.py` has a narrowly scoped, localhost-only Ollama client. Do not loosen its loopback checks or replace its approved task.
- H.E.R.B.I.E. `main` has a local **simulated** HTTP demo bridge and loopback-only Ollama adapter. This is **not** an authenticated worker AI service. Local Companion V2.1 work described elsewhere has not been confirmed as merged into GitHub; preserve it.

## Responsibility boundary

- **H.E.R.B.I.E. / ZBook**: local model service and future authenticated inference gateway. Private chat and memory are separate from worker task contexts. Ollama itself stays on localhost.
- **Baby Vision / older PC**: task policies, bounded workers, isolated execution, tests, and private evidence. Only this side may invoke work tools under approval rules.
- **iPhone / iPad**: eventual authenticated browser controls, never an unattended general-purpose code executor.
- **Private network**: eventually Tailscale Serve for authenticated HTTPS access, with a separately designed TLS-backed, direct LAN fallback for internet-disconnected use. Tailscale reachability while the internet is unavailable is **not** assumed.

## Contract v1 — proposal, not a deployed API

`POST /v1/worker/infer` to an independently authenticated, authorized H.E.R.B.I.E. gateway.

Request JSON (bounded to 12,000 UTF-8 bytes of prompt):

```json
{
  "schema_version": 1,
  "request_id": "3f6ee37b-6f53-4e12-8a42-93410620b7c4",
  "task_type": "coding",
  "model": "qwen2.5-coder:1.5b",
  "prompt": "Explain the proposed bounded task."
}
```

Success JSON:

```json
{
  "schema_version": 1,
  "request_id": "3f6ee37b-6f53-4e12-8a42-93410620b7c4",
  "model": "qwen2.5-coder:1.5b",
  "reply": "A bounded response."
}
```

The caller provides a canonical UUID as `request_id`; the reply must echo it. The worker client sends a bearer credential in the Authorization header, never within the request JSON. Remote URLs are limited to authenticated TLS endpoints under `*.ts.net`; plain HTTP is permitted **only for explicit loopback fixtures**. It refuses redirects, proxies, oversized or malformed responses, and any silent retry. The client has no subprocess, filesystem mutation, or GitHub write functionality.

**Authentication caveat:** The client alone cannot prove that a server enforces the token. A later Herbie gateway must verify the token, use constant-time comparisons or an appropriate authentication library, enforce authorization, rate/concurrency limits, model allowlists, input/output bounds, and handle idempotency where relevant. The gateway must never forward worker instructions to private conversation memory or robotics controls. A VPN does not replace API authentication.

There is no open gateway port, generated credential, deployment script, or auto-start added by this milestone. `agents/herbie_gateway_client.py` is an isolated module; the existing bounded worker continues to use its existing localhost adapter until an integrated end-to-end test passes.

## Test evidence for this milestone

Local synthetic fixtures, with **no real inference**:

```sh
python -m unittest discover -s tests -p 'test_herbie_gateway_client.py' -v
```

Seven local contract tests passed on the development workspace. These prove only input checks, shape matching and error behavior; they do **not** verify real TLS/Tailscale, two-PC operation, Windows worker isolation, offline model inference, or physical iPhone Safari behavior. The full Baby Vision suite and hosted checks must run on the PR before merge consideration.

## Next safely bounded development step

1. Audit the latest local H.E.R.B.I.E. development branch before modifying its runtime.
2. Create a separate **disabled-by-default** authenticated gateway with a loopback smoke test and a temporary test credential. Never expose raw Ollama.
3. Exercise this client against that gateway locally, then across two authorized Tailscale devices using HTTPS and revocable credentials.
4. Verify loss of connection, incorrect token, mismatched request IDs, and missing model behavior.
5. Only then integrate with Baby Vision's approved scoped worker and consider a small persistent queue. Use an isolated VM/container for untrusted code execution; a Git checkout is insufficient.

No change to `main`, automatic merges, deployments, public endpoints or physical devices is authorized by this document.
