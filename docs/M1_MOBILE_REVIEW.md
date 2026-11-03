# Baby Vision M1 — read-only mobile review UI

**Scope:** Draft branch stacked on checkout-hardening PR #20. Browser-only, no backend, no network connections, no model calls, no repository or GitHub changes, no approval authority.

## Why reuse instead of merge the old gateway

The older dashboard in PR #5 (`dashboard/review.js`) supports an older, tightly scoped `package.json` worker report. That branch also contains a different gateway worker path which can run trusted tests without an OS sandbox. **Do not merge that gateway into this review surface.** Reuse only its security principles: CSP, local-only file import, bounded JSON, `textContent` rendering, no persistence.

## What this dashboard actually understands

- **Investigation**: the JSON saved by `readonly_investigate.save_report()`, containing `source_commit`, `query`, `evidence` and `analysis`, with cited `path:line` entries.
- **Guided proposal metadata**: the JSON saved by `proposal_bridge.save()`, containing `source_commit`, `query`, `target`, `diff_sha256`, `citations`, `analysis` and `model`.
- **Optional proposed diff**: the corresponding `.diff` file. The browser compares its SHA-256 with the metadata before displaying. No executable change is ever applied. If browser cryptography is unavailable, the patch remains hidden.

The viewer may read any one report alone or both JSON reports plus a diff. When both reports are present, it requires matching Git revision, question and evidence references. **These are self-reported claims**; a colluding or malicious report generator can fabricate *all* of them and a matching SHA-256. Nothing is independently authenticated.

## Development / review

Open `dashboard/m1-review.html` with `dashboard/m1-review.js` next to it. A trusted local HTTPS server may be necessary on iOS because direct `file://` JavaScript behavior varies. No hosted URL has been deployed or verified. For a manual browser demo, choose the three files in `samples/`. They are explicitly **synthetic** and not evidence of a real Trivia Lobby diagnosis.

Run offline automated validation:

```bash
node --test tests/test_m1_mobile_review.cjs
```

File safety: max 3 files, 256 KiB per JSON, 12 KiB per patch; no downloads/import from external URLs, no cloud APIs, no analytics, no localStorage/cookies, no service workers or approvals. DOM content uses `textContent`, including diff and model text. Both the HTML and JavaScript are plain files without dependencies.

Do **not** upload real private logs or code to public GitHub Pages or commit them to the repository. A future review-only iPhone-hosted frontend may serve **public static assets**, while selecting evidence privately from Files, but hosting requires separate security review and deployment authorization.

## Acceptance status and next steps

- Node unit/UI fixture suite covers format acceptance, invented citations, malformed data, digest checks, refusal, XSS-like text injection, clear/reload races, and CSP contract.
- Mobile layout uses viewport-safe padding, min 44px controls, and single-column fields on narrow screens.
- **Not verified:** real iPhone Safari interaction, iCloud/Files behavior, VoiceOver, private HTTPS hosting, actual local Ollama inference, or authenticity of evidence.
- The M1 proposal chain must remain review-only. This UI cannot be used to issue, consume, or sign approvals.
