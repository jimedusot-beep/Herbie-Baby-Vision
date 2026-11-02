# Baby Vision V0.4.3 — Signed approval architecture (review only)

**Status:** Experimental Ed25519 signature layer. All execution remains disabled. The new `agents/signed_approval.py` is **not** an executor, not a credential vault, and not proof that the keyboard operator is the repo owner. It requires the free `cryptography` Python dependency. The earlier `approval_gate.py` produces **unsigned, untrusted local decisions** and is retained only for backwards-compatible review and tests. A future executor MUST NOT accept those legacy JSON records.

## What is verified

Every signed record is bound to: **one action** (`apply_disposable_patch` or `run_isolated_tests`), one proposal ID, one exact report SHA-256, one exact proposed diff SHA-256, one pinned Git HEAD commit, one target file, one nonce, a signing-public-key fingerprint, and a 15-minute lifetime. The signature covers a domain-separated canonical JSON payload. Verification uses **only an explicitly supplied public key AND a pinned trusted SHA-256 fingerprint**; a public key placed alongside a proposal is not automatically trusted. Unknown fields, malformed types, wrong actions, altered signatures, missing trust anchors, stopped/revoked proposals, expired/future timestamps, dirty checkouts and modified proposals are refused.

An approval **does not** apply changes or run tests. No application code, build commands, Docker, commits, pushes, merges, or deployments are performed by the signed-approval module.

## Important trust boundary

Signatures prevent a worker from *editing a record into a new valid approval* **only if the worker cannot access the private signing key**. File permissions are not enough if the worker and the human signing process run under the **same OS account**. A stolen key, compromised signer, swapped output on an untrusted account, or an attacker controlling the runner bypasses the intended control. **Do not connect this to a privileged executor yet.** A protected out-of-process signer (or dedicated signing account / OS-backed key storage), isolated runner, trusted public-key pin and durable atomic one-use reservation must exist first.

`sign` is deliberately **disabled on Windows** until a real, separate Windows protected signer is built and validated. Windows can verify an already signed record through a trusted public key. Windows path/junction defenses still require physical Windows testing. Do not bypass the platform refusal.

## Developer-only POSIX demonstration

Use a **synthetic disposable repository** and a separate protected signing identity for a serious deployment. For demonstration only, generate an Ed25519 keypair **outside** the hive directory, in an owner-only directory. Do not commit or copy the private key into the repository, ZIP, model prompt, or agent process.

```bash
python -m pip install 'cryptography>=43,<47'
umask 077
mkdir -p "$HOME/baby-vision-signer"
chmod 700 "$HOME/baby-vision-signer"
python - <<'PY'
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pathlib import Path
root = Path.home() / 'baby-vision-signer'
key = Ed25519PrivateKey.generate()
private = root / 'private.key'
with private.open('xb') as f:
    f.write(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
private.chmod(0o600)
with (root / 'public.key').open('xb') as f:
    f.write(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
PY
```

From the hive folder, after a *previously generated* `guided-...` proposal exists, open an actual interactive trusted local terminal (not CI, not a chat bot):

```bash
python agents/signed_approval.py sign guided-EXAMPLE --action apply_disposable_patch --private-key "$HOME/baby-vision-signer/private.key"
python - <<'PY'
from agents.signed_approval import fingerprint
from pathlib import Path
print('PIN OUT OF BAND:', fingerprint(Path.home() / 'baby-vision-signer/public.key'))
PY
python agents/signed_approval.py verify guided-EXAMPLE --action apply_disposable_patch --public-key "$HOME/baby-vision-signer/public.key" --trusted-fingerprint PINNED_SHA256_FROM_TRUSTED_SETUP
```

The signing confirmation includes `SIGN APPLY <patch hash prefix> <commit prefix>` (or `SIGN TEST ...`). A second action requires its **own** signature. Duplicate approval file names cannot be overwritten. Verification does not consume the record; no runner or one-use transaction protocol exists.

## Test and review gates

- `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -p 'test_*.py' -q`
- CI on Linux with Python 3.9 and 3.12, and the `cryptography` dependency.
- Validate the GitHub branch and verify all project repositories remain unchanged.
- On the actual HP ZBook, run only **public-key verification and non-execution tests** pending development of an appropriately protected Windows signer.

## Before any executor can be built

1. Provision trusted signer outside the agent's authority and enroll a pinned public-key fingerprint outside the writable hive.
2. Distinct approver and executor OS identities, with minimized filesystem and network permissions; do not allow the agent to read signing credentials.
3. Reserve each approval **atomically and durably** before executing an action. An unsigned `*.consumed` marker is not a reliable distributed replay defense.
4. Enforce target SHA, worktree cleanliness, patch hashes and path restrictions **inside** the privileged runner, not only in the caller.
5. Perform Windows 11 key custody, junction/race, Docker mount and GPU/model validation on the real ZBook. No production approval until these gates pass.

References: [Baby Vision PR #14](https://github.com/jimedusot-beep/Herbie-Baby-Vision/pull/14), [Ed25519 RFC 8032](https://www.rfc-editor.org/rfc/rfc8032), [cryptography Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
