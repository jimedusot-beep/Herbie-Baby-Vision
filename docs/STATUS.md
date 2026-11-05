# Baby Vision project status and evidence

**Last verified: November 4, 2026.** This is the maintained status entry point. Older design documents describe their original branches and should not be used alone to determine merge state.

| Track | Default-branch contents | Evidence / limits |
| --- | --- | --- |
| First-task worker | Bounded package-script proposal coordinator | Can execute trusted tests on the host; no OS sandbox or automatic merge |
| Source investigation and proposal | Repository search, read-only investigation, patch validation and M1 synthetic acceptance | Model stubs are not real Ollama inference or evidence of diagnosis quality |
| Mobile review | Static `dashboard/m1-review.html` and companion JavaScript | Reads local report files; no approval authority, patch execution, verified deployment or real iPhone acceptance |
| Approval references | Signed-approval and replay-ledger prototypes | Not an operational trusted executor; Windows isolation/acceptance not established |
| Gateway / older dashboard | [PR #5](https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/5) remains open, unmerged | Different worker/report path; do not conflate it with M1's review-only surface |
| STOP hardening | [PR #24](https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/24) remains open, unmerged | Symlink-related hardening remains a review gate |

## Checked baseline

At main `8d2ac1821870e5443189e12397d62ae65d704eb0`, 151 Python tests and 14 M1 review Node tests passed during the portfolio review. These are selected offline suites, not every configured CI/browser workflow. No real Ollama/ZBook task, physical iPhone/VoiceOver, Windows isolation, deployment, robot action or live gateway acceptance was performed.

Main changes require fresh exact-revision checks; this dated baseline does not certify a later commit. See [M1 acceptance](M1_ACCEPTANCE.md) and [mobile review evidence](M1_MOBILE_REVIEW.md) for fixture scope.

## Next gates

1. Review STOP hardening and run the relevant exact-head checks.
2. Provision the intended local host/model and demonstrate a bounded real-model task, with private evidence.
3. Review gateway integration separately from the static M1 viewer.
4. Record real phone accessibility and local-host acceptance before claiming those capabilities.
5. Keep human approval separate from proposal generation; never treat imported evidence or a matching digest as independent authorization.
