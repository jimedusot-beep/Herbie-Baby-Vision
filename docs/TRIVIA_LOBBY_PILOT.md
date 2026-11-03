# Trivia Lobby — Baby Vision's first real-source read-only pilot

**Status:** proposed integration acceptance check, stacked on Baby Vision draft PR #8. This is **not** an autonomous AI agent, a reported bug fix, a live Ollama test, or a ZBook installation.

## Scope

- Uses the existing `agents/repository_search.py` from PR #8.
- In GitHub Actions, checks out the **public** repository `jimedusot-beep/Trivia-Lobby` at pinned commit `1841025f8e5be153350e4cb44ad772a417448bab`.
- Builds a committed-source manifest, asserts that `server/room-checkpoints.ts` is indexed, searches for `room checkpoint`, validates returned filename/line/commit evidence, and checks that the project checkout remains clean.
- The workflow **does not** run application code, install npm dependencies, invoke a model, run generated commands, write to Trivia Lobby, or merge anything.

## Why this is a better first integration test

Trivia Lobby already has real recovery-related code and tests: `server/room-checkpoints.ts`, `tests/live-recovery.test.ts`, and `tests/party-recovery.test.ts`. They provide a meaningful target for finding evidence without inventing a bug. The pilot assesses **retrieval**, not whether a defect exists.

The repository currently includes **609 Git blobs** (observed 2026-11-02); the search implementation has a **400 eligible-file scan cap**. If `partial_scan` is true, Baby Vision must disclose that searches are not exhaustive. Filename ranking makes checkpoint-related code easier to find, but is not proof of comprehensive understanding.

## On-device follow-up after review

On the ZBook, create a disposable clone and run:

```powershell
python agents\coding_bee.py init
git clone https://github.com/jimedusot-beep/Trivia-Lobby.git work\trivia-lobby
git -C work\trivia-lobby switch -c bee/test
python agents\coding_bee.py inspect "room checkpoint"
```

These commands assume the separately supplied Coding Bee review ZIP is extracted to a new `C:\hive` folder. The controller in that ZIP is **not part of this PR** and must be reviewed independently before integration.

A separate future milestone will connect source evidence to Ollama for review-only patch proposals, then later implement distinct, audited authorizations for applying changes and running tests. **No such authorizations are implied by this test.**

## References

- Read-only search module: https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/8
- Source repository: https://github.com/jimedusot-beep/Trivia-Lobby
- Source focus: https://github.com/jimedusot-beep/Trivia-Lobby/blob/main/server/room-checkpoints.ts
- Recovery tests: https://github.com/jimedusot-beep/Trivia-Lobby/blob/main/tests/live-recovery.test.ts
