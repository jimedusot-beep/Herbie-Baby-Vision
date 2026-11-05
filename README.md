# H.E.R.B.I.E. Baby Vision

Baby Vision is an **AI development assistant for H.E.R.B.I.E.**, not the robot runtime. It investigates source and prepares bounded proposals for human review without controlling physical hardware.

**Start with [Project status and evidence](docs/STATUS.md).** That page owns the current main-versus-draft status, validation limits and next gates. Individual design documents may retain historical branch descriptions.

## Cold start: offline checks

Requires Python 3.11+, Git and Node 22+. From a checkout:

```sh
git clone https://github.com/jimedusot-beep/Herbie-Baby-Vision.git
cd Herbie-Baby-Vision
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_m1_mobile_review.cjs
```

These checks use synthetic fixtures and do not require Ollama, a microphone or robot. They do not establish model quality or hardware acceptance.

## Choose a workflow

- [First-task coordinator](docs/FIRST_WORKER.md): optional local Ollama proposal plus trusted project tests in a disposable checkout. This executes trusted tests on the host; the checkout is not an OS sandbox.
- [Source search](docs/REPOSITORY_INTELLIGENCE_V01.md) and [read-only investigation](docs/READ_ONLY_INVESTIGATION_V02.md): find committed source and inspect cited evidence.
- [M1 proposal acceptance and limits](docs/M1_ACCEPTANCE.md): synthetic end-to-end proposal checks; no patch execution or automatic merge.
- [Read-only mobile review](docs/M1_MOBILE_REVIEW.md): open `dashboard/m1-review.html` with its companion JavaScript and use the synthetic samples in `samples/`. No hosted endpoint or real iPhone acceptance is claimed.
- [Signed approval reference](docs/SIGNED_APPROVALS_V043.md) and [replay ledger reference](docs/REPLAY_LEDGER_V044.md): separate review prototypes, not permission to execute code.

## Related repos

- [Herbie — private robot software and engineering hub](https://github.com/jimedusot-beep/Herbie/blob/main/docs/ENGINEERING_PROJECT_MAP.md); access is restricted.
- [Herbie-cyborg-hardware — electronics engineering](https://github.com/jimedusot-beep/Herbie-cyborg-hardware).
- [3D-vision — CAD and assembly workshop](https://github.com/jimedusot-beep/3D-vision).

See [integration plan](docs/INTEGRATION_PLAN.md) and [safety policy](docs/SAFETY.md). Keep private source, captures and review packets outside this public repository.

## License and third-party content

Original project software and its accompanying software documentation are licensed under **MIT**; see [LICENSE](LICENSE). Copyright 2026 jimedusot-beep. This notice covers only material the project authors have authority to license. Existing file-specific notices, third-party terms and prior license grants remain in effect.

Imported source, model weights, generated proposals containing third-party material, and review packets are not relicensed by this notice. Keep source-specific notices with any reused material.

CAD files, models, datasets, images, audio, fonts and other non-software assets are not granted a new license by this software notice. Use their existing asset-specific terms. Where provenance or permission is unresolved, this notice does not supply redistribution permission; record the source, author, exact license and modifications before redistributing that material.
