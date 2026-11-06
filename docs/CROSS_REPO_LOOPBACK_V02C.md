# V0.2c — Baby Vision ↔ H.E.R.B.I.E. loopback integration

**Status: local synthetic integration only.** The actual Baby Vision client and H.E.R.B.I.E. gateway code were exercised together on one temporary test machine using a fake Ollama HTTP server. There is no real Ollama inference, older-PC connection, LAN, Tailscale or iPhone verification. No remote service or deployment has been enabled.

## Related draft PRs

- Baby Vision V0.2a PR #3: https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/3 (head f4daaeb36434aefb1c24e0e7af54f3b112e84db2)
- H.E.R.B.I.E. V0.2b PR #86: https://github.com/jimedusot-beep/Herbie/pull/86 (head cf66e1c2579709776eb535afd50bb3856447a1ea)
- V0.2c is stacked on Baby Vision PR #3. Existing draft PRs remain unchanged; retest after upstream revisions change.

## Scope

1. Adds HerbieGatewayClient.health(), a bounded authenticated request to /v1/worker/health. It validates the exact minimal response schema. Gateway health **does not mean** that real Ollama inference is working.
2. Adds integration/test_cross_repo_gateway.py. It imports the reviewed H.E.R.B.I.E. gateway source from a separately checked out PR #86 revision, starts the actual gateway and a fake local Ollama process, then sends HTTP calls using the actual Baby Vision client.
3. Uses new random test tokens, strictly loopback networking, and no model files, private memories, cloud services, shell tools, GitHub mutations or robotics hardware.

The integration test checks successful round trips, incorrect-token denial, disallowed models and task types, separate call contexts, a model outage, nonretrying behavior and authenticated gateway health.

## Repeat without disturbing local H.E.R.B.I.E. development

Use **separate reviewed checkouts** of Baby Vision V0.2c and H.E.R.B.I.E. PR #86. Do not reset or switch the live Companion V2.1 working tree.

PowerShell from the Baby Vision V0.2c checkout (adjust the path):

    $env:HERBIE_WORKER_GATEWAY_PY = "C:/Review/Herbie-Gateway/socratic-agent/socratic_agent/worker_gateway.py"
    py -3.12 -m unittest discover -s tests -p 'test_*.py' -v
    py -3.12 -m unittest discover -s integration -p 'test_*.py' -v
    Remove-Item Env:HERBIE_WORKER_GATEWAY_PY

Linux/macOS from the same checkout:

    HERBIE_WORKER_GATEWAY_PY=/path/to/Herbie/socratic-agent/socratic_agent/worker_gateway.py python -m unittest discover -s integration -p 'test_*.py' -v

The integration suite **fails explicitly** when HERBIE_WORKER_GATEWAY_PY is missing or points to an unavailable source file. The ordinary unit tests in tests/ do not require a H.E.R.B.I.E. checkout.

## Verified in the local development container

- Original Baby Vision client tests: 7 passed.
- Original H.E.R.B.I.E. gateway tests: 13 passed.
- Revised Baby Vision client tests with authenticated health: 9 passed.
- Actual client → gateway → fake Ollama HTTP integration: 7 passed.
- Python syntax compilation of changed files: passed.
- Baby Vision PR #3 GitHub CI: completed successfully.
- H.E.R.B.I.E. PR #86 GitHub CI: failed, with missing job-step/log evidence at last review; **do not interpret that as passing**.

These checks do not establish compatibility with the newest unmerged H.E.R.B.I.E. Companion branches or prove real model accuracy.

## Blockers before using separate machines

1. Review both protocols and the latest local Companion changes, then resolve any conflicts.
2. Obtain successful H.E.R.B.I.E. tests in a reliable runner or reproduce the approved suites locally; investigate GitHub runner startup failures separately.
3. Verify one genuine model call through the gateway on the ZBook, keeping all data synthetic and the service bound to localhost.
4. Independently configure and test encrypted, authenticated private networking. The mobile dashboard must not hold a gateway bearer token.
5. Test failures, delays, token revocation and device disconnections on actual computers.
6. Design an authenticated TLS direct-LAN fallback separately. Never assume that remote Tailscale access guarantees air-gapped LAN access.
7. Only then integrate this transport into one bounded Baby Vision worker. Any code execution requires separate isolation and human approval.

Do not merge, deploy, enable remote listeners, open router ports, expose raw Ollama or modify personal memory/robotics controls as part of this milestone.
