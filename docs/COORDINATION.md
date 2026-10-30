# Supervised cross-repository validation

Baby Vision owns development coordination, not the conversational runtime,
course content, educational truth or personal memory. Herbie owns offline
knowledge and Study Mode; 3D-vision owns anatomy/model presentation;
Herbie-cyborg-hardware owns engineering interfaces and documentation.

## Run a reviewed check

Requirements: Python 3.12+, Git, Node for JS profiles, Linux/macOS. Windows host
execution is blocked until process-tree termination is implemented; use an
isolated Linux VM on the ZBook. The existing first-task worker remains separate.

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
python agents/validate_repositories.py --repository hardware /path/to/Herbie-cyborg-hardware --trusted
python agents/validate_repositories.py --repository herbie /path/to/Herbie --revision REVIEWED_COMMIT_SHA --trusted
```

`--trusted` means a human reviewed the exact committed revision and its tests
for host execution. Profiles select fixed commands, never model-supplied shell
strings. Prefer exact commit SHAs; HEAD is resolved once per repository. Multiple
`--repository PROFILE PATH` pairs produce one JSON report. For different proposed
revisions run separately and retain both source_commit values. No checkout,
fetch, reset, commit, branch update, credential request or network download is
performed by the coordinator. A read failure produces blocked, not a pass.

Committed snapshots exclude untracked/ignored personal files and have no .git
metadata or shared worktree administration. Links and special files are rejected.
Credentials/user configuration are removed from the child environment. Raw
stdout/stderr is discarded with temporary files. Only fixed reason codes,
profile names, commit SHAs and exit codes enter the report. Keep even these
reports private when repository metadata is sensitive. Never put private course
material, source snippets, chat histories or model responses in public issues,
CI artifacts or logs. Ignore patterns reduce accidents, not access control.

A snapshot is **not an OS security boundary**. Reviewed tests can still access
the host filesystem, devices and network. A hostile test can evade a process
group or fill temporary storage. Use an external disposable container/VM with
read-only inputs, no host mounts/secrets/devices, disabled network, resource
limits and whole-container timeout for untrusted proposals. This environment
has not been provisioned by this change. Do not claim offline verification
from environment filtering or ordinary unit tests.

Dependencies are never installed automatically. Node profiles with declared
runtime dependencies block before execution (`dependencies_not_provisioned`).
Provisioning a pinned, reviewed dependency bundle in an external sandbox is
follow-up work. Missing dev-only test dependencies may still cause a failed
suite; completed means only that the selected process returned zero.

## Validation contracts and ownership

| Owner | Repeatable gate | Evidence needed before capability completion |
| --- | --- | --- |
| Herbie | Unit profile plus synthetic knowledge adapter cases | Network-disabled run, known fixture facts, resolvable source IDs, relevant retrieval, insufficient-evidence refusal, Study Mode answer/hint boundaries, deletion and STOP regressions |
| 3D-vision | Unit profile; dependency provisioning currently blocked | Pinned geometry dependencies, model IDs/units/axes, missing-model handling, anatomy-label source IDs, offline asset/browser checks |
| Cyborg Hardware | Python unit profile | BOM/manifest consistency, source references, units/limits, incompatible protocol rejection and simulation-only status; no live actuation |
| Baby Vision | Coordinator + contract regression suite | Snapshot preservation, trust refusal, permissions failures, timeout/cleanup/retry, no raw report content |

`agents/check_contract.py` is a **proposed synthetic adapter contract**, not an
existing Herbie/3D API. Fixtures declare version 1, fact IDs, citation IDs,
retrieved IDs and instrumented network-attempt count. The checker rejects
unknown sources, wrong expected facts, irrelevant retrieval and network use.
Its tests prove the validator, not actual model accuracy. Callers must supply
trusted network instrumentation and public synthetic fixtures. Free-form
scientific/medical correctness requires qualified source review. Real adapters,
browser tests and citation-to-anatomy mappings remain unverified.

## Conflict and dependency review

For each proposed change record repository + base SHA + head SHA, owner,
required upstream PRs and interface versions in a private task record. Compare
changed paths locally; path overlap is a review signal, not proof of conflict.
Check actual mergeability in a disposable sandbox, never by merging into main.
Rerun consumers against the proposed producer revision, not mismatched main
snapshots. Reject renamed/missing IDs, changed units, unsupported protocol
versions and stale retrieval indexes. General cross-repository merge/conflict
automation is not implemented here.

## Report states and release authority

- completed: selected unit process exited zero; no broader guarantee.
- failed: selected process ran and exited nonzero.
- blocked: prerequisite, trust, platform, snapshot or timeout failure.
- unverified: capability-specific acceptance has not run.

Each capability stays unverified until its own integration evidence exists.
CI success never grants release authority: merge_allowed and deploy_allowed
remain false. A human must explicitly approve any merge, deployment or
production configuration change. Draft PR creation is a separate authenticated
coordinator action; these workers have no GitHub write credentials.

## Existing worker audit

`first_task.py` already validates a two-field model proposal, restricts the npm
alias edit, rejects lifecycle hooks, bounds model responses and requires a
loopback nonredirecting endpoint. Its seven existing tests passed. It still uses
shared Git worktree metadata, host tests, inherited child environment and private
packets containing raw output/diffs. It is not replaced or certified for hostile
code by this coordinator. Keep its packets private; migrate it to external
sandbox execution before expanding task scope. Real Ollama inference was not
run in this audit; its HTTP integration test uses a loopback fixture.
