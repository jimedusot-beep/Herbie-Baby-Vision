"""Baby Vision V0.4: local human decisions bound to an exact proposed diff.

This module NEVER applies a patch, runs tests, invokes Docker or Ollama,
commits, pushes or deploys. An approval is NOT an execution capability: a
separate privileged runner must enforce these gates before any future action.

Only an interactive terminal can issue a decision. No -y/noninteractive bypass.
This records local user intent, not proof of the human's cryptographic identity.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys

try:
    from . import proposal_bridge as bridge
    from . import artifact_io
except ImportError:
    import proposal_bridge as bridge
    import artifact_io

ACTIONS = {'apply_disposable_patch': 'APPLY', 'run_isolated_tests': 'TEST'}
APPROVAL_DURATION = timedelta(hours=1)
MAX_REPORT_BYTES = 20000
HEX = re.compile(r'^[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40,64}$')
NAME = re.compile(r'^guided-[A-Za-z0-9_-]{10,100}$')


class ApprovalError(ValueError):
    """Fail closed without including source/model contents in error messages."""


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _guard():
    try:
        bridge.stopped()
    except Exception as exc:
        raise ApprovalError('STOP is set; approvals disabled') from exc


def _dirs():
    root = bridge.investigation.HIVE
    proposal_dir = bridge.investigation.REPORTS
    decision_dir = root / 'approvals'
    # Never follow a symlinked control directory outside the hive.
    if (root.is_symlink() or proposal_dir.is_symlink() or decision_dir.is_symlink()
            or proposal_dir.resolve() != root.resolve() / 'proposals'
            or decision_dir.resolve() != root.resolve() / 'approvals'):
        raise ApprovalError('Unexpected or symlinked approval/proposal directory')
    return proposal_dir, decision_dir


def _read_regular(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ApprovalError('Missing or unsafe review artifact')
    return path.read_bytes()


def inspect(name):
    """Fail unless exactly this report, diff and source revision remain valid."""
    _guard()
    if not isinstance(name, str):
        raise ApprovalError('Invalid proposal identifier')
    stem = name[:-5] if name.endswith('.json') else name
    if not NAME.fullmatch(stem):
        raise ApprovalError('Use only a guided proposal basename')
    proposal_dir, _ = _dirs()
    report_raw = _read_regular(proposal_dir / (stem + '.json'), MAX_REPORT_BYTES)
    diff_raw = _read_regular(proposal_dir / (stem + '.diff'), bridge.MAX_PATCH_BYTES)
    try:
        report = json.loads(report_raw.decode('utf-8'))
        diff = diff_raw.decode('utf-8')
    except (UnicodeError, ValueError) as exc:
        raise ApprovalError('Invalid review artifact encoding') from exc
    if not isinstance(report, dict) or not isinstance(report.get('target'), str):
        raise ApprovalError('Missing or invalid proposal metadata')
    if (not isinstance(report.get('source_commit'), str) or
            not COMMIT.fullmatch(report['source_commit']) or
            not isinstance(report.get('diff_sha256'), str) or
            not HEX.fullmatch(report['diff_sha256']) or
            report['diff_sha256'] != _digest(diff_raw)):
        raise ApprovalError('Proposal checksum or source commit invalid')
    try:
        commit = bridge.investigation.check_work()
        if commit != report['source_commit']:
            raise ApprovalError('Checkout changed from proposal source commit')
        bridge.validate_patch(diff, report['target'])
    except (bridge.ProposalError, bridge.investigation.InvestigationError) as exc:
        raise ApprovalError('Source is stale or proposed patch failed validation') from exc
    _guard()
    return {'name': stem, 'target': report['target'], 'source_commit': commit,
            'report_sha256': _digest(report_raw), 'diff_sha256': _digest(diff_raw),
            'diff': diff, 'partial_scan': report.get('partial_scan', True)}


def _record_path(name, action):
    _, decision_dir = _dirs()
    if action not in ACTIONS:
        raise ApprovalError('Unrecognized action')
    return decision_dir / (name + '.' + action + '.json')


def _marker(name, suffix):
    _, decision_dir = _dirs()
    return decision_dir / (name + '.' + suffix)


def _safe_write(path, contents):
    """Use the same guarded output policy for approval *records* as proposals."""
    root = bridge.investigation.HIVE
    if path.parent != root / 'approvals':
        raise ApprovalError('Unexpected decision destination')
    try:
        artifact_io.write_exclusive(root, 'approvals', path.name, contents.encode('utf-8'))
    except artifact_io.ArtifactError as exc:
        raise ApprovalError('Unsafe decision destination or existing record') from exc


def _blocked(name, action):
    return (_marker(name, 'rejected').exists() or
            _marker(name, 'revoked').exists() or
            _marker(name, action + '.consumed').exists())


def issue(name, action, *, typed, terminal):
    """Record human decision only; cannot execute the requested action."""
    if action not in ACTIONS:
        raise ApprovalError('Unrecognized action')
    if not terminal:
        raise ApprovalError('Approval requires an interactive local terminal')
    proposal = inspect(name)
    expected = f'APPROVE {ACTIONS[action]} {proposal["diff_sha256"][:12]}'
    if typed != expected:
        raise ApprovalError('Approval phrase mismatch; no permission granted')
    if _blocked(proposal['name'], action):
        raise ApprovalError('Proposal is rejected, revoked or already used')
    issued = _now()
    record = {'schema': 'baby-vision-approval-v1', 'action': action,
              'proposal': proposal['name'], 'source_commit': proposal['source_commit'],
              'target': proposal['target'], 'report_sha256': proposal['report_sha256'],
              'diff_sha256': proposal['diff_sha256'], 'approved_at': issued.isoformat(),
              'expires_at': (issued + APPROVAL_DURATION).isoformat(),
              'nonce': secrets.token_hex(16),
              'warning': 'Decision record only; does not execute any operation.'}
    _safe_write(_record_path(proposal['name'], action), json.dumps(record, sort_keys=True) + '\n')
    return record


def _get_record(proposal, action):
    path = _record_path(proposal['name'], action)
    if not path.exists():
        raise ApprovalError('Separate approval for this action is missing')
    raw = _read_regular(path, 5000)
    try:
        record = json.loads(raw)
        expiry = datetime.fromisoformat(record['expires_at'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ApprovalError('Invalid approval record') from exc
    if (record.get('schema') != 'baby-vision-approval-v1'
            or record.get('action') != action
            or record.get('proposal') != proposal['name']
            or record.get('target') != proposal['target']
            or record.get('source_commit') != proposal['source_commit']
            or record.get('report_sha256') != proposal['report_sha256']
            or record.get('diff_sha256') != proposal['diff_sha256']
            or not isinstance(record.get('nonce'), str)
            or not re.fullmatch(r'[0-9a-f]{32}', record['nonce'])
            or expiry.tzinfo is None or expiry <= _now()
            or expiry - _now() > APPROVAL_DURATION + timedelta(minutes=1)):
        raise ApprovalError('Approval expired or no longer matches exact proposal')
    return record


def verify(name, action):
    """Check decision readiness without consuming or performing an operation."""
    proposal = inspect(name)
    if action not in ACTIONS or _blocked(proposal['name'], action):
        raise ApprovalError('No valid authorization for this action')
    return _get_record(proposal, action)


def consume(name, action):
    """Atomically mark a decision used; internal contract for future runner only.

    Does not apply a patch or run tests. Future executors must enforce proper
    isolation, verify source and patch hashes and call this before executing.
    """
    record = verify(name, action)
    _safe_write(_marker(record['proposal'], action + '.consumed'),
                json.dumps({'nonce': record['nonce'], 'consumed_at': _now().isoformat()}) + '\n')
    return record


def close(name, decision):
    if decision not in ('rejected', 'revoked'):
        raise ApprovalError('Invalid decision')
    proposal = inspect(name)
    _safe_write(_marker(proposal['name'], decision),
                json.dumps({'decision': decision, 'at': _now().isoformat()}) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='cmd', required=True)
    for verb in ('review', 'approve', 'status', 'reject', 'revoke'):
        p = subs.add_parser(verb)
        p.add_argument('proposal', help='Guided proposal basename, not an arbitrary file path')
        if verb in ('approve', 'status'):
            p.add_argument('--action', required=True, choices=sorted(ACTIONS))
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'review':
            result = inspect(args.proposal)
            print(f"Proposal: {result['name']}\nFile: {result['target']}\n"
                  f"Source commit: {result['source_commit']}\n"
                  f"Patch SHA-256: {result['diff_sha256']}\n"
                  f"Partial scan: {result['partial_scan']}\n--- DIFF FOR REVIEW ---\n{result['diff']}")
        elif args.cmd == 'approve':
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise ApprovalError('Refusing approval without an interactive local terminal')
            proposal = inspect(args.proposal)
            print(f"Source: {proposal['source_commit']}\nTarget: {proposal['target']}\n"
                  f"Patch SHA-256: {proposal['diff_sha256']}\n--- FULL PATCH ---\n{proposal['diff']}")
            challenge = f"APPROVE {ACTIONS[args.action]} {proposal['diff_sha256'][:12]}"
            print(f'Confirm only this {args.action} action. Type exactly: {challenge}')
            entry = input('Your decision: ')
            issued = issue(proposal['name'], args.action, typed=entry, terminal=True)
            print(f"Recorded {issued['action']} decision; expires {issued['expires_at']}.")
            print('NO PATCH APPLIED. NO TESTS RUN. A separate approved runner is required.')
        elif args.cmd == 'status':
            r = verify(args.proposal, args.action)
            print(f"Approved decision exists for {r['action']}; expires {r['expires_at']}.")
            print('Decision only. No execution is connected.')
        else:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise ApprovalError('Rejection/revocation requires a local interactive terminal')
            if input(f'Type {args.cmd.upper()} to confirm: ') != args.cmd.upper():
                raise ApprovalError('No decision recorded')
            close(args.proposal, 'rejected' if args.cmd == 'reject' else 'revoked')
            print('Decision recorded. No actions will be authorized by this proposal.')
        return 0
    except (ApprovalError, OSError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
