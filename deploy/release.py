#!/usr/bin/env python3
"""Build independent releases and atomically switch the Linux public service.

No serving checkout reset, force push, automatic cleanup, or active-tree merge.
Run as the service user (or a shared group) with narrowly scoped restart rights.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))
from website_sync import SyncManager, git, sync_lock


class StaleRelease(RuntimeError):
    pass


class ReleaseManager:
    sync_class = SyncManager

    def __init__(self, base_dir=Path('/opt/os-tutorial'), state_dir=Path('/var/lib/os-tutorial'),
                 branch='master', repo=None, service='os-tutorial', rebuild=False):
        self.base = Path(base_dir).resolve()
        self.releases = self.base / 'releases'
        self.current = self.base / 'current'
        self.state_dir = Path(state_dir).resolve()
        self.branch = branch
        self.repo = repo
        self.service = service
        self.rebuild = rebuild

    def snapshot(self):
        if not self.current.exists():
            return None
        root = self.current.resolve()
        sync = self.sync_class(root, self.state_dir, self.branch)
        return {'root': str(root), **sync.status()}

    def assert_unchanged(self, snapshot):
        now = self.snapshot()
        if now != snapshot or (now and (now['dirty'] or now['state'] not in ('synced', 'pending-deploy'))):
            raise StaleRelease('Active release changed or has pending edits; build retained, activation skipped')

    def remote_head(self, root):
        result = git(root, 'ls-remote', '--exit-code', 'origin', f'refs/heads/{self.branch}')
        return result.stdout.split()[0]

    def build(self, candidate):
        # Ubuntu 24.04 /usr/bin/python3 is Python 3.12; all public runtime code is stdlib.
        self.sync_class(candidate, self.state_dir, self.branch)._validate(candidate)
        for args in (['npm', 'ci'], ['npm', 'run', 'build', '--', '--base', '/os-tutorial/']):
            subprocess.run(args, cwd=candidate / 'frontend', check=True, timeout=900)

    def restart(self):
        subprocess.run(['sudo', '-n', '/usr/bin/systemctl', 'restart', self.service + '.service'], check=True, timeout=60)

    def healthy(self):
        for _ in range(30):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8765/os-tutorial/api/health', timeout=2) as response:
                    if response.status == 200 and json.loads(response.read()).get('ok') is True:
                        return True
            except (OSError, ValueError):
                pass
            time.sleep(1)
        return False

    def _switch(self, destination):
        temporary = self.base / f'.current-{uuid.uuid4().hex}'
        temporary.symlink_to(destination, target_is_directory=True)
        try:
            os.replace(temporary, self.current)
        finally:
            temporary.unlink(missing_ok=True)

    def activate(self, candidate, snapshot):
        # Caller holds the external lock through health/rollback. Descriptors are
        # non-inheritable, so the restarted service can later acquire its own lock.
        self.assert_unchanged(snapshot)
        previous = self.current.resolve() if self.current.exists() else None
        self._switch(candidate)
        try:
            self.restart()
            if not self.healthy():
                raise RuntimeError('New release health check failed')
        except Exception:
            if previous:
                self._switch(previous)
                self.restart()
            else:
                self.current.unlink(missing_ok=True)
                subprocess.run(['sudo', '-n', '/usr/bin/systemctl', 'stop', self.service + '.service'], check=False, timeout=60)
            raise

    def update(self):
        self.releases.mkdir(parents=True, exist_ok=True)
        with sync_lock(self.state_dir):
            snapshot = self.snapshot()
            if snapshot:
                active = Path(snapshot['root'])
                sync = self.sync_class(active, self.state_dir, self.branch)
                # Always retry before reading/building a newer release.
                status = sync.retry()
                if status['state'] not in ('synced', 'pending-deploy'):
                    raise StaleRelease(f"Synchronization requires attention: {status['state']}")
                snapshot = self.snapshot()
                if snapshot['dirty']:
                    raise StaleRelease('Active checkout has unrelated edits; leaving it untouched')
                upstream = git(active, 'remote', 'get-url', 'origin').stdout.strip()
                remote_head = self.remote_head(active)
                if remote_head == snapshot['head'] and not self.rebuild:
                    return {'state': 'unchanged', 'head': remote_head}
            else:
                if not self.repo:
                    raise ValueError('--repo SSH_URL is required for the first release')
                upstream = self.repo
                remote_head = None
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        candidate = self.releases / f'{stamp}-{uuid.uuid4().hex[:8]}'
        git(self.base, 'clone', '--no-hardlinks', '--single-branch', '--branch', self.branch,
            upstream, str(candidate))
        head = git(candidate, 'rev-parse', 'HEAD').stdout.strip()
        if remote_head and head != remote_head:
            raise StaleRelease('Remote advanced during clone; retry next update')
        if snapshot:
            for key in ('user.name', 'user.email'):
                value = git(Path(snapshot['root']), 'config', '--get', key).stdout.strip()
                git(candidate, 'config', key, value)
        self.build(candidate)
        with sync_lock(self.state_dir):
            self.assert_unchanged(snapshot)
            if self.remote_head(candidate) != head:
                raise StaleRelease('Remote advanced during build; activation skipped')
            self.activate(candidate, snapshot)
            self.sync_class(candidate, self.state_dir, self.branch)._state('synced', published_head=head)
        return {'state': 'deployed', 'head': head, 'release': str(candidate)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dir', type=Path, default=Path('/opt/os-tutorial'))
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/os-tutorial'))
    parser.add_argument('--branch', default='master')
    parser.add_argument('--repo', help='SSH origin for initial installation only')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild even when active HEAD equals the remote (manual recovery)')
    args = parser.parse_args()
    try:
        print(json.dumps(ReleaseManager(args.base_dir, args.state_dir, args.branch, args.repo, rebuild=args.rebuild).update()))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
