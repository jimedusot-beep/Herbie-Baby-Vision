# Worker Bee #1 — opt-in authenticated H.E.R.B.I.E. inference (V0.3)

**Review-only development.** Adds `agents/gateway_first_task.py`, an opt-in alternate inference transport for the existing `agents/first_task.py` approved `package.json` task. This is **not** a general coding agent.

## Existing first-worker contract — unchanged

The coordinator can only add an `npm test` alias to a trusted repository that already has the exact `test:unit` command `node --test tests/*.test.cjs`. It verifies eligibility at the committed revision, runs the existing trusted test suite before and after, edits **only** the `package.json` script, checks the diff, and emits a private review packet. It does **not** accept arbitrary model-supplied shell commands or automatic merges. A temporary Git worktree is **not** an operating-system sandbox; never run untrusted repository test scripts on the host.

## Optional gateway flow

1. Start **only** a reviewed H.E.R.B.I.E. gateway in localhost mode, separately and explicitly. H.E.R.B.I.E. #93 now contains the opt-in gateway module staged from #86; neither branch is deployed.
2. Ensure a reviewed model is already installed and available to local Ollama. The worker does not install or download models.
3. Configure a long bearer token in a local environment variable `HERBIE_WORKER_TOKEN`. Do not put credentials in CLI arguments, chat, or public GitHub.
4. Execute `agents/gateway_first_task.py` against a **trusted disposable fixture or approved source checkout**, with `--repo`, `--model`, `--gateway-url http://127.0.0.1:8787`, and `--output` pointing to a private path outside the repository.
5. The adapter sends one fixed, scoped **coding** request to the gateway and accepts **only** a strict JSON proposal with `script` and `reason`. Blank results, extra fields, malformed JSON, forbidden commands and gateway failures block the task. It never auto-retries.
6. The existing coordinator validates the returned data independently, runs its fixed tests in the disposable checkout and produces private evidence. It cannot merge.
7. Open that JSON in the offline review dashboard at [dashboard/index.html](../dashboard/index.html) on this same unified review branch. That dashboard *only* displays claimed evidence; it does not independently verify tests or approve a GitHub PR.

For this V0.3 adapter, **remote Tailscale/LAN endpoints are refused even though the lower-level gateway client can represent some HTTPS Tailscale addresses**. Real two-PC networking requires a separate reviewed milestone.

### Test tiers (do not conflate)

| Gate | Evidence |
|---|---|
| Unit validation of gateway client and fixed proposal | CI / Python test modules |
| Fake authenticated gateway → actual scoped worker → real Git and Node fixture | `tests/test_gateway_first_task.py`; does not call an LLM |
| Actual installed ZBook Ollama → reviewed gateway → Baby Vision client | Explicit local opt-in smoke harness; **not performed in this chat** |
| Real Ollama coding task yielding compliant JSON and passing tests | **Unverified**; small models may not honor strict JSON instruction |
| Physical iPhone/browser dashboard and voice loop | **Unverified** |
| Untrusted-repo OS sandbox | **Not implemented** |

The AI can propose data only. A tested diff is not proof that the robot's hardware, clinical behavior, security or project logic is safe.

## Why selective reuse instead of installing OpenHands/OpenCode now?

[OpenHands](https://github.com/OpenHands/OpenHands) demonstrates a separate agent server, workspace and dashboard, but explicitly warns that unsandboxed execution can reach the host filesystem. [OpenCode](https://opencode.ai/v2/docs/models) supports direct local Ollama discovery and model configuration; that does not guarantee a model can use tools or that we have enough RAM/VRAM on this ZBook. [Stack-Chan Minimal](https://www.hackster.io/UtaAoya/stack-chan-minimal-tiny-body-local-ai-soul-23cba5) separates face/body from the local AI service, a good **future physical Bee** boundary. We reused the *architectural principles*, not upstream code, binaries or UI assets.

## Acceptance criteria before any merge

- [ ] Real CI completed on exact Baby Vision PR #5 head and runner steps examined.
- [ ] H.E.R.B.I.E. gateway negative and local model tests executed on exact #93 combined head.
- [ ] Real authenticated ZBook Ollama smoke completed without remote exposure.
- [ ] One real model-generated, allowed JSON proposal produces a tested diff and private report.
- [ ] Owner reviews the diff, resource use and privacy boundary.
- [ ] Separate approval for production merge and local integration.

See also [H.E.R.B.I.E. issue #94](https://github.com/jimedusot-beep/Herbie/issues/94) and [Baby Vision issue #6](https://github.com/jimedusot-beep/Herbie-Baby-Vision/issues/6).
