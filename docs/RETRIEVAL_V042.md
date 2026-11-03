# Baby Vision V0.4.2 — Bounded, broader code retrieval

**Review-only:** These modules read committed Git objects, ask local Ollama (only when explicitly invoked), and produce untested proposed diffs. Nothing applies a patch, runs application code, merges, or deploys.

## Improvements
- Searches up to **2,000 eligible files**, capped at **24 MiB** total committed text and **192 KiB per file**.
- Uses one `git cat-file --batch` process per query instead of opening one Git process per file. Each blob's object ID, type, and size are verified before use.
- Exposes `partial_scan`, `omitted_due_to_budget`, and `bytes_scanned`; binary, invalid UTF-8, oversized and excluded files are not reported as searched.
- The investigator screens the **entire** selected file up to 192 KiB before returning a few bounded evidence excerpts, preventing secrets matching its heuristic regex from appearing elsewhere in the same file.
- For proposals targeting source files above 8 KB, selects up to three **cited** windows (12 lines before and after each) bounded to **8 KB total** of model source. Invalid citations, oversize windows, and sensitive content are rejected. A partial view is not complete understanding; the model must be prepared to decline.

## Tests and measured synthetic benchmark
The combined review ZIP contains 86 passing offline tests. This GitHub branch adds a focused regression subset plus a pinned public Trivia Lobby smoke test. On one Linux test container, the median of five warm searches on the same synthetic 610-small-file repository was **748 ms** previously (400 files, incomplete) versus **49 ms** after this change (610 files, complete). Those are not Windows, ZBook, GPU, or model benchmarks.

Pinned Trivia Lobby source SHA: `1841025f8e5be153350e4cb44ad772a417448bab`. Its Git tree has 609 tracked blobs; the earlier pilot indexed 547 searchable text blobs. The V0.4.2 GitHub check verifies at least 500 eligible files are scanned with no budget omission and leaves the checkout clean.

## Unresolved launch blockers
- **No authenticated approval execution**: V0.4 records remain editable/forgable by the same account, so the patch executor must remain disabled.
- Windows reparse/junction attacks and real Ollama performance still require testing on the ZBook.
- The file-filter/sensitive-word heuristic is **not a secret scanner**; use vetted, authorized repos only.
- Keyword/literal search is not semantic. `partial_scan=false` only means budgets did not exclude eligible entries. It does not assert that excluded/binary files or unrecognized secrets were inspected.
- Source windows can omit important context and models can suggest faulty changes. `git apply --check` verifies syntax/applicability, not correctness.

This is stacked on draft PR #13; do not merge or deploy automatically.
