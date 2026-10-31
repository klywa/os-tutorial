"""Serialized, allowlisted website edits and non-destructive Git synchronization.

Call record_save/retry while holding sync_lock. The lock lives outside releases.
Remote merges happen in disposable checkouts; serving code is never updated here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class SyncBusy(RuntimeError):
    pass


class SyncBlocked(RuntimeError):
    pass


@contextmanager
def sync_lock(state_dir):
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'sync.lock').open('a+b') as handle:
        handle.seek(0)
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SyncBusy('Another save or deployment is in progress') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def git(root, *args, check=True):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0',
           'GIT_SSH_COMMAND': os.environ.get('GIT_SSH_COMMAND', 'ssh -o BatchMode=yes -o ConnectTimeout=15')}
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            encoding='utf-8', errors='replace', env=env, timeout=180)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Git operation failed')
    return result


def allowed_path(path):
    return (path in {'knowledge/index.meta.json', 'website-data/usage-matches.json'}
            or bool(re.fullmatch(r'knowledge/(players|lineups|other)/[^/]+\.json', path)))


class SyncManager:
    def __init__(self, root: Path, state_dir: Path, branch='master'):
        self.root = Path(root).resolve()
        self.state_dir = Path(state_dir).resolve()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', branch) or '..' in branch:
            raise ValueError('Invalid sync branch')
        self.branch = branch

    def _head(self):
        return git(self.root, 'rev-parse', 'HEAD').stdout.strip()

    def _changed(self):
        tracked = git(self.root, 'diff', 'HEAD', '--name-only', '-z').stdout
        untracked = git(self.root, 'ls-files', '--others', '--exclude-standard', '-z').stdout
        return sorted({p for p in (tracked + untracked).split('\0') if p})

    def status(self):
        try:
            value = json.loads((self.state_dir / 'sync.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            value = {'state': 'synced'}
        # A freshly activated published checkout satisfies the old release's state.
        if value.get('state') == 'pending-deploy' and value.get('published_head') == self._head():
            value = {'state': 'synced', 'published_head': value['published_head']}
        messages = {
            'synced': '修改已同步。',
            'pending': '修改已保存在服务器，等待同步；请稍后重试。',
            'conflict': '修改已保存在服务器，同步需要管理员处理；暂时无法继续编辑。',
            'pending-deploy': '修改已同步，等待发布新版本；暂时无法继续编辑。',
        }
        return {**value, 'message': messages.get(value.get('state'), '同步状态需要管理员检查。'),
                'head': self._head(), 'dirty': self._changed()}

    def _state(self, state, error=None, **extra):
        value = {'state': state, 'updated_at': datetime.now(timezone.utc).isoformat(), **extra}
        if error:
            value['error'] = str(error)[:1500]
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / 'sync.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        os.replace(temporary, path)
        return self.status()

    def _validate(self, root):
        for command in ('recover', 'prepare', 'validate'):
            result = subprocess.run([sys.executable, str(root / 'frontend/website_data.py'),
                                     command, '--root', str(root)], capture_output=True,
                                    encoding='utf-8', errors='replace', timeout=300)
            if result.returncode:
                raise ValueError(result.stderr.strip() or result.stdout.strip() or 'Knowledge validation failed')

    def record_save(self):
        if self.status()['state'] != 'synced':
            raise SyncBlocked('Previous save must synchronize or deploy before further edits')
        return self.retry()

    def retry(self):
        """Retry saved edits; caller holds sync_lock. Never modifies serving code."""
        try:
            # Durable journals are not tracked. Replay them before selecting the
            # files to commit, otherwise a valid overlay can hide missing disk writes.
            self._validate(self.root)
            paths = [p for p in self._changed() if allowed_path(p)]
            if paths:
                # --only ensures unrelated staged changes cannot enter this commit.
                git(self.root, 'add', '--', *paths)
                git(self.root, 'commit', '--only', '-m', 'website: save knowledge edits', '--', *paths)
        except Exception as exc:
            return self._state('conflict', exc)
        local_head = self._head()
        try:
            upstream = git(self.root, 'remote', 'get-url', 'origin').stdout.strip()
            with tempfile.TemporaryDirectory(prefix='website-sync-') as directory:
                candidate = Path(directory) / 'checkout'
                git(self.root, 'clone', '--no-hardlinks', '--no-checkout', str(self.root), str(candidate))
                git(candidate, 'checkout', '-B', self.branch, local_head)
                git(candidate, 'remote', 'set-url', 'origin', upstream)
                # Identity is explicit repo/global configuration, never a tracked secret.
                for key in ('user.name', 'user.email'):
                    configured = git(self.root, 'config', '--get', key).stdout.strip()
                    git(candidate, 'config', key, configured)
                git(candidate, 'fetch', 'origin', self.branch)
                remote_head = git(candidate, 'rev-parse', 'FETCH_HEAD').stdout.strip()
                merge = git(candidate, 'merge', '--no-edit', remote_head, check=False)
                if merge.returncode:
                    return self._state('conflict', merge.stderr or merge.stdout)
                self._validate(candidate)
                published = git(candidate, 'rev-parse', 'HEAD').stdout.strip()
                git(candidate, 'push', 'origin', f'HEAD:refs/heads/{self.branch}')
            if published != local_head:
                return self._state('pending-deploy', published_head=published)
            return self._state('synced', published_head=published)
        except ValueError as exc:
            return self._state('conflict', exc)
        except Exception as exc:
            return self._state('pending', exc)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/os-tutorial'))
    parser.add_argument('--branch', default='master')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    manager = SyncManager(args.root, args.state_dir, args.branch)
    if args.status:
        result = manager.status()
    else:
        with sync_lock(args.state_dir):
            result = manager.retry()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['state'] in ('synced', 'pending-deploy') else 1


if __name__ == '__main__':
    raise SystemExit(main())

