# Baby Vision V0.3 — Source-cited review-only diff proposals

**Status:** review-only implementation. This step adds `agents/proposal_bridge.py` and synthetic tests, stacked on draft PR #10.

## What this milestone does

1. Requires a clean standalone public/sanitized Trivia Lobby checkout on a `bee/*` branch.
2. Runs the committed-only code search and V0.2 read-only Ollama investigation, requiring real validated citations and medium/high *model-reported* confidence.
3. Selects exactly one cited regular committed source file under 8,000 bytes; refuses files matching common credential indicators.
4. Sends that file and the untrusted investigation to **local loopback Ollama** for a minimal unified patch, or `CANNOT_PROPOSE`.
5. Checks that the patch modifies only that cited file. Rejects patch metadata, renames, binary changes, added/deleted files, oversized edits, stale checkouts and invalid line counts. `git apply --check` is a **read-only check**, not patch application.
6. Saves a `.diff` and `.json` evidence sidecar outside the target repository. No patch is applied, no generated code is run, and no commit/push/merge/deploy occurs.

## When the ZBook is available

Extract the V0.3 ZIP into `C:\hive`, and prepare a separate clean public Trivia Lobby clone in `C:\hive\work\trivia-lobby` on `bee/test` (see earlier V0.2 instructions). Ollama must already be running locally with the small model installed.

```powershell
cd C:\hive
python agents\proposal_bridge.py "recovery checkpoint" --ask --model qwen2.5-coder:1.5b
```

`--ask` is an **explicit local inference request**: it may invoke Ollama twice, once for investigation and once for a proposed diff. It is **not** permission to apply changes or test project code. The saved proposal is advisory and unverified.

## Offline regression checks

```sh
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Synthetic tests substitute both Ollama calls and operate on tiny temporary Git repositories. A passing CI check does **not** demonstrate that a real coding model can locate or fix a bug.

## Limits and next gates

- `confidence` comes from the model, not an independent verifier; human code review is still required.
- The repository search currently scans at most 400 eligible files, so `partial_scan` may be true. Results may omit relevant code.
- Credential detection is heuristic, **not** a comprehensive secret scanner. Do not inspect private or sensitive repos yet.
- STOP is checked between phases but cannot interrupt a model call already blocking on network I/O instantly.
- Do not treat a `bee/*` branch alone as proof a repository is disposable. This module never modifies it.
- No Docker test executor or patch application is implemented; build separate server-enforced permission gates and a container sandbox later.
- No OpenCode or Cline implementation is included here. This is a small integration using the already-tested Baby Vision components.
