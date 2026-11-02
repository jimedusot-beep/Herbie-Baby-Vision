# Baby Vision V0.4.1 — Review-only safety fixes

**Scope:** correct three reproducible V0.4 defects, without implementing patch application or test execution.

## Changes

1. **Output path redirection:** `proposals/`, `logs/` and `approvals/` are now constrained to direct, non-redirected children of the configured hive root. On POSIX, the I/O uses directory file descriptors, `O_EXCL`, and `O_NOFOLLOW` (where supported) to reduce symlink/race risks. Existing symlinked files and hardlinked audit logs are refused. On Windows, reparse points/junctions are explicitly screened and output creation is exclusive, but an attacker running as the same account can still race a path-based check. This is a defense-in-depth safeguard, **not sandbox isolation**.
2. **Malformed AI citations:** require string `path` and strictly integer, positive `line` (`bool` is rejected). All malformed citation types result in a normal `InvestigationError`; source evidence is never executed.
3. **Packaging integrity:** regenerate the one canonical full SHA-256 manifest only after all other package files are finalized and ensure it verifies on the *extracted ZIP*. Old stale manifests are not shipped.
4. **Approval record creation:** use the same guarded writer, but the records are still editable and forgable by a process with the same filesystem privileges. No authenticated execution authority is claimed.

## Tests

Run from extracted package root:

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Tests are entirely offline/synthetic. They verify refusal to write through a symlinked output directory into a fake repository, blocked symlink and hardlink logs, rejection of malformed citations and preservation of regular outputs. Do not interpret these tests as Windows reparse-point or real Ollama acceptance tests.

## Unresolved launch blockers

- **Executor disabled:** there is no mechanism to prove that an approval JSON was created by the human rather than forged or altered by another process. A future executor must run with separate privileges, authenticate the user, pin patch hashes/commits, enforce one-use decisions and distinguish apply from test permission.
- **Windows race tests pending:** NTFS junction/reparse replacement, ACLs and concurrently modified directories need on-device testing and isolation. No user-writable directory alone is an execution-security boundary.
- **Search coverage:** a maximum of 400 searchable files per query, and proposal writing rejects source files above 8 KB. Partial scans must be shown as incomplete. Improve targeted retrieval later.
- **Local runtime pending:** ZBook Ollama speed/model quality and any Docker profile must be validated separately.
- **Artifact concurrency:** if one member of a two-file guided proposal fails to save, the other may remain orphaned. It cannot become an approved action without both valid files, but cleanup would improve robustness.

## Review rules

PR is stacked on draft PR #12; do not merge or deploy without separate review. Source and target repository are not modified by these scripts. Failures in filesystem controls must be treated as refusals, not bypassed to make progress.
