"""V0.4.4: reference *non-executing* one-use reservation of signed approvals.

IMPORTANT: This is not a Windows trust service. Windows reservations are refused.
The signer key, trusted public-key pin and SQLite database must be owned by a
separate trusted OS identity for *any* credible security boundary. Python file
checks alone never establish that separation. Reservation does not run actions.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from urllib.parse import quote

try:
    from . import signed_approval as signed
except ImportError:
    import signed_approval as signed

SCHEMA_VERSION = 1
DOMAIN = b'BABY-VISION-SINGLE-USE-v1\0'

class ReplayError(ValueError):
    """Fail-closed reservation problem without revealing source content."""


def _hive():
    return signed.legacy.bridge.investigation.HIVE.resolve()


def _check_path(db, *, must_exist):
    """POSIX demo file protection; no Windows ACL trust assertions."""
    if os.name == 'nt':
        raise ReplayError('Windows ledger requires a separately secured service; refused')
    p = Path(db).expanduser().absolute()
    if p.suffix != '.sqlite3' or p.name.startswith('.'):
        raise ReplayError('Ledger must be a named .sqlite3 file')
    if p == _hive() or _hive() in p.parents:
        raise ReplayError('Replay ledger must be outside the worker workspace')
    # Reject all symlink ancestors, including links to a protected directory.
    for candidate in (p, *p.parents):
        if candidate.is_symlink():
            raise ReplayError('Ledger path contains a symlink')
    try:
        parent = p.parent.stat()
    except OSError as exc:
        raise ReplayError('Ledger parent missing') from exc
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o077
            or hasattr(os, 'getuid') and parent.st_uid != os.getuid()):
        raise ReplayError('Ledger parent is not protected by owner-only permissions')
    if must_exist:
        try:
            fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            try:
                info = os.fstat(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise ReplayError('Trusted ledger not available') from exc
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_mode & 0o077
                or hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise ReplayError('Trusted ledger is unsafe or accessible to other accounts')
    elif p.exists():
        raise ReplayError('Refusing to overwrite existing ledger')
    # Reject symlinked SQLite sidecars too. Database directory must be protected
    # from other accounts and is never writable by an untrusted bee process.
    for suffix in ('-journal', '-wal', '-shm'):
        side = Path(str(p) + suffix)
        if side.is_symlink():
            raise ReplayError('Unsafe SQLite sidecar')
    return p


def _connect(p, *, create=False):
    # No implicit file creation on reserve. Init creates the file with O_EXCL.
    if create:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        os.close(fd)
    uri = 'file:' + quote(str(p), safe='/') + '?mode=rw'
    con = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
    try:
        con.execute('PRAGMA trusted_schema=OFF')
        con.execute('PRAGMA busy_timeout=10000')
        con.execute('PRAGMA synchronous=FULL')
        con.execute('PRAGMA journal_mode=DELETE')
        return con
    except Exception:
        con.close()
        raise


def provision(ledger):
    """Create an EMPTY review-only ledger. Must be run by trusted account."""
    p = _check_path(ledger, must_exist=False)
    try:
        with closing(_connect(p, create=True)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE claims ('
                       'claim_id TEXT PRIMARY KEY, proposal TEXT NOT NULL, '
                       'action TEXT NOT NULL, key_sha256 TEXT NOT NULL, '
                       'source_commit TEXT NOT NULL, claimed_at TEXT NOT NULL, '
                       'UNIQUE(proposal,action))')
            db.execute('PRAGMA user_version=1')
            db.execute('COMMIT')
    except (OSError, sqlite3.Error) as exc:
        raise ReplayError('Could not provision trusted ledger') from exc
    return {'provisioned': True, 'execution': False}


def _claim_id(decision):
    fields = {key:decision[key] for key in ('proposal', 'action', 'key_sha256', 'nonce',
              'source_commit', 'report_sha256', 'diff_sha256')}
    body = json.dumps(fields, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    return hashlib.sha256(DOMAIN + body).hexdigest()


def reserve(name, action, *, ledger, public_key_file, trusted_fingerprint):
    """Commit exactly one durable reservation BEFORE any future action.

    This method does NOT execute an action and provides NO execution authority.
    A trusted isolated runner must call it *internally*, not trust a caller's
    claimed reservation, nonce, fingerprint, or stdout response.
    """
    p = _check_path(ledger, must_exist=True)
    try:
        decision = signed.verify(name, action, public_key_file=public_key_file,
                                 trusted_fingerprint=trusted_fingerprint)
    except (signed.SignedApprovalError, signed.legacy.ApprovalError) as exc:
        raise ReplayError('Signed approval verification failed') from exc
    try:
        with closing(_connect(p)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                raise ReplayError('Unsupported replay ledger version')
            db.execute('BEGIN IMMEDIATE')
            # Check STOP again inside the reservation transaction.
            try:
                signed.legacy._guard()
                if signed.legacy._blocked(name, action):
                    raise ReplayError('Approval is revoked, stopped, or consumed')
            except signed.legacy.ApprovalError as exc:
                raise ReplayError('STOP prevents reservation') from exc
            db.execute('INSERT INTO claims VALUES (?,?,?,?,?,?)',
                 (_claim_id(decision), decision['proposal'], decision['action'],
                  decision['key_sha256'], decision['source_commit'],
                  datetime.now(timezone.utc).isoformat()))
            db.execute('COMMIT')
    except sqlite3.IntegrityError as exc:
        raise ReplayError('Approval already reserved; replay refused') from exc
    except sqlite3.Error as exc:
        raise ReplayError('Trusted replay ledger is unavailable or invalid') from exc
    return {'reserved': True, 'action': action, 'proposal': decision['proposal'],
            'claim_id': _claim_id(decision), 'executed': False,
            'warning': 'Review-only reservation; no executor or Windows security boundary'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    init = sub.add_parser('provision')
    init.add_argument('--ledger', required=True, type=Path)
    p = sub.add_parser('reserve')
    p.add_argument('proposal')
    p.add_argument('--action', required=True, choices=sorted(signed.VALID_ACTIONS))
    p.add_argument('--ledger', required=True, type=Path)
    p.add_argument('--public-key', required=True, type=Path)
    p.add_argument('--trusted-fingerprint', required=True)
    args = parser.parse_args(argv)
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise ReplayError('Trusted replay operations require an interactive terminal')
        result = (provision(args.ledger) if args.cmd == 'provision' else
                  reserve(args.proposal, args.action, ledger=args.ledger,
                          public_key_file=args.public_key,
                          trusted_fingerprint=args.trusted_fingerprint))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ReplayError, OSError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
