"""V0.4.3: Ed25519-signed, review-only human approval attestations.

This is a SIGNATURE VERIFICATION PROTOTYPE. It performs no project execution.
A signature is meaningful ONLY when the signing key is inaccessible to the bee
and its runtime account; this package cannot create that OS trust boundary.

Requires: pip install cryptography (supported dependency in CI).
Existing legacy approval_gate.py JSON decisions are never accepted here.
"""
import argparse
import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except ImportError as exc:
    raise ImportError('Install the cryptography package for signed approvals') from exc

try:
    from . import approval_gate as legacy
    from . import artifact_io
except ImportError:
    import approval_gate as legacy
    import artifact_io

SCHEMA = 'baby-vision-signed-approval-v1'
DOMAIN = b'BABY-VISION-SIGNED-APPROVAL-v1\0'
VALID_ACTIONS = frozenset(legacy.ACTIONS)
MAX_RECORD = 4096
MAX_KEY = 32
TTL = timedelta(minutes=15)
CLOCK_SKEW = timedelta(seconds=30)
HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX32 = re.compile(r'^[0-9a-f]{32}$')
KEY_FIELDS = frozenset({'schema', 'action', 'proposal', 'source_commit', 'target',
                        'report_sha256', 'diff_sha256', 'issued_at', 'expires_at',
                        'nonce', 'key_sha256'})
RECORD_FIELDS = frozenset({'payload', 'signature'})


class SignedApprovalError(ValueError):
    """A bounded error that never reproduces private source content."""


def _fail(message):
    raise SignedApprovalError(message)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _is_child(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_key(path, private):
    """Reject keys in hive, redirects, hardlinks and weak POSIX private-key modes."""
    p = Path(path).expanduser()
    hive = legacy.bridge.investigation.HIVE.resolve()
    try:
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) or (
                p.parent.is_symlink() or (hasattr(p.parent, 'is_junction') and p.parent.is_junction())):
            _fail('Signing key path is redirected')
        resolved = p.resolve(strict=True)
        if _is_child(resolved, hive) or resolved == hive:
            _fail('Signing keys must be held outside the bee workspace')
        info = p.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != MAX_KEY:
            _fail('Invalid key file')
        if private:
            if os.name == 'nt':
                _fail('Windows private-key custody requires a separate protected signer')
            if info.st_mode & 0o077:
                _fail('Private signing key has unsafe permissions')
            parent_info = p.parent.stat()
            if parent_info.st_mode & 0o077:
                _fail('Private signing key directory must be owner-only')
            if hasattr(os, 'getuid') and parent_info.st_uid != os.getuid():
                _fail('Private signing key directory belongs to another account')
            if hasattr(os, 'getuid') and info.st_uid != os.getuid():
                _fail('Private signing key belongs to another account')
        # No-follow open on POSIX. On Windows this is only a public key read.
        fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_size != MAX_KEY:
                _fail('Key file changed during inspection')
            raw = os.read(fd, 33)
        finally:
            os.close(fd)
        if len(raw) != MAX_KEY:
            _fail('Invalid key size')
        return raw
    except (OSError, RuntimeError) as exc:
        raise SignedApprovalError('Unable to access trusted key') from exc


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        _fail('Invalid approval timestamp')
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, OverflowError) as exc:
        raise SignedApprovalError('Invalid approval timestamp') from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        _fail('Approval timestamp must be UTC')
    return dt


def fingerprint(public_key_file):
    return hashlib.sha256(_read_key(public_key_file, False)).hexdigest()


def _filename(name, action):
    if action not in VALID_ACTIONS:
        _fail('Unknown approval action')
    if not isinstance(name, str) or not legacy.NAME.fullmatch(name):
        _fail('Invalid proposal identifier')
    return f'{name}.{action}.signed.json'


def _payload(proposal, action, key_sha, now):
    return {'schema': SCHEMA, 'action': action, 'proposal': proposal['name'],
            'source_commit': proposal['source_commit'], 'target': proposal['target'],
            'report_sha256': proposal['report_sha256'], 'diff_sha256': proposal['diff_sha256'],
            'issued_at': now.isoformat(), 'expires_at': (now + TTL).isoformat(),
            'nonce': os.urandom(16).hex(), 'key_sha256': key_sha}


def sign(name, action, *, private_key_file, confirmation, interactive):
    """Write one signed decision. No patch application, process execution or tests."""
    if not interactive:
        _fail('Signing requires an interactive trusted terminal')
    if action not in VALID_ACTIONS:
        _fail('Unknown approval action')
    proposal = legacy.inspect(name)
    phrase = f'SIGN {legacy.ACTIONS[action]} {proposal["diff_sha256"][:12]} {proposal["source_commit"][:12]}'
    if confirmation != phrase:
        _fail('Explicit confirmation phrase does not match')
    if legacy._blocked(proposal['name'], action):
        _fail('Proposal has already been rejected, revoked or consumed')
    # The private key MUST NOT be accessible to an untrusted bee process.
    secret = _read_key(private_key_file, True)
    private = Ed25519PrivateKey.from_private_bytes(secret)
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    key_sha = hashlib.sha256(public).hexdigest()
    now = datetime.now(timezone.utc)
    body = _payload(proposal, action, key_sha, now)
    signature = private.sign(DOMAIN + _json_bytes(body))
    record = {'payload': body, 'signature': base64.b64encode(signature).decode('ascii')}
    legacy._guard()
    if legacy.inspect(name)['report_sha256'] != proposal['report_sha256']:
        _fail('Proposal changed while signing')
    try:
        artifact_io.write_exclusive(legacy.bridge.investigation.HIVE, 'approvals',
                                    _filename(proposal['name'], action), _json_bytes(record) + b'\n')
    except artifact_io.ArtifactError as exc:
        raise SignedApprovalError('Signed record already exists or output is unsafe') from exc
    return {'action': action, 'proposal': proposal['name'], 'key_sha256': key_sha,
            'expires_at': body['expires_at'], 'warning': 'REVIEW ONLY: no execution is connected'}


def verify(name, action, *, public_key_file, trusted_fingerprint):
    """Verify with a separately pinned trusted public-key fingerprint.

    A matching signature is not sufficient to authorize execution: a future
    privileged runner must separately enforce OS isolation and atomic replay
    prevention. This function never provides an execution capability.
    """
    if not isinstance(trusted_fingerprint, str) or not HEX64.fullmatch(trusted_fingerprint):
        _fail('Pinned trusted fingerprint is required')
    proposal = legacy.inspect(name)
    if action not in VALID_ACTIONS or legacy._blocked(proposal['name'], action):
        _fail('Action refused by current proposal state')
    public = _read_key(public_key_file, False)
    actual = hashlib.sha256(public).hexdigest()
    if actual != trusted_fingerprint:
        _fail('Public signing key differs from pinned trust anchor')
    path = legacy._record_path(proposal['name'], action).parent / _filename(proposal['name'], action)
    try:
        raw = legacy._read_regular(path, MAX_RECORD)
        record = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise SignedApprovalError('Missing or invalid signed decision') from exc
    if not isinstance(record, dict) or frozenset(record) != RECORD_FIELDS:
        _fail('Unrecognized signed decision format')
    payload = record['payload']
    if not isinstance(payload, dict) or frozenset(payload) != KEY_FIELDS:
        _fail('Signed decision has unexpected fields')
    if any(type(payload[k]) is not str for k in KEY_FIELDS):
        _fail('Signed decision has invalid value types')
    if (payload['schema'] != SCHEMA or payload['action'] != action
            or payload['proposal'] != proposal['name']
            or payload['source_commit'] != proposal['source_commit']
            or payload['target'] != proposal['target']
            or payload['report_sha256'] != proposal['report_sha256']
            or payload['diff_sha256'] != proposal['diff_sha256']
            or payload['key_sha256'] != actual
            or not HEX32.fullmatch(payload['nonce'])):
        _fail('Signed decision does not match this exact proposal and key')
    issued = _timestamp(payload['issued_at'])
    expiry = _timestamp(payload['expires_at'])
    now = datetime.now(timezone.utc)
    if issued > now + CLOCK_SKEW or expiry <= now or expiry <= issued or expiry - issued > TTL:
        _fail('Signed decision is stale, future-dated or overlong')
    if not isinstance(record['signature'], str):
        _fail('Invalid signature encoding')
    try:
        signature = base64.b64decode(record['signature'], validate=True)
        if len(signature) != 64:
            _fail('Invalid signature length')
        Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + _json_bytes(payload))
    except (binascii.Error, ValueError, InvalidSignature) as exc:
        raise SignedApprovalError('Approval signature invalid') from exc
    legacy._guard()
    return {'proposal': proposal['name'], 'action': action, 'expires_at': payload['expires_at'],
            'signed': True, 'key_sha256': actual,
            'warning': 'Signed decision only; no execution authority or replay service exists'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('sign')
    s.add_argument('proposal')
    s.add_argument('--action', required=True, choices=sorted(VALID_ACTIONS))
    s.add_argument('--private-key', required=True, type=Path)
    v = sub.add_parser('verify')
    v.add_argument('proposal')
    v.add_argument('--action', required=True, choices=sorted(VALID_ACTIONS))
    v.add_argument('--public-key', required=True, type=Path)
    v.add_argument('--trusted-fingerprint', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'sign':
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                _fail('Cannot sign outside a trusted local interactive terminal')
            info = legacy.inspect(args.proposal)
            print('ACTION:', args.action, '\nSOURCE:', info['source_commit'],
                  '\nTARGET:', info['target'], '\nPATCH SHA:', info['diff_sha256'],
                  '\n--- REVIEW THIS PATCH ---\n' + info['diff'])
            phrase = f'SIGN {legacy.ACTIONS[args.action]} {info["diff_sha256"][:12]} {info["source_commit"][:12]}'
            print('Type exactly:', phrase)
            result = sign(args.proposal, args.action, private_key_file=args.private_key,
                          confirmation=input('Confirm: '), interactive=True)
        else:
            result = verify(args.proposal, args.action, public_key_file=args.public_key,
                            trusted_fingerprint=args.trusted_fingerprint)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SignedApprovalError, legacy.ApprovalError, OSError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
