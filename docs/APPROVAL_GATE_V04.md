# Baby Vision V0.4 — Separate human decisions (REVIEW ONLY)

This is the next layer after the V0.3 guided proposal bridge. It **records** an explicit human decision for one exact generated proposal and action. It does **not** apply a patch, run Docker, execute tests or commands, commit, push, deploy or merge.

## What can be approved

| Action | Meaning | Current implementation |
|---|---|---|
| `apply_disposable_patch` | Human authorizes a future runner to apply exactly this patch to a **disposable clone** | Decision record **only**; no patch runner |
| `run_isolated_tests` | Human authorizes a future runner to run project tests **in a locked-down container** | Separate decision record **only**; no Docker runner |

An `apply_disposable_patch` decision **never** implies test execution authorization. A test decision does not imply patch application or mean that an applied copy exists. No action runs in V0.4, even if both decisions exist.

## Use on a future ZBook session

Extract the combined review ZIP in `C:\hive` and prepare the approved disposable `work\trivia-lobby` clone on branch `bee/test`. Make a guided proposal with the V0.3 tool (real Ollama test is pending):

```powershell
cd C:\hive
python agents\proposal_bridge.py "room checkpoint recovery" --ask --model qwen2.5-coder:1.5b
python agents\approval_gate.py review guided-YYYYMMDDTHHMMSSZ-abc123abc123
python agents\approval_gate.py approve guided-YYYYMMDDTHHMMSSZ-abc123abc123 --action apply_disposable_patch
python agents\approval_gate.py status guided-YYYYMMDDTHHMMSSZ-abc123abc123 --action apply_disposable_patch
```

Use the **actual** saved proposal basename shown by the tool, not the example. The `approve` command prints the full diff and asks the person at the computer to type an exact action-specific confirmation phrase. Noninteractive input is rejected. To separately record test consent:

```powershell
python agents\approval_gate.py approve guided-YYYYMMDDTHHMMSSZ-abc123abc123 --action run_isolated_tests
```

No `--yes`, auto-approval or remote HTTP approval API is provided. The decision expires after **one hour**; repeating or reusing the same decision is refused. A future runner may call the internal `consume` function to mark permission used, but no runner exists in this version. Each action must be consumed separately. The `STOP` file disables issuance and verification. `reject` and `revoke` create permanent markers for that proposal; create a new proposal to proceed.

## Security properties and limitations

- Both report and diff are restricted to small regular files directly inside `hive/proposals`. Symlinks and path traversal are refused.
- The approval record pins the **whole report SHA-256**, **whole patch SHA-256**, source commit and target path. Review requires `git apply --check` only on a clean, standalone `bee/*` checkout. Any change to the committed source, uncommitted files, patch or report makes verification fail.
- New decisions use exclusive file creation. A consumed authorization cannot be reused. Local approval files are created mode `0600` where supported, but Windows ACLs and filesystem access still need separate setup.
- **This is local user-intent recording, not cryptographic proof of who approved it.** A process with the same OS user's file access could forge or alter local decision records. A later real executor must live outside the model's write authority, authenticate the operator and enforce authorization in a separate process/security domain. Do not grant an AI agent write access to `hive/approvals`.
- This version cannot prove that `bee/*` is truly disposable and it does not install or run containers. Before an execution runner is added, confirm the clone origin, immutable source snapshot, container mount permissions, network isolation, no inherited credentials, resource budgets and abort behavior.
- An `approve run_isolated_tests` decision alone **does not** establish that any patch has been applied. A future runner must check completed patch stage, exact applied tree and test command separately. If a patch makes the checkout dirty, the existing pre-application clean-check logic will need a separate post-application state verifier.
- Filenames/contents in code can still include secrets not detected by heuristic screening; use only vetted public or sanitized samples.
- All tests here use a tiny synthetic Git checkout; no ZBook, live Ollama, real vulnerability fix, real Docker run or physical devices tested.

## Tests

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
```

See the separate GitHub draft PR and its CI checks before considering a merge. Recommended next milestone: build an **independent, sandboxed executor** that uses these records only after explicit approval, with separate create/apply/test and rollback checks. Do not merge any draft PR automatically.
