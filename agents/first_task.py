"""Baby Vision's first bounded coding task: propose an npm test entry point.

The local model proposes data. The coordinator validates one allowed edit, runs
trusted repository tests in a disposable checkout, and emits a review packet.
No model-generated command is executed. No GitHub write credentials are used.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlsplit


SCRIPT = 'npm run test:unit'
UNIT_SCRIPT = 'node --test tests/*.test.cjs'


def validate_proposal(proposal):
    if (not isinstance(proposal, dict) or set(proposal) != {'script', 'reason'}
            or proposal['script'] != SCRIPT or not isinstance(proposal['reason'], str)
            or not proposal['reason'].strip() or len(proposal['reason']) > 500):
        raise ValueError('Only the approved npm test alias and a short reason are accepted')
    return proposal


def patched_package(package, proposal):
    validate_proposal(proposal)
    scripts = package.get('scripts', {})
    if (not isinstance(scripts, dict) or scripts.get('test:unit') != UNIT_SCRIPT
            or any(key in scripts for key in ('test', 'pretest', 'posttest',
                                             'pretest:unit', 'posttest:unit'))):
        raise ValueError('Repository is not eligible for the first bounded task')
    result = deepcopy(package)
    result['scripts']['test'] = proposal['script']
    return result


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def propose(model, base_url, timeout):
    parsed = urlsplit(base_url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or not parsed.port or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Use an explicit loopback Ollama URL')
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ValueError('Local model name required')
    schema = {'type': 'object', 'properties': {
        'script': {'type': 'string', 'enum': [SCRIPT]},
        'reason': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
        'required': ['script', 'reason'], 'additionalProperties': False}
    payload = {'model': model, 'stream': False, 'format': schema,
        'options': {'temperature': 0, 'num_predict': 160, 'num_ctx': 4096},
        'messages': [
            {'role': 'system', 'content': 'You are Baby Vision, a bounded coding worker. '
             'Return only a JSON object with exactly two string fields: script and reason. '
             'Do not propose other edits or commands.'},
            {'role': 'user', 'content': 'The approved task is to add a missing npm test entry point. '
             'The repository already has test:unit = node --test tests/*.test.cjs. '
             'Propose a test script that delegates to that existing npm script. '
             'The approved script value is exactly npm run test:unit. '
             'Provide a short reason.'}]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    request = urllib.request.Request(base_url.rstrip('/') + '/api/chat',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('Model proposal exceeded its size limit')
    body = json.loads(raw)
    proposal = json.loads(body['message']['content'])
    return validate_proposal(proposal)


def review_result(proposal, *, returncode, output, patch):
    return {'status': 'ready_for_human_review' if returncode == 0 else 'blocked',
            'merge_allowed': False, 'proposal': validate_proposal(proposal),
            'test_command': ['npm', 'test'], 'test_exit_code': returncode,
            'test_output': output, 'patch': patch}


def git(repo, *arguments):
    return subprocess.run(['git', '-C', str(repo), *arguments], check=True,
                          text=True, capture_output=True, timeout=20).stdout.strip()


def run_task(repo, model, base_url='http://127.0.0.1:11434', base='HEAD', timeout=90):
    repo = Path(repo).resolve()
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}')
    with tempfile.TemporaryDirectory(prefix='baby-vision-task-') as directory:
        checkout = Path(directory) / 'checkout'
        git(repo, 'worktree', 'add', '--detach', str(checkout), commit)
        try:
            package_file = checkout / 'package.json'
            if package_file.is_symlink() or not package_file.is_file():
                raise ValueError('A regular package.json is required')
            before = json.loads(package_file.read_text())
            # Validate eligibility before spending time on model generation.
            patched_package(before, {'script': SCRIPT, 'reason': 'Eligibility check'})
            baseline = subprocess.run(['npm', 'test'], cwd=checkout,
                capture_output=True, text=True, timeout=90)
            if baseline.returncode == 0:
                raise ValueError('npm test already succeeds; choose a task that is actually needed')
            proposal = propose(model, base_url, timeout)
            after = patched_package(before, proposal)
            package_file.write_text(json.dumps(after, indent=2) + '\n')
            git(checkout, 'diff', '--check')
            if git(checkout, 'diff', '--name-only') != 'package.json':
                raise ValueError('Change escaped the approved package.json scope')
            # The command is coordinator-owned and fixed, never supplied by the model.
            # This runs trusted project tests; a disposable checkout is not an OS sandbox.
            result = subprocess.run(['npm', 'test'], cwd=checkout,
                capture_output=True, text=True, timeout=90)
            evidence = review_result(proposal, returncode=result.returncode,
                output=(result.stdout + result.stderr)[-200000:], patch=git(checkout, 'diff', '--', 'package.json'))
            evidence.update({'task': 'add-npm-test-entry-point', 'model': model,
                'source_commit': commit, 'created_at': datetime.now(timezone.utc).isoformat(),
                'allowed_files': ['package.json'], 'hosted_ci_verified': False,
                'baseline_test_exit_code': baseline.returncode,
                'baseline_test_output': (baseline.stdout + baseline.stderr)[-10000:],
                'model_generated': True, 'package_json': after})
            return evidence
        finally:
            git(repo, 'worktree', 'remove', '--force', str(checkout))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--base', default='HEAD')
    parser.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    parser.add_argument('--output', required=True, type=Path,
        help='Private evidence file; it can contain source code and test output')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new evidence path; existing files are never overwritten')
    try:
        evidence = run_task(args.repo, args.model, args.ollama_url, args.base)
    except Exception as error:
        evidence = {'status': 'blocked', 'merge_allowed': False,
                    'model': args.model, 'test_exit_code': None,
                    'error_type': type(error).__name__, 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'status': evidence['status'], 'model': args.model,
                      'test_exit_code': evidence['test_exit_code'], 'merge_allowed': False}))
    raise SystemExit(0 if evidence['status'] == 'ready_for_human_review' else 1)


if __name__ == '__main__':
    main()
