# Baby Vision V0.4.4 — single-use reservation **reference**, not an executor

**Status: review-only POSIX prototype. Windows reservation deliberately refuses to operate.** This increment adds a single-use SQLite reservation ledger to the V0.4.3 Ed25519-signed approval verifier. It **never** executes generated source, applies a patch, starts Docker, pushes, merges, or deploys.

## Design and evidence

- Existing `signed_approval.verify()` checks a signed human decision against a **separately pinned** Ed25519 public-key fingerprint, exact proposal and diff SHA-256, source commit, target, action, expiration, STOP/revocation and clean source checkout. The verifier now returns the verified nonce/hash bindings for use **inside** a trusted reservation component. This output is not a secret or a bearer token.
- New `approval_replay.reserve()` verifies the signature again, checks source and STOP again, and uses a SQLite `BEGIN IMMEDIATE` transaction with uniqueness constraints on **both** signed claim identity and `(proposal, action)`. Competing reservations of the same permission result in only one successful commit.
- The ledger must be an existing `.sqlite3` file inside an owner-only POSIX directory **outside** the bee workspace. Provisioning is separate and refuses overwrites. It rejects symlink and hardlink substitution and non-owner-only permissions; reservation never silently creates an absent DB. It uses a full-sync rollback journal and `trusted_schema=OFF`.
- Reservation is a write of decision state, **not** a change to a project or an authorization to perform work. No replay result may be passed in from the worker as proof; a future isolated runner must verify and reserve internally before any possible action.

## Crucial security limitations

**A private signing key outside the hive is not automatically safe.** If the worker, signer, ledger owner, and future executor share a Windows or POSIX account, a compromised worker may steal the key, modify ledger state, or impersonate the approver. A same-user local Python process is **not** a trust boundary. This demo verifies mode bits and UID but cannot independently prove that the bee runs under a distinct identity. SQLite protects against honest concurrent callers, **not** a hostile process with write access to the DB or its directory. The public-key fingerprint supplied by the caller is not trusted just because it is a command-line argument; a future service must enroll it out of band in a protected configuration.

### Windows installation acceptance gates (not yet implemented)

1. Dedicated, least-privileged Windows bee account with **no** access to signing key, trusted configuration, or replay database. Separately protected approver process that displays the exact diff and requires a trusted confirmation path.
2. Windows CNG/Hello/hardware-bound or otherwise OS-isolated signer: do not export a raw private key into model-readable files, the hive, environment variables, or logs. Establish key enrollment, rotation and owner recovery.
3. Windows service under a distinct identity owns public-key pin, private replay ledger and action runner; the bee can request a review but cannot read or reset the service's ledger. Explicit ACL, junction/reparse and process-integrity testing **on the real Windows machine** is required.
4. The service must atomically reserve a signature and check STOP, repository path, exact source commit and proposed diff **within its own boundary**; on a crash after reservation, fail closed (no automatic retry). Unsuccessful operations also consume approvals unless a new proposal is reviewed and signed.
5. Docker isolation, mount permissions, network restrictions, command allowlist, CPU/memory limits, logs, and manual STOP must be separately validated before enabling execution. **Do not enable an executor from this PR.**

## POSIX demonstration (not for authorization)

Install cryptography (`python -m pip install 'cryptography>=43,<47'`) and use a disposable synthetic repo as in `docs/SIGNED_APPROVALS_V043.md`.

```bash
mkdir -m 700 "$HOME/baby-vision-trusted-ledger"
python agents/approval_replay.py provision --ledger "$HOME/baby-vision-trusted-ledger/used.sqlite3"
# Sign a proposal in a separate trusted terminal as documented in V0.4.3.
python agents/approval_replay.py reserve guided-EXAMPLE \
  --action apply_disposable_patch \
  --ledger "$HOME/baby-vision-trusted-ledger/used.sqlite3" \
  --public-key "$HOME/baby-vision-signer/public.key" \
  --trusted-fingerprint PINNED_SHA256_FROM_TRUSTED_SETUP
# A second identical reservation is REFUSED, without running anything.
```

`provision` and `reserve` CLI deliberately require a local interactive terminal. The Python functions may be called in test fixtures but are **not** suitable as an authorization endpoint. Windows CLI refuses reservation irrespective of confirmation.

## Tests

`PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -p 'test_*.py' -q`

20 new tests include 8-way concurrent replay attempts, separate actions, durability, STOP, wrong fingerprint, legacy unsigned approvals, tampering, unsafe parent modes, symlinks/hardlinks, corrupted DB, unknown schema, and Windows fail closed. No real ZBook, Windows CNG, live Ollama, Docker or actual patch application was tested.

References: [SQLite transaction isolation](https://www.sqlite.org/isolation.html), [SQLite URI filenames](https://www.sqlite.org/uri.html), [Windows data protection concepts](https://learn.microsoft.com/en-us/windows/win32/seccng/cng-portal), [Ed25519 RFC 8032](https://www.rfc-editor.org/rfc/rfc8032).
