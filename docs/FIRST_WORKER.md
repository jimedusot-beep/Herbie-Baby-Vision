# First bounded local-model worker

Baby Vision can now run one specific coding task: add a missing `npm test`
entry point that delegates to an existing `test:unit` script. The real local
model proposes a JSON edit; coordinator code validates it and runs the tests
in a disposable Git checkout. It produces a private review packet and never
merges, deploys or writes to the source checkout.

Requirements: Python 3.11+, Git, Node/npm and a running local Ollama model.
No OpenHands, CrewAI or multi-agent dashboard is installed by this worker.

```sh
python agents/first_task.py \
  --repo /absolute/path/to/Herbie \
  --model qwen2.5-coder:1.5b \
  --output /private/path/first-task-evidence.json
```

The source repository must have committed `package.json` and test files. The
worker operates at the committed `HEAD` (or `--base`), preserving uncommitted
work in the source checkout. It refuses existing test entry points, unsupported
test commands and lifecycle hooks that would change the task's scope.

The coordinator first records the failing `npm test`, obtains the model's
proposal, changes only the allowed script field, checks the diff, and executes
`npm test` again. A failing test blocks review-ready status. The packet includes
the exact proposal, source commit, diff, command, exit codes and output.

Review packets can contain private source code and must not be committed to
this public repository. Keep a private Herbie task record and open its PR
through an authenticated human/coordinator workflow. The worker itself needs
no GitHub credentials and is never allowed to merge.

This is a narrowly bounded worker for a trusted repository, not a general
coding-agent sandbox. Its test commands execute trusted project code on the
host; a disposable checkout is not operating-system isolation. No arbitrary
model-generated shell command is executed.

Run tests:

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```
