"""Opt-in Worker Bee #1: the EXISTING bounded coding task via H.E.R.B.I.E. gateway.

No new tools, autonomous commands, deployment, memory, or hardware access.
Runs trusted repository tests through first_task.run_task, NOT inside an OS sandbox.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from first_task import run_task, validate_proposal, SCRIPT, UNIT_SCRIPT
from herbie_gateway_client import HerbieGatewayClient, validate_gateway_url


class ModelProposalRejected(ValueError):
    """A safe rejection reason; never includes model output or private data."""

    def __init__(self, code):
        if code not in ('model_proposal_not_json', 'model_proposal_unapproved'):
            raise ValueError('Unexpected proposal rejection code')
        super().__init__(code)
        self.code = code


TASK_PROMPT = (
    "Return ONLY a JSON object with exactly the fields 'script' and 'reason'. "
    "The script must be exactly 'npm run test:unit'. "
    "The reason must be a short plain-English explanation (max 500 characters). "
    "This is the only approved task: create the npm test alias for a trusted "
    "repository where test:unit already equals 'node --test tests/*.test.cjs'. "
    "Do not include Markdown, shell commands, extra keys or commentary."
)


def require_local_gateway(url):
    """Worker Bee #1 is local only; remote tailnet use needs a separate review."""
    base = validate_gateway_url(url)
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Worker Bee #1 gateway must be on this computer (loopback HTTP)')
    return base


def propose_via_gateway(model, base_url, timeout, token):
    """Get data, never a command. A malformed response blocks the task."""
    base = require_local_gateway(base_url)
    client = HerbieGatewayClient(base, token, model, timeout=timeout)
    reply = client.infer('coding', TASK_PROMPT, str(uuid4()))
    try:
        parsed = json.loads(reply)
    except (ValueError, TypeError, UnicodeError):
        raise ModelProposalRejected('model_proposal_not_json') from None
    try:
        return validate_proposal(parsed)
    except ValueError:
        raise ModelProposalRejected('model_proposal_unapproved') from None


def run_gateway_task(repo, model, gateway_url, token, *, base='HEAD'):
    """Reuse the existing allowlisted edit, trusted tests and review packet."""
    url = require_local_gateway(gateway_url)
    # The gateway's upstream socket timeout is 45s; allow for proxy overhead.
    def proposer(current_model, current_url, timeout):
        return propose_via_gateway(current_model, current_url, timeout, token)
    evidence = run_task(repo, model, base_url=url, base=base, timeout=60,
                        proposer=proposer)
    evidence['proposal_transport'] = 'authenticated_herbie_gateway'
    evidence['remote_devices_tested'] = False
    evidence['merge_allowed'] = False
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path,
                        help='Path to an owner-approved TRUSTED Git checkout')
    parser.add_argument('--model', required=True,
                        help='Exact model allowlisted in the local H.E.R.B.I.E. gateway')
    parser.add_argument('--gateway-url', required=True,
                        help='Explicit localhost gateway URL, e.g. http://127.0.0.1:8787')
    parser.add_argument('--token-env', default='HERBIE_WORKER_TOKEN',
                        help='Environment variable holding the gateway bearer token')
    parser.add_argument('--base', default='HEAD', help='Committed source revision')
    parser.add_argument('--output', required=True, type=Path,
                        help='New private evidence JSON path outside the public repository')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Evidence output exists; never overwrite an earlier report')
    try:
        if not args.token_env.isidentifier():
            raise ValueError('Invalid token environment variable name')
        token = os.environ.get(args.token_env, '')
        if not token:
            raise ValueError('Gateway token environment variable not configured')
        evidence = run_gateway_task(args.repo, args.model, args.gateway_url, token,
                                    base=args.base)
    except Exception as exc:
        # Never echo source, tokens, pathnames, upstream errors, or model output.
        evidence = {'status':'blocked', 'merge_allowed':False, 'model':args.model,
                    'test_exit_code':None, 'error_type':type(exc).__name__,
                    'error':'Worker task blocked; inspect configuration and private logs'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status':evidence['status'], 'merge_allowed':False,
                      'test_exit_code':evidence['test_exit_code']}))
    return 0 if evidence['status'] == 'ready_for_human_review' else 1


if __name__ == '__main__':
    raise SystemExit(main())
