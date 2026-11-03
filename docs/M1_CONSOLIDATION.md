# Baby Vision M1 — single consolidated review candidate

**Decision:** Present the completed V0.1–V0.4.4 / M1 investigation-and-proposal chain as ONE **draft pull request to `main`**. Keep the preceding component PRs as historical review branches. **Do not merge, publish, execute a patch, grant approval authority, or deploy automatically.**

## Inventory verified against GitHub

- **Base:** `main` at `64bb698def7ae8e7408ae7e777458d01b5cd6d2b` (when inspected on 2026-11-02).
- **Integration source:** `review/baby-vision-m1-acceptance-20261102` at `3a2beed576ccad0fa2e14fa7b7dc2f935dfa6467` (original draft PR #18).
- GitHub comparison: **15 commits ahead, 0 behind, 38 changed files** before the two consolidation files in this PR. GitHub reported the source PR mergeable with no conflict against `main` at inspection time.
- New integrated review includes repository search, read-only investigation, bounded proposal validation, audit/output hardening, untrusted/unsigned approval record prototype, signed-approval prototype, replay-ledger prototype, and M1 synthetic end-to-end acceptance tests.
- Five essential files in the existing combined review ZIP were byte-for-byte verified against GitHub file blob hashes: `agents/repository_search.py`, `agents/proposal_bridge.py`, `agents/signed_approval.py`, `agents/approval_replay.py`, and `tests/test_m1_acceptance.py`.

## Parallel work intentionally excluded

| Branch | Review status | Conflict | M1 decision |
| --- | --- | --- | --- |
| Old dashboard and gateway: PR #5 | Separate draft | **1 overlapping path:** `.github/workflows/worker-tests.yml` | Do not import gateway or dashboard code. The gateway can run trusted tests without an OS sandbox; it is not appropriate to combine with a read-only worker. Reconcile CI workflow separately if PR #5 is ever revived. |
| Agent 05 coordinator: PR #2 | Separate draft | **No overlapping changed paths** against the M1 chain | Defer; not needed for one reliable worker. |
| Component PRs #8–#17 | Linear stacked ancestors | No cross-branch merge needed | Included through M1 head ancestry. Keep open for review history until an explicit consolidation/closure decision. |
| M1 acceptance: PR #18 | Predecessor | Already contains all ancestor commits | Converted to **Draft**; consolidation branches from its tested head. |

A clean GitHub mergeability result means **no textual conflict at this snapshot**; it does not prove security, functionality on Windows, or equivalence with the old gateway work.

## What the integration candidate proves

A full run of `python -B -m unittest discover -s tests -p 'test_*.py' -q` on the M1 combined local package passed **143/143 tests** (Linux container, Python environment with `cryptography` installed). The fixture includes **411 committed synthetic TypeScript files**, fake model responses, review-only diff validation, output safety checks, stop/stale-data refusal, signing/replay tests. The new `m1-full-suite.yml` workflow runs the **complete GitHub checkout**, rather than just a local ZIP or a path-filtered subset, on **Python 3.9 and 3.12** with read-only repository permissions. Its result must be checked separately after this PR opens.

Earlier read-only search against pinned public Trivia Lobby source succeeded, but **did not demonstrate a real bug fix**.

## Explicit non-goals and execution boundary

- No real Ollama on the ZBook; no measure of model quality, GPU or memory.
- No model-driven patch application, Docker execution, command execution, git push/merge or remote deployment.
- Approval signatures and replay records are **prototypes only**, not a production trusted signer or Windows replay service. The old gateway/test-execution path is excluded.
- Existing `main` worker functionality is not claimed to be globally non-executing; this specific M1 addition has a read-only proposal boundary. Check all existing modules separately before any future merge.
- Do not display any evidence packets publicly; keep them local/private when live testing.

## Review gates before merge

1. Confirm the new *full suite* GitHub Actions run passes in both Python versions. Also confirm the existing `worker-tests.yml` run passes, including main's existing boundary tests.
2. Inspect the full `main...M1` diff and review the collision with PR #5's worker CI before any plan to integrate the dashboard.
3. Keep this PR **Draft** and obtain explicit human approval before promotion or merge.
4. On the ZBook later: prove local Ollama on a disposable checkout, inspect prompts/reports for secrets, measure runtime, and confirm safe STOP behavior.

**References:** PR #18 — https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/18 ; PR #5 — https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/5 ; PR #2 — https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/2 .
