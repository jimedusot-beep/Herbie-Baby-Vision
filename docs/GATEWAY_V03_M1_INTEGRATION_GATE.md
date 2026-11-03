# Gateway V0.3 — M1 compatibility review

**Status:** Draft PR #5, **not approved for merge or deployment**. The code branch now includes M1 `main` commit `7d329ffa11781a1454e6a5406f1be433efb4fb51` via an explicit two-parent reconciliation commit. The cumulative PR-to-main diff remains restricted to the original gateway/client/dashboards/docs/tests and a combined `worker-tests.yml`; M1's signed-approval test dependency and both dashboards' Node tests are preserved in CI.

## Verified synthetic private/public contract

- Public client: Baby Vision PR #5 Git blob `96056a3aed2328f4a55b1030788672de61c04235`, original head `bdfe0863ca627732d45d0a3ea67ad9a2722ea9e3`.
- Private gateway: H.E.R.B.I.E. PR #93 `worker_gateway.py` Git blob `2a591120c01815698d9a0c7d4c7e3a1005b75936`. Its source remains in the **private** repository, and is absent from the public PR.
- A **private** GitHub Actions test ran the reviewed gateway with public Baby Vision client and *fake* loopback Ollama: **8/8 integration** and **4/4 negative client security** tests passed. See private H.E.R.B.I.E. PR #100 (integrated into PR #93's branch) and its [Actions result](https://github.com/jimedusot-beep/Herbie/actions/runs/41571284786).
- Client timeout default is 60 seconds, blank/whitespace responses are rejected; synthetic fixtures cover both. These do not prove a complete end-to-end 60-second deadline.

## Pending blocking acceptance requirements

1. The private H.E.R.B.I.E. PR #93 gateway is **not merged into private Herbie main** or accepted as the final companion release. Pin any updated gateway blob and re-run private tests before connecting.
2. A **real installed Ollama** model must produce usable answers on the ZBook using the exact reviewed source, with acceptable latency, STOP behavior and no private data exposure.
3. Remote/Tailscale HTTPS, stale-response and reconnect behavior, and cancellation/idempotency are **not verified**. Test no-retry safety, and implement explicit job-state guarantees before enabling automated retries.
4. The optional historical `gateway_first_task.py` runs *trusted* Node test code on the host; a disposable checkout is **not** a sandbox. Never run unknown GitHub revisions, enable autonomous patch application or treat its evidence as authorization. Keep M1's local read-only workflow as the default.
5. The older `dashboard/review.js` is separate from the merged M1 mobile read-only dashboard and must not expose a public private-report API.
6. Run the **reconciled exact-head PR #5 CI**, including all M1 regressions and the older gateway/dashboard unit tests, before any further release decision.

## Current disposition

Maintain PR #5 as **Draft** until the above are explicitly reviewed, or close it as deferred while preserving this branch and tracking the remaining live acceptance in public audit issue #6. No automatic merge or service enablement is warranted by synthetic CI.
