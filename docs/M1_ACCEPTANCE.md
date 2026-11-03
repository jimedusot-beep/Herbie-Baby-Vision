# Baby Vision M1 — One reliable, review-only Coding Bee

**Status:** Offline integration candidate. No real Ollama inference, Windows isolation, patch execution, Docker testing, GitHub merge, or deployment is claimed.

## Why M1 exists

The repository contains two distinct development tracks: the stacked read-only source search / investigation / proposal and safety modules (draft PRs #8–#17), and an older gateway/dashboard track (PR #5, plus related work). These should **not** be merged indiscriminately. In particular, the gateway's existing trusted test workflow is not an isolated sandbox. Its static review dashboard may be reused only after an explicit evidence-format and trust-boundary review.

## Acceptance demonstrated in this candidate

`tests/test_m1_acceptance.py` constructs a disposable synthetic Git project with 411 committed TypeScript files. It exercises the actual repository scanner, two model **stubs** (investigation and diff writer), the patch validator, and saving a review-only diff and JSON evidence packet. The tests require: correct commit/citation/hash binding, complete search above the old 400-file limit, no working-tree edits, no approval or execution records, STOP refusal, stale-tree refusal, malformed patch refusal, invented citation refusal, and output symlink refusal.

The suite also uncovered a STOP-related error-path bug: `proposal_bridge.save()` could propagate an investigation exception instead of returning a `ProposalError` that its command-line caller handles. That is now normalized to a controlled refusal.

## What is **not** demonstrated

* The model stubs always return predefined correct answers. They do not establish real model quality, diagnosis correctness, or Ollama responsiveness.
* This is synthetic code. The earlier read-only smoke check on pinned Trivia Lobby proves retrieval, **not** a real bug fix.
* `git apply --check` validates whether the proposed diff could apply to a disposable checkout, but it **never applies** the patch.
* The signed decision and replay mechanisms are review prototypes, not a trusted Windows authorization service. The executor is still disabled.
* The older PR #5 gateway has different behavior and could run trusted tests without an OS sandbox; M1 does not invoke or merge it.

## Next gates

1. Review this candidate and the upstream stacked PRs; do not auto-merge.
2. Run actual Ollama on the ZBook, with a disposable repository, local-only data, manual review, and measured latency and memory.
3. Review the older dashboard's evidence format, then build a read-only adapter that can display M1 proposal JSON/diffs without uploading them.
4. Only after a separate Windows signer/account/ledger and Docker isolation review should a future executor be considered.

Run in CI or in a Linux/Python environment with `cryptography` installed:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -p 'test_*.py' -q
```
