"""Serialized, allowlisted website edits and non-destructive Git synchronization.

Call enqueue/record_save/retry while holding sync_lock. The lock lives outside releases.
Remote merges happen in disposable checkouts; serving code is never updated here.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import signal
import threading
import time
import uuid

_cancellation=ContextVar('website_sync_cancellation',default=None)


class SyncBusy(RuntimeError):
    pass


class SyncBlocked(RuntimeError):
    pass


class SyncCancelled(RuntimeError):
    pass


class StaleSync(SyncBlocked):
    pass


def _stop_child(process):
    if os.name=='nt':
        if process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
    else:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name!='nt':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:process.kill()
        process.communicate(timeout=2)


def run_process(args,*,timeout=180,**kwargs):
    event=_cancellation.get()
    env=kwargs.pop('env',None)
    kwargs['env']={**os.environ,**(env or {}),'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}
    if event is None:return subprocess.run(args,timeout=timeout,**kwargs)
    if event.is_set():raise SyncCancelled('同步已暂停，将在服务恢复后重试')
    kwargs.pop('capture_output',None)
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
    else:kwargs['start_new_session']=True
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs) as process:
        deadline=time.monotonic()+timeout
        try:
            while True:
                if event.is_set():raise SyncCancelled('同步已暂停，将在服务恢复后重试')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
                try:
                    stdout,stderr=process.communicate(timeout=min(.2,remaining))
                    return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
                except subprocess.TimeoutExpired:continue
        except BaseException:
            _stop_child(process)
            raise


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


@contextmanager
def wait_sync_lock(state_dir,timeout=300):
    """Publisher waits for a running save/sync without cancelling that job."""
    deadline=time.monotonic()+timeout
    acquired=False
    while True:
        try:
            with sync_lock(state_dir):
                acquired=True
                yield
                return
        except SyncBusy:
            if acquired:raise
            if time.monotonic()>=deadline:raise SyncBusy('等待正在执行的同步超时；任务仍保留，请稍后重试')
            time.sleep(min(.25,max(0,deadline-time.monotonic())))


def git(root, *args, check=True):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0',
           'GIT_SSH_COMMAND': os.environ.get('GIT_SSH_COMMAND', 'ssh -o BatchMode=yes -o ConnectTimeout=15')}
    result = run_process(['git', '-C', str(root), *args], capture_output=True,
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

    def _read_state(self):
        try:
            value = json.loads((self.state_dir / 'sync.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            value = {'state': 'synced'}
        return value

    def status(self,light=False):
        value=self._read_state()
        # A freshly activated published checkout satisfies the old release's state.
        if value.get('state') == 'pending-deploy' and value.get('published_head') == self._head():
            value = {'state': 'synced', 'published_head': value['published_head']}
        messages = {
            'synced': '已同步',
            'pending': '正文已保存，等待同步',
            'conflict': '修改已保存在服务器，同步需要管理员处理；暂时无法继续编辑。',
            'pending-deploy': '修改已同步，等待发布新版本；暂时无法继续编辑。',
        }
        phases={'queued':'正文已保存，等待同步','validating':'正在校验','committing':'正在保存同步版本',
                'fetching':'正在检查远端','merging':'正在合并远端','pushing':'正在推送',
                'waiting-retry':'同步失败，正文已保存，等待重试'}
        message=phases.get(value.get('phase')) if value.get('state')=='pending' else None
        result={**value,'message':message or messages.get(value.get('state'),'同步状态需要管理员检查。')}
        return result if light else {**result,'head':self._head(),'dirty':self._changed()}

    def _assert_active(self):
        if self.root.parent.name=='releases':
            current=self.root.parent.parent/'current'
            if current.exists() and current.resolve()!=self.root:
                raise StaleSync('当前同步任务属于旧发布目录，已停止')

    def _state(self, state, error=None, **extra):
        self._assert_active()
        previous=self._read_state()
        retained={k:previous[k] for k in ('job_id','attempts','head') if k in previous}
        value = {**retained,'state': state,'source_root':str(self.root),
                 'phase':'idle' if state=='synced' else state,
                 'next_retry_at':None,'updated_at': datetime.now(timezone.utc).isoformat(), **extra}
        if error:
            value['error'] = str(error)[:1500]
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / 'sync.json'
        temporary = path.with_name('sync-'+uuid.uuid4().hex+'.tmp')
        try:
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w',encoding='utf-8') as handle:
                handle.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
                handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,path)
            if os.name!='nt':
                directory=os.open(self.state_dir,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
        finally:temporary.unlink(missing_ok=True)
        return self.status(light=True)

    def enqueue(self,force=False):
        """Caller holds sync_lock and has already durably saved the formal write."""
        self._assert_active()
        value=self.status(light=True)
        if value['state'] in ('pending','conflict') and value.get('source_root',str(self.root))!=str(self.root):
            raise StaleSync('待同步任务属于其他发布目录，请先在原版本恢复')
        if value['state']=='pending' and not force:return value
        if value['state']=='pending-deploy':raise SyncBlocked('修改已同步，等待发布新版本')
        return self._state('pending',job_id=uuid.uuid4().hex,phase='queued',attempts=0)

    def _phase(self,phase):
        return self._state('pending',phase=phase)

    def _validate(self, root):
        result = run_process([sys.executable,str(root/'frontend/website_data.py'),
                              'sync-check','--root',str(root)],capture_output=True,
                             encoding='utf-8',errors='replace',timeout=300)
        if result.returncode:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or 'Knowledge validation failed')

    def record_save(self):
        if self.status()['state'] != 'synced':
            raise SyncBlocked('Previous save must synchronize or deploy before further edits')
        self.retry()
        return self.status()

    def retry(self):
        """Retry saved edits; caller holds sync_lock. Never modifies serving code."""
        self._assert_active()
        state=self._read_state()
        if state.get('state') in ('pending','conflict') and state.get('source_root',str(self.root))!=str(self.root):
            raise StaleSync('待同步任务属于其他发布目录，请先在原版本恢复')
        if state.get('state')=='pending-deploy':
            return self.status()
        try:
            proposal_db=self.state_dir/'proposals.sqlite3'
            if proposal_db.with_name(proposal_db.name+'.approval.json').exists():
                from proposals import ProposalStore
                ProposalStore(self.root,proposal_db).recover()
            paths_before=self._changed()
            journal=self.root/'raw/knowledge/pending-json-save.json'
            if (state.get('state')=='synced' and state.get('published_head')==self._head()
                    and not any(allowed_path(path) for path in paths_before) and not journal.exists()):
                return self.status()
            # Durable journals are not tracked. Replay them before selecting the
            # files to commit, otherwise a valid overlay can hide missing disk writes.
            self._phase('validating')
            self._validate(self.root)
            paths = [p for p in self._changed() if allowed_path(p)]
            if paths:
                # --only ensures unrelated staged changes cannot enter this commit.
                self._phase('committing')
                git(self.root, 'add', '--', *paths)
                git(self.root, 'commit', '--only', '-m', 'website: save knowledge edits', '--', *paths)
        except SyncCancelled:
            return self._state('pending',phase='queued')
        except Exception as exc:
            return self._state('conflict', exc)
        local_head = self._head()
        try:
            self._phase('fetching')
            upstream = git(self.root, 'remote', 'get-url', 'origin').stdout.strip()
            git(self.root,'fetch','origin',self.branch)
            remote_head=git(self.root,'rev-parse','FETCH_HEAD').stdout.strip()
            if git(self.root,'merge-base','--is-ancestor',remote_head,local_head,check=False).returncode==0:
                self._phase('pushing')
                git(self.root,'push','origin',f'{local_head}:refs/heads/{self.branch}')
                return self._state('synced',published_head=local_head,head=local_head)
            with tempfile.TemporaryDirectory(prefix='website-sync-') as directory:
                candidate = Path(directory) / 'checkout'
                git(self.root, 'clone', '--config','core.autocrlf=false','--no-hardlinks', '--no-checkout', str(self.root), str(candidate))
                git(candidate, 'checkout', '-B', self.branch, local_head)
                git(candidate, 'remote', 'set-url', 'origin', upstream)
                # Identity is explicit repo/global configuration, never a tracked secret.
                for key in ('user.name', 'user.email'):
                    configured = git(self.root, 'config', '--get', key).stdout.strip()
                    git(candidate, 'config', key, configured)
                git(candidate, 'fetch', 'origin', self.branch)
                # Fetch the same branch but keep the originally verified snapshot.
                self._phase('merging')
                merge = git(candidate, 'merge', '--no-edit', remote_head, check=False)
                if merge.returncode:
                    return self._state('conflict', merge.stderr or merge.stdout)
                self._phase('validating')
                self._validate(candidate)
                published = git(candidate, 'rev-parse', 'HEAD').stdout.strip()
                self._phase('pushing')
                git(candidate, 'push', 'origin', f'{published}:refs/heads/{self.branch}')
            if published != local_head:
                return self._state('pending-deploy', published_head=published)
            return self._state('synced', published_head=published)
        except SyncCancelled:
            return self._state('pending',phase='queued')
        except StaleSync:
            raise
        except ValueError as exc:
            return self._state('conflict', exc)
        except Exception as exc:
            return self._state('pending', exc)


class SyncWorker:
    """One per public process. Job execution is serialized across processes too."""
    def __init__(self,manager,*,clock=time.time):
        self.manager=manager
        self.clock=clock
        self.stop_event=threading.Event()
        self.wakeup=threading.Event()
        self.thread=None
        self.initialized=False

    def start(self):
        if self.thread is not None:return self
        self.thread=threading.Thread(target=self._run,name='website-git-sync',daemon=True)
        self.thread.start()
        return self

    def wake(self):self.wakeup.set()

    def close(self):
        self.stop_event.set();self.wakeup.set()
        if self.thread is not None:self.thread.join(5)

    def _reconcile(self):
        manager=self.manager
        manager._assert_active()
        value=manager.status(light=True)
        if value.get('state') in ('pending','conflict') and value.get('source_root',str(manager.root))!=str(manager.root):
            raise StaleSync('待同步任务属于其他发布目录，需在原版本恢复')
        receipt=manager.state_dir/'proposals.sqlite3.approval.json'
        if receipt.exists():
            from proposals import ProposalStore
            ProposalStore(manager.root,manager.state_dir/'proposals.sqlite3').recover()
        journal=manager.root/'raw/knowledge/pending-json-save.json'
        if journal.exists():
            from website_data import recover
            recover(manager.root)
        dirty=any(allowed_path(path) for path in manager._changed())
        if dirty and value['state']=='synced':manager.enqueue()
        self.initialized=True

    def step(self):
        token=_cancellation.set(self.stop_event)
        try:return self._step()
        except SyncCancelled:return False
        finally:_cancellation.reset(token)

    def _step(self):
        if self.stop_event.is_set():return False
        manager=self.manager
        value=manager.status(light=True)
        if self.initialized and (value['state']!='pending' or (value.get('next_retry_at') or 0)>self.clock()):
            return False
        try:
            with sync_lock(manager.state_dir):
                if not self.initialized:self._reconcile()
                manager._assert_active()
                value=manager.status(light=True)
                if value['state']!='pending' or (value.get('next_retry_at') or 0)>self.clock():return False
                if value.get('source_root',str(manager.root))!=str(manager.root):
                    raise StaleSync('任务属于其他发布目录')
                token=_cancellation.set(self.stop_event)
                try:result=manager.retry()
                finally:_cancellation.reset(token)
                if result['state']=='pending' and not self.stop_event.is_set():
                    attempts=value.get('attempts',0)+1
                    delay=(30,60,120,300)[min(attempts-1,3)]
                    manager._state('pending',result.get('error'),phase='waiting-retry',attempts=attempts,
                                   next_retry_at=self.clock()+delay)
                return True
        except SyncBusy:return False
        except StaleSync:
            self.stop_event.set()
            return False

    def _run(self):
        while not self.stop_event.is_set():
            try:self.step()
            except Exception:
                logging.exception('后台同步暂不可用；已保存正文与任务保留')
            self.wakeup.wait(1)
            self.wakeup.clear()


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

