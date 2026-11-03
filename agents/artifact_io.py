"""Bounded review-artifact I/O; never use project checkout as an output directory.

POSIX uses relative directory handles + O_NOFOLLOW to resist symlink swaps.
Windows uses path/reparse validation plus exclusive file creation. This is NOT
an isolation boundary against a hostile process with the same account rights.
No generated code is executed by this module.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat

SAFE_LABELS = frozenset({'proposals', 'logs', 'approvals', 'tasks', 'work'})
SAFE_FILE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,170}$')
MAX_WRITE = 500_000


class ArtifactError(ValueError):
    """Refuse unsafe review-artifact output, without disclosing source content."""


def _reparse(path):
    """Includes Windows directory junctions on Python versions before is_junction."""
    try:
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            return True
        if os.name == 'nt' and path.exists():
            return bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError as exc:
        raise ArtifactError('Could not verify artifact directory') from exc
    return False



def verify_disposable_checkout(root, checkout):
    """Reject redirected work/, checkout and .git paths before reading Git.

    The checkout must be a *physical directory* at hive/work/trivia-lobby,
    rather than a symlink or Windows junction to another repository.
    This is a safety precondition, not a sandbox or proof of ownership.
    """
    root = Path(root)
    checkout = Path(checkout)
    work = root / 'work'
    git_dir = checkout / '.git'
    if checkout != work / 'trivia-lobby':
        raise ArtifactError('Unexpected disposable checkout location')
    try:
        if any(_reparse(p) or not p.is_dir() for p in (root, work, checkout, git_dir)):
            raise ArtifactError('Missing or redirected disposable checkout directory')
        canonical_root = root.resolve(strict=True)
        if (work.resolve(strict=True) != canonical_root / 'work' or
                checkout.resolve(strict=True) != canonical_root / 'work' / 'trivia-lobby' or
                git_dir.resolve(strict=True) != canonical_root / 'work' / 'trivia-lobby' / '.git'):
            raise ArtifactError('Disposable checkout resolves outside the hive')
    except OSError as exc:
        raise ArtifactError('Could not verify disposable checkout directories') from exc
    return checkout


@contextmanager
def _stop_parent(root):
    """Verify the hive root and hold a physical root directory FD on POSIX."""
    root = Path(root)
    if _reparse(root) or not root.is_dir():
        raise ArtifactError('Unsafe STOP marker parent')
    dfd = None
    try:
        if os.name != 'nt' and os.open in os.supports_dir_fd:
            flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            dfd = os.open(root, flags)
            if not stat.S_ISDIR(os.fstat(dfd).st_mode):
                raise ArtifactError('Unsafe STOP marker parent')
        yield root, dfd
    except OSError as exc:
        raise ArtifactError('Could not safely access STOP marker') from exc
    finally:
        if dfd is not None:
            os.close(dfd)


def _stop_lstat(root, dfd):
    try:
        if dfd is not None:
            return os.stat('STOP', dir_fd=dfd, follow_symlinks=False)
        return (root / 'STOP').lstat()
    except FileNotFoundError:
        return None


def _stop_regular(root, info):
    return (info is not None and stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1 and not _reparse(root / 'STOP'))


def stop_present(root):
    """Any STOP entry, even a dangling symlink, disables work (fail closed)."""
    with _stop_parent(root) as (path, dfd):
        return _stop_lstat(path, dfd) is not None


def set_stop(root):
    """Create a STOP marker exclusively, never following or overwriting links.

    An existing *regular, singly-linked* marker is already active. Reject
    redirected markers and other filesystem types. No owner file is overwritten.
    """
    with _stop_parent(root) as (path, dfd):
        # On Windows O_CREAT|O_EXCL is not guaranteed to reject a dangling
        # reparse link. Check lexically first, then retain exclusive creation
        # for ordinary races. This is not isolation from a hostile same-user
        # process concurrently modifying the directory.
        preexisting = _stop_lstat(path, dfd)
        if preexisting is not None:
            if not _stop_regular(path, preexisting):
                raise ArtifactError('Refusing redirected or nonregular STOP marker')
            return False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        try:
            if dfd is not None:
                fd = os.open('STOP', flags, 0o600, dir_fd=dfd)
            else:
                fd = os.open(path / 'STOP', flags, 0o600)
        except FileExistsError:
            if not _stop_regular(path, _stop_lstat(path, dfd)):
                raise ArtifactError('Refusing redirected or nonregular STOP marker')
            return False
        _write_all(fd, b'disabled\n')
        return True


def clear_stop(root):
    """Remove only a regular standalone STOP filename, without following links."""
    with _stop_parent(root) as (path, dfd):
        info = _stop_lstat(path, dfd)
        if info is None:
            return False
        if not _stop_regular(path, info):
            raise ArtifactError('Refusing redirected or nonregular STOP marker')
        try:
            if dfd is not None:
                os.unlink('STOP', dir_fd=dfd)
            else:
                (path / 'STOP').unlink()
        except FileNotFoundError:
            return False
        return True

def _location(root, label):
    root = Path(root)
    if label not in SAFE_LABELS or not root.is_dir() or _reparse(root):
        raise ArtifactError('Unsafe hive root or output directory label')
    target = root / label
    if _reparse(target):
        raise ArtifactError('Refusing redirected artifact directory')
    try:
        if root.resolve() / label != target.resolve():
            raise ArtifactError('Artifact directory escapes hive root')
    except OSError as exc:
        raise ArtifactError('Could not resolve artifact directory') from exc
    return root, target


@contextmanager
def open_directory(root, label):
    """Yield (directory FD or None, path). Do not open target files by PATH on POSIX."""
    root, target = _location(root, label)
    if (os.name != 'nt' and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd):
        flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        root_fd = None
        child_fd = None
        try:
            root_fd = os.open(root, flags)
            try:
                os.mkdir(label, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            child_fd = os.open(label, flags, dir_fd=root_fd)
            if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                raise ArtifactError('Artifact location is not a directory')
            yield child_fd, target
        except OSError as exc:
            raise ArtifactError('Could not safely open artifact directory') from exc
        finally:
            if child_fd is not None:
                os.close(child_fd)
            if root_fd is not None:
                os.close(root_fd)
    else:
        # Path-based fallback for Windows. Reject reparse points before/after
        # creation; a concurrent hostile process still requires OS isolation.
        try:
            target.mkdir(mode=0o700, exist_ok=True)
            _location(root, label)
            if not target.is_dir() or _reparse(target):
                raise ArtifactError('Unexpected artifact directory')
            yield None, target
        except OSError as exc:
            raise ArtifactError('Could not safely create artifact directory') from exc


def ensure_directory(root, label):
    with open_directory(root, label) as (_fd, path):
        return path


def _name(name):
    if not isinstance(name, str) or not SAFE_FILE.fullmatch(name) or name in ('.', '..'):
        raise ArtifactError('Invalid artifact filename')


def _write_all(fd, body):
    with os.fdopen(fd, 'wb') as out:
        out.write(body)
        out.flush()
        os.fsync(out.fileno())


def write_exclusive(root, label, name, body):
    """Create a new artifact atomically by basename; existing files never overwritten."""
    _name(name)
    if not isinstance(body, bytes) or len(body) > MAX_WRITE:
        raise ArtifactError('Invalid artifact size')
    with open_directory(root, label) as (dfd, path):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = None
        try:
            if dfd is not None:
                fd = os.open(name, flags, 0o600, dir_fd=dfd)
            else:
                _location(root, label)
                fd = os.open(path / name, flags, 0o600)
            _write_all(fd, body)
            fd = None
        except FileExistsError as exc:
            raise ArtifactError('Artifact filename already exists') from exc
        except OSError as exc:
            raise ArtifactError('Unable to write review artifact') from exc
        finally:
            if fd is not None:
                os.close(fd)
    return path / name


def append_log(root, name, body):
    """Append only to a regular, non-symlinked, non-hardlinked file inside logs/."""
    _name(name)
    if not isinstance(body, bytes) or len(body) > 64_000:
        raise ArtifactError('Invalid log entry size')
    with open_directory(root, 'logs') as (dfd, path):
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0)
        fd = None
        try:
            if dfd is not None:
                fd = os.open(name, flags, 0o600, dir_fd=dfd)
            else:
                _location(root, 'logs')
                if _reparse(path / name):
                    raise ArtifactError('Refusing redirected log file')
                fd = os.open(path / name, flags, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ArtifactError('Refusing nonregular or hardlinked log')
            _write_all(fd, body)
            fd = None
        except OSError as exc:
            raise ArtifactError('Unable to write audit log') from exc
        finally:
            if fd is not None:
                os.close(fd)
