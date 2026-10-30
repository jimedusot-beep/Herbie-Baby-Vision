"""Read-only coordination of explicitly reviewed, trusted repository checks.

Disposable snapshots are NOT security sandboxes. Run untrusted revisions only
inside an external container/VM without credentials, devices or network access.
"""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tarfile
import tempfile

PROFILES = {
    'herbie': ('node', 'tests/*.test.cjs'),
    'vision': ('node', 'tests/*.test.mjs'),
    'hardware': ('python', 'test_*.py'),
    'baby': ('python', 'test_*.py'),
}
CAPABILITIES = ['offline', 'source_accuracy', 'retrieval', 'interface_contracts']


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], timeout=30, stderr=subprocess.DEVNULL)


def snapshot(repo, revision, destination):
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()
    archive = git(repo, 'archive', '--format=tar', commit)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        members = stream.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or
                    not (member.isfile() or member.isdir()) or
                    '.git' in path.parts):
                raise ValueError('Unsafe archive entry')
        stream.extractall(destination, members=members, filter='data')
    return commit


def execute(command, checkout, timeout):
    # Inherit no tokens, model context, user configuration or Python search path.
    env = {key: os.environ[key] for key in ('PATH', 'SystemRoot', 'WINDIR') if key in os.environ}
    home = checkout.parent / 'home'
    home.mkdir(exist_ok=True)
    env.update(HOME=str(home), USERPROFILE=str(home), TMPDIR=str(home),
               TEMP=str(home), TMP=str(home), PYTHONNOUSERSITE='1',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    # Raw output stays ephemeral; report only exit status, never source or logs.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, cwd=checkout, env=env, stdout=output,
                                   stderr=output, start_new_session=os.name == 'posix')
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
            raise


def validate(repo, profile, revision='HEAD', *, trusted=False, timeout=90):
    result = {'profile': profile, 'status': 'blocked', 'merge_allowed': False,
              'deploy_allowed': False, 'capabilities': {key: 'unverified' for key in CAPABILITIES},
              'isolation': 'disposable_snapshot_not_os_sandbox'}
    if profile not in PROFILES or not trusted or timeout <= 0:
        result['reason'] = 'trusted_profile_required'
        return result
    # Windows process-tree containment is not yet implemented; fail closed.
    if os.name != 'posix':
        result['reason'] = 'process_tree_isolation_unavailable'
        return result
    try:
        with tempfile.TemporaryDirectory(prefix='baby-validation-') as directory:
            checkout = Path(directory) / 'checkout'
            checkout.mkdir()
            result['source_commit'] = snapshot(Path(repo).resolve(), revision, checkout)
            runtime, pattern = PROFILES[profile]
            package = checkout / 'package.json'
            if runtime == 'node' and package.exists():
                if json.loads(package.read_text()).get('dependencies'):
                    result['reason'] = 'dependencies_not_provisioned'
                    return result
            if runtime == 'node':
                files = sorted(str(p.relative_to(checkout)) for p in checkout.glob(pattern))
                if not files:
                    result['reason'] = 'no_tests'
                    return result
                command = ['node', '--test', *files]
            else:
                if not list((checkout / 'tests').glob(pattern)):
                    result['reason'] = 'no_tests'
                    return result
                command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern]
            result['check'] = 'existing_unit_suite'
            code = execute(command, checkout, timeout)
            result.update(status='completed' if code == 0 else 'failed', exit_code=code)
    except subprocess.TimeoutExpired:
        result['reason'] = 'timeout'
    except FileNotFoundError:
        result['reason'] = 'missing_dependency_or_repository'
    except (ValueError, subprocess.CalledProcessError, OSError):
        result['reason'] = 'snapshot_or_execution_error'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', action='append', nargs=2, metavar=('PROFILE', 'PATH'), required=True)
    parser.add_argument('--trusted', action='store_true', help='I reviewed these revisions for host execution')
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args()
    report = {'schema_version': 1, 'repositories': [validate(path, profile, args.revision,
              trusted=args.trusted, timeout=args.timeout) for profile, path in args.repository]}
    print(json.dumps(report, indent=2))
    return 0 if all(row['status'] == 'completed' for row in report['repositories']) else 1


if __name__ == '__main__':
    sys.exit(main())
