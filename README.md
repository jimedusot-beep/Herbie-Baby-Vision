# H.E.R.B.I.E. Baby Vision

Baby Vision is an **AI development assistant for H.E.R.B.I.E.**, not the robot runtime. It will coordinate research, code proposals, tests and human review without controlling physical hardware.

**Current status: first bounded local-model worker.** The
[first-task coordinator](docs/FIRST_WORKER.md) asks a local model for one scoped
code proposal, tests it in a disposable checkout and produces private evidence
for human review. An operational dashboard, general coding agent and broader
orchestration remain pending.

## Project links

- [H.E.R.B.I.E. robot software](https://github.com/jimedusot-beep/Herbie)
- [H.E.R.B.I.E. hardware engineering](https://github.com/jimedusot-beep/Herbie-cyborg-hardware)
- [Robot-side integration proposal PR #66](https://github.com/jimedusot-beep/Herbie/pull/66)

## Roadmap

1. Check HP ZBook CPU, RAM, GPU, operating system and free storage.
2. Evaluate OpenHands or OpenCode using an isolated disposable checkout.
3. Connect a suitable local model through Ollama if hardware permits.
4. Run one narrowly scoped H.E.R.B.I.E. coding task, collect tests and diff.
5. Require human approval before any merge or deployment.

See [integration plan](docs/INTEGRATION_PLAN.md) and [safety policy](docs/SAFETY.md).
