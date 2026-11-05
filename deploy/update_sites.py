#!/usr/bin/env python3
"""Root-only Linux updater. No commands run on import; tests inject service runners."""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid

from configure_roles import capability, migrate
from git_history import history_paths


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]


def command(args, *, cwd=None, env=None, runner=subprocess.run, timeout=1800, log_output=True):
    logging.info('执行 %s', ' '.join(map(str, args)))
    try:
        result = runner(list(map(str, args)), cwd=cwd, env=env, check=True, timeout=timeout,
                        capture_output=True, text=True, encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as exc:
        if log_output:
            logging.error('%s\n%s', exc.stdout or '', exc.stderr or '')
        raise
    if result.stdout and log_output:
        logging.info('%s', result.stdout.rstrip())
    # Credential config contents are never passed to commands or logged.
    if result.stderr and log_output:
        logging.info('%s', result.stderr.rstrip())
    return result.stdout.strip()


def sqlite_snapshot(source, destination):
    """Read committed WAL content, never copy a live SQLite main file alone."""
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
    shutil.copystat(source, destination)
    if hasattr(os, 'chown'):
        source_stat = source.stat()
        os.chown(destination, source_stat.st_uid, source_stat.st_gid)


def preserve_ownership(source, destination):
    if hasattr(os, 'chown'):
        for entry in [source, *source.rglob('*')]:
            target = destination / entry.relative_to(source)
            info = entry.lstat()
            os.chown(target, info.st_uid, info.st_gid, follow_symlinks=False)


def pokilot_health():
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:3000/pokilot/api/auth/me', timeout=3) as response:
                if response.status != 200 or json.load(response).get('role') != 'guest':
                    raise ValueError('guest identity missing')
            with urllib.request.urlopen('http://127.0.0.1:3000/pokilot/db', timeout=3) as response:
                if response.status == 200:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


class PokilotUpdater:
    def __init__(self, root=Path('/opt/pokilot'), *, runner=subprocess.run, health=pokilot_health):
        self.root = Path(root).absolute()
        self.db = self.root / 'data/pokilot.db'
        self.runner, self.health = runner, health

    def run(self, args, **kwargs):
        return command(args, runner=self.runner, **kwargs)

    def git(self, *args, log_output=True):
        env = {**os.environ, 'GIT_TERMINAL_PROMPT':'0',
               'GIT_SSH_COMMAND':os.environ.get('GIT_SSH_COMMAND','ssh -o BatchMode=yes -o ConnectTimeout=15')}
        return self.run(['git','-C',str(self.root), *args], env=env, timeout=180, log_output=log_output)

    def service(self, action):
        self.run(['systemctl',action,'pokilot.service'], timeout=90)

    def preflight(self):
        if self.root.is_symlink() or self.root.resolve() != self.root or not (self.root / '.git').is_dir():
            raise RuntimeError('Pokilot 必须是独立真实 Git 工作目录，不能是链接')
        branch = self.git('branch','--show-current')
        if not branch:
            raise RuntimeError('Pokilot 当前处于游离 HEAD，请先恢复部署分支；未自动切换分支')
        remote = self.git('config','--default','','--get',f'branch.{branch}.remote',log_output=False)
        merge = self.git('config','--default','','--get',f'branch.{branch}.merge',log_output=False)
        if (remote or merge) and (remote != 'origin' or merge != f'refs/heads/{branch}'):
            raise RuntimeError(f'Pokilot 当前分支 {branch} 的上游必须为 origin/{branch}；未修改分支或上游配置')
        logging.info('Pokilot 保留部署分支 %s，更新目标 origin/%s',branch,branch)
        if self.git('status','--porcelain','--untracked-files=all'):
            raise RuntimeError('Pokilot 有本地改动，已停止更新')
        if self.git('ls-files','--','data/pokilot.db','data/pokilot.db-wal','data/pokilot.db-shm'):
            raise RuntimeError('Pokilot 线上数据库不能被 Git 跟踪')
        if not self.db.is_file() or self.db.resolve() != self.db:
            raise RuntimeError('Pokilot 数据库路径无效或是链接')
        config = self.run(['systemctl','show','pokilot.service', '--property=WorkingDirectory,Environment,User'], log_output=False)
        properties = dict(line.split('=', 1) for line in config.splitlines() if '=' in line)
        environment = dict(item.split('=', 1) for item in shlex.split(properties.get('Environment', '')) if '=' in item)
        if (properties.get('WorkingDirectory') != f'{self.root}/apps/web' or
                environment.get('POKILOT_DB') != str(self.db) or
                environment.get('NEXT_PUBLIC_BASE_PATH') != '/pokilot'):
            raise RuntimeError('Pokilot 服务工作目录、数据库或 /pokilot 子路径配置不匹配')
        with closing(sqlite3.connect(self.db.as_uri()+'?mode=ro', uri=True)) as connection:
            if connection.execute('pragma quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Pokilot 数据库完整性检查失败')
        return branch

    def backup(self, destination, old_head):
        # Full copy includes node_modules and .next: rollback needs no network/build.
        # Relative pnpm links remain relative to the identical restored directory.
        shutil.copytree(self.root, destination, symlinks=True)
        preserve_ownership(self.root, destination)
        os.chmod(destination, 0o700)
        sqlite_snapshot(self.db, destination / 'data/pokilot.db')
        for suffix in ('-wal','-shm'):
            (destination / ('data/pokilot.db'+suffix)).unlink(missing_ok=True)
        (destination / '.git/update-sites-head').write_text(old_head+'\n', encoding='utf-8')

    def update(self):
        branch = self.preflight()
        old_head = self.git('rev-parse','HEAD')
        # Fetch with service running; reject divergence before downtime.
        self.git('fetch','origin',branch)
        new_head = self.git('rev-parse','FETCH_HEAD')
        if old_head == new_head:
            logging.info('Pokilot 已是最新版本，跳过')
            return {'state':'unchanged', 'head':old_head, 'branch':branch}
        self.git('merge-base','--is-ancestor',old_head,new_head)
        database_paths=history_paths(self.git,old_head,new_head)
        if any(path in {'data/pokilot.db','data/pokilot.db-wal','data/pokilot.db-shm'} for path in database_paths) or self.git('ls-tree','-r','--name-only',new_head,'--','data/pokilot.db'):
            raise RuntimeError('远端版本跟踪了线上数据库，已停止更新')
        suffix = stamp()
        backup = self.root.parent / ('pokilot-backup-'+suffix)
        failed = self.root.parent / ('pokilot-failed-'+suffix)
        # All moves below use fixed sibling names, verified within the same parent.
        for target in (backup, failed):
            if target.parent.resolve() != self.root.parent.resolve() or target.exists():
                raise RuntimeError('备份目标路径不安全')
        original_mode = self.root.stat().st_mode & 0o7777
        self.service('stop')
        backed_up = False
        try:
            # Recheck after stop so an out-of-band edit never gets overwritten.
            if (self.git('status','--porcelain','--untracked-files=all') or
                    self.git('rev-parse','HEAD') != old_head or
                    self.git('branch','--show-current') != branch):
                raise RuntimeError('停服期间代码或分支发生变化，已停止更新')
            self.backup(backup, old_head)
            backed_up = True
            logging.info('Pokilot 完整回滚备份：%s', backup)
            self.git('merge','--ff-only',new_head)
            env = {**os.environ, 'POKILOT_DB':str(self.db), 'NEXT_PUBLIC_BASE_PATH':'/pokilot'}
            for args in (['pnpm','install','--frozen-lockfile'], ['pnpm','db:migrate'], ['pnpm','build']):
                self.run(args, cwd=self.root, env=env)
                if self.git('ls-files','--','data/pokilot.db','data/pokilot.db-wal','data/pokilot.db-shm'):
                    raise RuntimeError('构建步骤跟踪了线上数据库，已停止并恢复备份')
            self.service('restart')
            if not self.health():
                raise RuntimeError('Pokilot 健康检查失败')
            logging.info('Pokilot 更新成功；备份保留：%s', backup)
            return {'state':'deployed','head':self.git('rev-parse','HEAD'), 'branch':branch, 'backup':str(backup)}
        except Exception:
            if backed_up:
                self.service('stop')
                self.root.rename(failed)
                os.chmod(backup, original_mode)
                backup.rename(self.root)
                logging.error('Pokilot 已恢复旧代码和数据库；故障现场：%s', failed)
            self.service('start')
            raise


@contextmanager
def updater_lock(path=Path('/run/lock/update-sites.lock')):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('另一条 update-sites 正在运行，请等待完成') from exc
        yield


def snapshot_os(current, state_dir, destination, *, include_images=True):
    """Capture mutable data under sync_lock; callers may defer immutable images."""
    current=Path(current).resolve()
    if destination.parent == state_dir / 'update-backups':
        destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(destination.parent, 0o750)
        if hasattr(os, 'chown'):
            state_owner = state_dir.stat()
            os.chown(destination.parent, state_owner.st_uid, state_owner.st_gid)
    destination.mkdir(parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    for name in ('knowledge','knowledge-history','knowledge-sync','website-data'):
        source = current / name
        if source.exists():
            shutil.copytree(source, destination / name,
                            ignore=shutil.ignore_patterns('images') if name=='website-data' else None)
    for source in state_dir.iterdir():
        if source.name in ('sync.lock', 'proposals.sqlite3-wal', 'proposals.sqlite3-shm'):
            continue
        if source.name == 'proposals.sqlite3':
            sqlite_snapshot(source, destination / source.name)
        elif source.is_file():
            shutil.copy2(source, destination / source.name)
    (destination / 'release.txt').write_text(str(current.resolve())+'\n', encoding='utf-8')
    if include_images:snapshot_os_images(current,destination)


def snapshot_os_images(current, destination):
    """Published images are immutable within a release; no save lock is needed."""
    source=Path(current)/'website-data/images'
    if source.exists():shutil.copytree(source,Path(destination)/'website-data/images')


def retain_os_snapshot(latest):
    """Remove older update snapshots after all parts of the new one are copied."""
    directory=latest.parent.resolve()
    for path in directory.iterdir():
        if (path.name != latest.name
                and re.fullmatch(r'(?:release-)?\d{8}T\d{6}Z-[0-9a-f]{8}', path.name)
                and path.is_dir() and not path.is_symlink() and path.resolve().parent == directory):
            shutil.rmtree(path)


def wait_role_capability():
    for _ in range(30):
        try:
            result = capability()
            if any(key in result for key in ('account_role', 'allowed_roles')):
                return result
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('万象棋新版服务角色能力检查失败')


def update_os(*, runner=subprocess.run, auth=Path('/etc/os-tutorial/admins.json')):
    # systemctl start joins an already active oneshot job rather than killing it.
    # A second start after waiting performs the usual no-change check safely.
    deadline = time.monotonic() + 1900
    while True:
        active = command(['systemctl','show','os-tutorial-update.service','--property=ActiveState','--value'], runner=runner)
        if active not in ('activating', 'deactivating', 'active'):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('等待万象棋自动更新超时，未停止原任务')
        logging.info('等待正在执行的万象棋自动更新…')
        time.sleep(3)
    command(['systemctl','start','os-tutorial-update.service'], runner=runner, timeout=1900)
    # Run the helper from the activated release, never migrate before role support.
    changed = migrate(auth, wait_role_capability())
    if changed:
        command(['systemctl','restart','os-tutorial.service'], runner=runner, timeout=90)
        wait_role_capability()  # startup/endpoint failures propagate; do not continue Pokilot.
    logging.info('万象棋更新完成（无新提交时发布器自动跳过构建）')
    return {'state':'completed'}


def update_selected(os_tutorial, pokilot, os_update=update_os, pokilot_update=None):
    results = {}
    if os_tutorial:
        logging.info('开始更新万象棋')
        results['os-tutorial'] = os_update()
    if pokilot:
        logging.info('开始更新 Pokilot')
        results['pokilot'] = (pokilot_update or PokilotUpdater().update)()
    return results


def main():
    parser = argparse.ArgumentParser(description='一条命令更新万象棋和 Pokilot（服务器 root 执行）')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--os-tutorial', action='store_true', help='只更新万象棋')
    group.add_argument('--pokilot', action='store_true', help='只更新 Pokilot')
    args = parser.parse_args()
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        parser.error('请在服务器 root SSH 窗口执行，或使用 sudo update-sites')
    directory = Path('/var/log/update-sites')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    logfile = directory / (stamp()+'.log')
    handler = logging.FileHandler(logfile, encoding='utf-8')
    os.chmod(logfile, 0o600)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[handler, logging.StreamHandler(sys.stdout)])
    logging.info('本次更新日志：%s', logfile)
    try:
        with updater_lock():
            results = update_selected(not args.pokilot, not args.os_tutorial)
        logging.info('更新结束：%s', json.dumps(results, ensure_ascii=False))
        return 0
    except Exception as exc:
        logging.exception('更新失败，已停止后续站点：%s', exc)
        logging.error('请保留日志：%s', logfile)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
