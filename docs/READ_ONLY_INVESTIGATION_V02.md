# Baby Vision V0.2: Evidence-to-Ollama Investigation

**Status:** proposed review-only integration; no physical ZBook or live Ollama acceptance yet.

This is a narrowly scoped coding investigator, not an autonomous code editor. It combines the committed Git search from draft PR #8 and the real Trivia Lobby checkout pilot from draft PR #9 with a local-only model request. No OpenCode/Cline source code has been incorporated.

## Setup on Windows ZBook

Use a second, disposable clone, never your normal development checkout:

```powershell
cd C:\hive
git clone https://github.com/jimedusot-beep/Trivia-Lobby.git work\trivia-lobby
git -C work\trivia-lobby switch -c bee/test
python agents\readonly_investigate.py "room checkpoint recovery"
```

Run the next command only after reviewing the retrieved evidence and confirming Ollama is running locally:

```powershell
ollama pull qwen2.5-coder:1.5b
python agents\readonly_investigate.py "room checkpoint recovery" --ask --model qwen2.5-coder:1.5b
```

The first command performs committed-file search only. The explicit `--ask` option sends up to 12 screened source excerpts to the local Ollama HTTP endpoint at `127.0.0.1:11434`. The model must return a JSON explanation, hypothesis, suggested change and citations that exactly match search results. If its JSON or citations are invalid, the tool refuses. Successful advisory reports go to `proposals/`; audit metadata goes to `logs/`. Never commit those local artifacts.

## Test

```sh
python -B -m unittest discover -s tests -p 'test_readonly_investigate.py' -v
```

The 10 unit tests create synthetic temporary Git repos and stub model responses. They do not run project code, invoke Ollama, apply patches, start Docker, push changes or connect to hardware.

## Important limitations

- This script returns *investigation advice*, NOT a unified diff or a verified fix. The separate reviewed Coding Bee ZIP can produce diff proposals with explicitly named files; consolidation is future work.
- Search scans at most 400 eligible files per query; the public Trivia Lobby repository has more than 400. `partial_scan` must be shown and results are not exhaustive.
- Secret-looking lines and files are rejected by heuristic filtering, not complete secret scanning. Use only public, previously reviewed source for now.
- Valid citations demonstrate that a location appeared in the search evidence; they do not prove that the model's interpretation is correct.
- `STOP` blocks new steps but does not forcibly terminate an in-flight model response.
- This is not an OS sandbox for Git read operations. Do not point it at untrusted repositories.
- It can never apply a patch, execute generated code, run tests in the target project, push, merge or deploy. Those operations require separate explicit approval workflows later.

## Review order

Review PR #8, then PR #9, then this V0.2 draft PR; none are auto-merged.
