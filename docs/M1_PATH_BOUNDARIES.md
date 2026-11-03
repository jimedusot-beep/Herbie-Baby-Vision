# M1 safety review: physical disposable checkout

**Status:** stacked draft on consolidated M1 PR #19. No execution, merge, deployment or live Ollama test.

## Confirmed defect (reproduced before the fix)

The original `agents/readonly_investigate.py` computed the expected checkout path with `Path.resolve()` on the same `WORK` path it was about to validate. The original `agents/coding_bee.py` similarly resolved `hive/work` before checking its child. A symlinked `hive/work` parent therefore allowed **both** validators to accept a Git repository physically located outside the intended disposable work area, provided the Git root and `bee/*` branch matched. This is a meaningful precondition bypass even though M1 itself only prepares proposals.

Also, `coding_bee.safe_task()` resolved a task path **before** calling `is_symlink()`, making its symlink check ineffective for links whose resolved target remained in `tasks/`.

## Minimal review-only fix

- Common `artifact_io.verify_disposable_checkout()` checks `hive/`, `work/`, `trivia-lobby/` and `.git/` are physical, nonredirected directories, and verifies canonical path containment before reading committed Git data.
- Both Coding Bee and the read-only investigator call the same guard.
- Task-file and task-directory links are checked **before** resolving the task path.
- Six new regression tests cover a normal checkout and the disallowed link scenarios.
- No subprocess/AI/approval/execution authority was added.

## Verification

- Original test package on Linux: **143/143 passed**.
- Before fix, two actual Git checkout validators **both accepted** the same redirected repository.
- After fix: both refused the redirect; locally **149/149 tests passed** on a Linux container (Python 3.13). The hosted tests on GitHub are required for 3.9 and 3.12 before promoting anything.
- GitHub CI cannot establish Windows junction/OneDrive reparse security, hostile same-user filesystem races, or that `work/trivia-lobby` is genuinely disposable. Those require a later separate ZBook test.

## Review gates

1. Run full GitHub CI against the stacked patch.
2. Inspect the three source-module changes and six regression tests.
3. Keep this PR and PR #19 in Draft. Do not combine the unsandboxed gateway runner from PR #5.
4. Do not enable execution, use trusted approvals, merge, or deploy based solely on these tests.
