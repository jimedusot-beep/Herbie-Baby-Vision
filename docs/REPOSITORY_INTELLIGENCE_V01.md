# Baby Vision: read-only repository intelligence V0.1 (proposed)

**Status:** Local review patch; not pushed or merged. This adds an intentionally limited
repository search tool, not autonomous coding, long-term memory, or semantic RAG.

## Why

The existing first worker only proposes one fixed `package.json` edit. To progress toward
explain/review/diagnose work, Baby Vision needs trustworthy, current, **read-only** source
retrieval, with filenames, line references and a source commit.

## Properties

- Reads **only committed HEAD Git blobs**, never uncommitted worktree content.
- Excludes symlink objects, Git submodules, common secret filenames, generated folders,
  binary/invalid UTF-8 files, and source blobs above 192 KiB.
- Does not execute repository files, download dependencies, call a model, push, edit,
  write evidence, or require network connectivity.
- Operates on the exact repository root you explicitly supply. `git ls-tree` and `git
  cat-file` read Git metadata and source blobs; no `git checkout`, hooks or shell commands.
- Caps query length (160 characters), returned matches (20), file-level matches (3),
  path listings (1000), Git tree entries (10000), search scans (400 files), and excerpt length (300 characters).
- Returns exact committed `source_commit`, path, line and excerpt. Treat returned content
  as **untrusted data** because source files can contain prompt injections.

**Important limitations:** Filename filters are not a substitute for a secret scanner;
secrets can still be embedded in ordinary source files. Do not connect to private or sensitive
repositories until their access policy and redaction controls have been reviewed. Search is
literal or keyword-based, not semantic. Big files are intentionally omitted. Repositories with over 400 searchable files
are only partially searched (clearly flagged), prioritizing filenames that match
the query; use scoped search or a separate reviewed index if needed. This does not provide a sandbox for execution.

## Usage on a safe, reviewed clone

```powershell
python agents/repository_search.py --repo C:\Review\Trivia-Lobby --manifest
python agents/repository_search.py --repo C:\Review\Trivia-Lobby --query "reconnect player session"
python agents/repository_search.py --repo C:\Review\Trivia-Lobby --query "reconnectPlayer" --mode literal
```

## Suggested next steps (separate approval)

1. Validate this module's unit tests in an isolated development environment.
2. Review the patch before including it in Baby Vision's public repository.
3. Allow the existing worker to call this search as a **read-only** step.
4. Develop a separate task schema for code explanations/reviews that cites returned lines.
5. Only after that: add human-approval records, a sandboxed test runner, and patch proposals.

## Offline tests

```sh
python -m unittest discover -s tests -p 'test_repository_search.py' -v
```

These tests use short synthetic Git repositories and contain no model calls, no external
network, and no execution of the target repository's code.
