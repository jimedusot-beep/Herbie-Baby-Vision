"""Opt-in Worker Bee #1: the EXISTING bounded coding task via H.E.R.B.I.E. gateway.

No new tools, autonomous commands, deployment, memory, or hardware access.
Runs trusted repository tests through first_task.run_task, NOT inside an OS sandbox.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from first_task import run_task, validate_proposal, SCRIPT, UNIT_SCRIPT
from container_test_runner import run_container_npm_test
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


def propose_via_gateway(model, base_url, timeout, token, *, request_id=None, cancel_event=None):
    """Get data, never a command. A malformed response blocks the task."""
    base = require_local_gateway(base_url)
    client = HerbieGatewayClient(base, token, model, timeout=timeout)
    reply = client.infer('npm_test_alias_v1', TASK_PROMPT,
                         request_id or str(uuid4()), cancel_event=cancel_event)
    try:
        parsed = json.loads(reply)
    except (ValueError, TypeError, UnicodeError):
        raise ModelProposalRejected('model_proposal_not_json') from None
    try:
        return validate_proposal(parsed)
    except ValueError:
        raise ModelProposalRejected('model_proposal_unapproved') from None


def run_gateway_task(repo, model, gateway_url, token, *, base='HEAD',
                     request_id=None, cancel_event=None, sandbox_image=None):
    """Reuse the bounded task; callers can supply an ID and local STOP signal.

    Caller must set cancel_event and separately invoke client.cancel(request_id)
    to record logical cancellation at the gateway. This cannot abort npm already
    running on the host; no sandbox or OS process termination is implied.
    """
    url = require_local_gateway(gateway_url)
    # The gateway's upstream socket timeout is 45s; allow for proxy overhead.
    def proposer(current_model, current_url, timeout):
        return propose_via_gateway(current_model, current_url, timeout, token,
                                   request_id=request_id, cancel_event=cancel_event)
    executor = (lambda checkout: run_container_npm_test(
        checkout, image=sandbox_image)) if sandbox_image else None
    evidence = run_task(repo, model, base_url=url, base=base, timeout=60,
                        proposer=proposer, cancel_event=cancel_event,
                        test_executor=executor)
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
    parser.add_argument('--allow-trusted-host-tests', action='store_true',
        help='Explicit opt-in to unsandboxed npm tests on an owner-approved repository')
    parser.add_argument('--request-id', default=None,
        help='Canonical UUID retained by the operator; reuse it on every retry')
    parser.add_argument('--sandbox-image',
        help='Optional local digest-pinned Docker Node image; no network or image pull')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Evidence output exists; never overwrite an earlier report')
    try:
        if bool(args.allow_trusted_host_tests) == bool(args.sandbox_image):
            raise PermissionError('Choose trusted host opt-in OR isolated npm test image')
        # Never generate a fresh UUID on a repeatable CLI invocation: doing
        # so would bypass the gateway's durable same-ID replay protection.
        try:
            if (not isinstance(args.request_id, str)
                    or str(UUID(args.request_id)) != args.request_id):
                raise ValueError()
        except ValueError:
            raise ValueError('Explicit canonical --request-id required for host CLI') from None
        if not args.token_env.isidentifier():
            raise ValueError('Invalid token environment variable name')
        token = os.environ.get(args.token_env, '')
        if not token:
            raise ValueError('Gateway token environment variable not configured')
        kwargs = {'base': args.base, 'request_id': args.request_id}
        if args.sandbox_image:
            kwargs['sandbox_image'] = args.sandbox_image
        evidence = run_gateway_task(args.repo, args.model, args.gateway_url, token,
                                    **kwargs)
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
