#!/usr/bin/env python3
"""Explicit local publish/pull workflow; never force-push or kill arbitrary processes."""
import argparse
from contextlib import contextmanager
from datetime import datetime
from html.parser import HTMLParser
from http.client import HTTPException
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'frontend'))
from website_sync import SyncBusy, sync_lock
from git_history import history_paths
from knowledge_git import merge_branches


def child_environment(env=None):
    return {**os.environ, **(env or {}), 'PYTHONUTF8':'1', 'PYTHONIOENCODING':'utf-8'}


def allowed_local_path(path):
    parts = Path(path).parts
    if not parts or any(part in {'..','.git','raw','personal','proposal','proposals','node_modules','dist',
                                 '__pycache__','.test-tmp','coverage','.vite'} for part in parts):
        return False
    basename = parts[-1].lower()
    if (basename.startswith('.env') or basename in {'admins.json','auth.json','credentials.json','id_rsa','id_ed25519'} or
            basename.endswith(('.sqlite3','.sqlite','.db','.pem','.key','.log','.pyc','.tsbuildinfo'))):
        return False
    if path in {'.gitignore','.gitattributes','README.md','start.ps1','start.zsh','publish-local.ps1','pull-local.ps1'}:
        return True
    if path == '.github/workflows/deploy-os-tutorial.yml':
        return True
    if parts[0] == 'knowledge':
        return path == 'knowledge/index.meta.json' or (len(parts)==3 and parts[1] in {'players','lineups','other'} and basename.endswith('.json'))
    if parts[0] in {'knowledge-history','knowledge-sync','templates'}:
        from website_sync import allowed_path
        return allowed_path(path)
    if parts[0] == 'website-data':
        return basename.endswith(('.json','.img'))
    if parts[0] in {'frontend','deploy','docs'} or path.startswith('.codex/skills/wanxiangqi-knowledge/'):
        return basename.endswith(('.py','.ts','.tsx','.js','.cjs','.mjs','.jsx','.json','.css','.html','.md','.txt','.ps1','.sh','.zsh',
                                  '.yml','.yaml','.toml','.service','.timer','.sudoers','.fragment'))
    return False


class ForeignService(RuntimeError):
    """A responding endpoint identifies a different workspace."""


class ServiceNotReady(RuntimeError):
    """The listener has not yet provided a usable status endpoint."""


def local_manager(root):
    """Optional on older release clones and isolated legacy test fixtures."""
    if not (Path(root)/'deploy/local_supervisor.py').is_file():return None
    import importlib.util
    specification=importlib.util.spec_from_file_location('wxq_local_supervisor',Path(root)/'deploy/local_supervisor.py')
    module=importlib.util.module_from_spec(specification);specification.loader.exec_module(module)
    return module if module.status(root)['available'] else None


class FrontendAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets=[]

    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag=='script' and attrs.get('src'):
            self.assets.append((attrs['src'],'js'))
        elif tag=='link' and 'stylesheet' in attrs.get('rel','').split() and attrs.get('href'):
            self.assets.append((attrs['href'],'css'))


class LocalService:
    stop_endpoint='/api/local-service/stop'
    def __init__(self, root, port=8765, *, stop_timeout=600, clock=time.monotonic, sleep=time.sleep):
        self.root, self.port = Path(root).resolve(), port
        self.url = f'http://127.0.0.1:{port}'
        self.stop_timeout, self.clock, self.sleep = stop_timeout, clock, sleep
        self.stopping = False
        self.start_timeout = 120
        self.stable_time = 5
        self.retries = 3
        self.process = None
        self.logfile = None

    def occupied(self):
        with socket.socket() as connection:
            connection.settimeout(0.4)
            return connection.connect_ex(('127.0.0.1',self.port)) == 0

    def running(self):
        try:
            with urllib.request.urlopen(self.url+'/api/local-service/status', timeout=3) as response:
                status=json.load(response)
        except (urllib.error.URLError, OSError) as exc:
            if not self.occupied():
                return False
            raise ServiceNotReady('端口已有服务但不支持安全停止；请先在原窗口 Ctrl+C，升级一次后重试。不自动杀进程。') from exc
        except (ValueError, TypeError) as exc:
            raise ForeignService('本地服务身份响应无效，未停止任何服务') from exc
        if (not isinstance(status,dict) or status.get('mode')!='local' or status.get('port')!=self.port or
                not isinstance(status.get('root'),str) or
                os.path.normcase(str(Path(status['root']).resolve()))!=os.path.normcase(str(self.root))):
            raise ForeignService('端口属于其他项目或公网服务，未停止任何服务')
        return True

    def healthy(self):
        if not self.running():
            return False
        with urllib.request.urlopen(self.url+'/api/auth/me',timeout=3) as response:
            return json.load(response).get('mode')=='local'

    def assets_healthy(self):
        with urllib.request.urlopen(self.url+'/',timeout=3) as response:
            if response.status!=200 or 'text/html' not in response.headers.get_content_type():
                return False
            page=response.read().decode('utf-8')
        parser=FrontendAssets();parser.feed(page)
        local=[]
        for source,kind in parser.assets:
            url=urljoin(self.url+'/',source)
            if urlsplit(url).netloc==urlsplit(self.url).netloc:
                local.append((url,kind))
        if not any(kind=='js' for _,kind in local):
            return False
        for url,kind in local:
            with urllib.request.urlopen(url,timeout=3) as response:
                mime=response.headers.get_content_type()
                if response.status!=200 or not response.read():
                    return False
                if kind=='js' and mime not in {'text/javascript','application/javascript','application/x-javascript'}:
                    return False
                if kind=='css' and mime!='text/css':
                    return False
        return True

    def stop(self):
        manager=local_manager(self.root) if self.port in (8765,5173) else None
        if manager:
            self.stopping=True
            manager.stop(self.root,('frontend' if isinstance(self,LocalFrontend) else 'backend',),timeout=self.stop_timeout)
            self.stopping=False
            return
        if not self.running():return
        request=urllib.request.Request(self.url+self.stop_endpoint, data=b'{}', method='POST',
            headers={'Origin':self.url,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=5) as response:
            if response.status!=202:
                raise RuntimeError('本地服务未确认安全停止')
        self.stopping = True
        self.wait_stopped()

    def wait_stopped(self):
        deadline = self.clock() + self.stop_timeout
        next_progress = self.clock()
        while self.occupied() or (self.process is not None and self.process.poll() is None):
            now = self.clock()
            if now >= deadline:
                raise RuntimeError('等待本地服务退出超时；未拉取覆盖文件；原服务仍在安全关闭，不会强制杀进程')
            if now >= next_progress:
                logging.info('等待本项目后台任务安全结束并关闭服务…（最多 %s 秒）', self.stop_timeout)
                next_progress = now + 15
            self.sleep(min(0.5, deadline-now))
        self.stopping = False
        logging.info('本项目本地服务已停止')

    def command(self):
        return [sys.executable,str(self.root/'frontend/server.py'),'--root',str(self.root),'--port',str(self.port)],self.root

    def launch(self):
        directory=self.root/'raw/local-sync'; directory.mkdir(parents=True,exist_ok=True)
        logfile=directory/(f'server-{self.port}-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.log')
        command,cwd=self.command()
        options={'cwd':cwd,'stdin':subprocess.DEVNULL,'stderr':subprocess.STDOUT,
                 'env':child_environment()}
        if os.name=='nt':
            # Detaching the console alone still inherits a kill-on-close job.
            # Do not silently fall back to a child that dies with its publisher.
            options['creationflags']=subprocess.DETACHED_PROCESS | subprocess.CREATE_BREAKAWAY_FROM_JOB
        else:
            options['start_new_session']=True
        with logfile.open('ab') as output:
            output.write(f'[launcher] parent_pid={os.getpid()} executable={sys.executable}\n'.encode('utf-8'))
            output.flush()
            try:
                process=subprocess.Popen(command,stdout=output,**options)
            except OSError as exc:
                raise RuntimeError(f'无法独立启动本地服务：{self.url} 父PID={os.getpid()} 日志：{logfile}；{exc}') from exc
        self.process=process
        self.logfile=logfile
        logging.info('启动本地服务：%s PID=%s 父PID=%s 日志：%s',self.url,process.pid,os.getpid(),logfile)
        # Reap the process while the publisher lives; the daemon never keeps
        # the publisher alive and is not a service supervisor.
        def record_exit():
            code=process.wait()
            with logfile.open('ab') as output:
                output.write(f'[launcher] pid={process.pid} exit_code={code}\n'.encode('utf-8'))
        threading.Thread(target=record_exit,daemon=True,name='local-service-exit').start()
        return process,logfile

    def restart(self):
        manager=local_manager(self.root) if self.port in (8765,5173) else None
        if manager:
            if self.stopping:self.wait_stopped()
            name='frontend' if isinstance(self,LocalFrontend) else 'backend'
            manager.resume(self.root,(name,));manager.wait_ready(self.root,(name,),timeout=self.start_timeout)
            if not self.healthy():raise RuntimeError('本地管理器启动后健康检查失败')
            return
        if self.stopping:
            self.wait_stopped()
        existing=self.running()  # Foreign services must fail before launching.
        process=self.process if self.process is not None and self.process.poll() is None else None
        logfile=self.logfile;last_error='服务尚未就绪'
        for attempt in range(self.retries+1):
            if not existing and process is None:
                try:
                    process,logfile=self.launch()
                except OSError as exc:
                    raise RuntimeError(f'无法独立启动本地服务：{self.url} 父PID={os.getpid()}；{exc}') from exc
            deadline=self.clock()+self.start_timeout
            stable_since=None
            while self.clock()<deadline:
                if process is not None and process.poll() is not None:
                    last_error=f'PID={process.pid} exit_code={process.returncode}'
                    logging.error('本地服务启动退出：%s 日志：%s',last_error,logfile)
                    break
                try:
                    ready=self.healthy()
                except ForeignService:
                    raise
                except (ServiceNotReady,OSError,ValueError,HTTPException) as exc:
                    ready=False;last_error=str(exc)
                if ready:
                    if stable_since is None:stable_since=self.clock()
                    if self.clock()-stable_since>=self.stable_time and self.clock()<deadline:
                        if process is not None and process.poll() is not None:
                            continue
                        logging.info('本地服务和前端已稳定恢复：%s PID=%s 日志：%s',
                                     self.url,process.pid if process else 'existing',logfile)
                        return
                else:
                    stable_since=None
                self.sleep(min(.25,max(0,deadline-self.clock())))
            else:
                raise RuntimeError(f'等待重启健康检查超时，未重复启动或强制杀进程：{self.url} '
                                   f'PID={process.pid if process else "existing"} 日志：{logfile}；{last_error}')
            if attempt<self.retries:
                # Only a confirmed dead instance is eligible for another launch.
                if self.running():
                    existing=True;process=None
                else:
                    existing=False;process=None
                self.sleep(.25)
        raise RuntimeError(f'本地服务重启失败（已重试 {self.retries} 次）：{self.url} {last_error} 日志：{logfile}')


class LocalFrontend(LocalService):
    control='/__wxq_local_frontend'
    stop_endpoint=control+'/stop'

    def __init__(self, root):
        super().__init__(root,5173)

    def command(self):
        node=shutil.which('node')
        frontend=self.root/'frontend'
        vite=frontend/'node_modules/vite/bin/vite.js'
        if not node or not vite.is_file():
            raise RuntimeError('缺少 Node.js 或 Vite，请先安装前端依赖')
        return [node,str(vite)],frontend

    def running(self):
        try:
            with urllib.request.urlopen(self.url+self.control,timeout=3) as response:
                status=json.load(response)
        except (OSError,ValueError):
            if not self.occupied():
                return False
            raise ForeignService('5173 已被占用，未识别到本项目的 Vite 前端；原进程保留') from None
        if (not isinstance(status,dict) or not isinstance(status.get('root'),str)
                or Path(status['root']).resolve()!=self.root/'frontend'
                or status.get('mode')!='local' or status.get('port')!=self.port):
            raise ForeignService('5173 已被其他项目占用；原进程保留')
        return True

    def healthy(self):
        if not self.running() or not self.assets_healthy():
            return False
        for path,key,expected in (('/api/auth/me','mode','local'),('/api/notes/catalog','ready',True)):
            with urllib.request.urlopen(self.url+path,timeout=8) as response:
                if json.load(response).get(key)!=expected:
                    return False
        return True

    def refresh(self):
        request=urllib.request.Request(self.url+self.control,method='POST',data=b'',headers={'X-WXQ-Refresh':'1'})
        with urllib.request.urlopen(request,timeout=3) as response:
            if response.status!=204:
                raise RuntimeError('5173 未确认刷新请求')


def ensure_local_frontend(root,backend,*,refresh=True):
    frontend=LocalFrontend(root)
    if not backend.healthy():
        backend.restart()
    try:
        ready=frontend.healthy()
    except (OSError,ValueError,HTTPException):
        ready=False
    if not ready:
        frontend.restart()
    if refresh:
        frontend.refresh()


def run_local_sync(manager,action):
    original=None
    supervisor=local_manager(manager.root) if isinstance(getattr(manager,'service',None),LocalService) else None
    desired=supervisor.status(manager.root)['services'] if supervisor else None
    restore=tuple(name for name in ('backend','frontend') if desired and desired[name]['desired']=='running')
    try:
        result=getattr(manager,action)()
        logging.info('Git 同步结果：%s',json.dumps(result,ensure_ascii=False))
        return result
    except Exception as exc:
        original=exc
        raise
    finally:
        try:
            if not supervisor or len(restore)==2:
                ensure_local_frontend(manager.root,manager.service,refresh=original is None)
                logging.info('本地前端验收通过：http://127.0.0.1:5173/')
            elif restore:
                # Preserve each service's explicit prior stop independently.
                # A running Vite can serve its assets while backend is paused;
                # its proxy APIs are intentionally unavailable in that state.
                supervisor.resume(manager.root,restore)
                supervisor.wait_ready(manager.root,restore)
                if 'backend' in restore and not manager.service.healthy():
                    raise RuntimeError('本地后端恢复后健康检查失败')
                if 'frontend' in restore:
                    frontend=LocalFrontend(manager.root)
                    if not frontend.assets_healthy():raise RuntimeError('本地前端恢复后静态资源验收失败')
                    if original is None:frontend.refresh()
            else:
                logging.info('保留本地服务的明确停止状态')
        except Exception as recovery:
            logging.exception('本地 5173 验收失败：%s',recovery)
            if original is None:
                raise


class LocalSync:
    def __init__(self,root=ROOT,port=8765,*,service=None,validate=None,build=None,stop_timeout=600):
        self.root=Path(root).resolve()
        self.state=self.root/'raw/site-state'
        self.service=service or LocalService(self.root,port,stop_timeout=stop_timeout)
        self.validate=validate or self.validate_data
        self.build=build or self.build_frontend

    def run(self,args,root=None,env=None):
        logging.info('执行：%s',' '.join(map(str,args)))
        result=subprocess.run(list(map(str,args)),cwd=root or self.root,env=child_environment(env),check=False,
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1800)
        if result.stdout.strip(): logging.info('%s',result.stdout.strip())
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'命令失败：{args[0]}')
        return result.stdout.strip()

    def git(self,*args,root=None):
        env={**os.environ,'GIT_TERMINAL_PROMPT':'0',
             'GIT_SSH_COMMAND':os.environ.get('GIT_SSH_COMMAND','ssh -o BatchMode=yes -o ConnectTimeout=15')}
        return self.run(['git','-C',str(root or self.root),*args],env=env)

    def changed(self):
        tracked=self.git('diff','HEAD','--name-only','-z')
        untracked=self.git('ls-files','--others','--exclude-standard','-z')
        return sorted({path for path in (tracked+'\0'+untracked).split('\0') if path})

    def assert_branch(self):
        if self.git('branch','--show-current')!='master':
            raise RuntimeError('本地必须在 master 分支；未自动切换分支')
        if self.git('ls-files','--unmerged'):
            raise RuntimeError('存在未解决的 Git 冲突；请先处理')
        for marker in ('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply'):
            marker_path=self.git('rev-parse','--git-path',marker)
            if (self.root/marker_path).exists():
                raise RuntimeError('存在进行中的 Git 合并/变基；请先完成')

    def clean(self):
        if self.changed():
            raise RuntimeError('本地存在未提交改动，请先运行 publish-local.ps1 或自行保存；未覆盖文件')

    def recover(self):
        proposal_db=self.root/'raw/proposals.sqlite3'
        if proposal_db.with_name(proposal_db.name+'.approval.json').exists():
            from proposals import ProposalStore
            ProposalStore(self.root,proposal_db).recover()
        from website_sync import recover_template_approval
        recover_template_approval(self.root,self.state)
        self.run([sys.executable,self.root/'frontend/website_data.py','recover','--root',self.root])

    def validate_data(self,root,export=False):
        for action in (('recover','export','validate') if export else ('recover','prepare','validate')):
            self.run([sys.executable,root/'frontend/website_data.py',action,'--root',root],root=root)

    def build_frontend(self,paths,root):
        frontend=root/'frontend'
        package_changes=any(path in {'frontend/package.json','frontend/package-lock.json'} for path in paths)
        code_changes=any(path.startswith('frontend/src/') or path in {'frontend/index.html','frontend/vite.config.ts',
            'frontend/tsconfig.json','frontend/tsconfig.node.json'} for path in paths)
        missing=not (self.root/'frontend/dist/index.html').is_file()
        if not (package_changes or code_changes or missing):
            return []
        # Build exclusively in the candidate. Preserve an offline copy of the
        # active runtime before npm can mutate any dependency or dist files.
        for name in ('dist','node_modules'):
            source=self.root/'frontend'/name
            if source.is_dir():
                shutil.copytree(source,frontend/name,symlinks=True)
        npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
        if not npm:
            raise RuntimeError('未找到 npm，请安装 Node.js；没有自动安装模型或 Python 依赖')
        if package_changes or not (frontend/'node_modules').is_dir():
            self.run([npm,'ci'],root=frontend)
        self.run([npm,'run','build','--','--base','/'],root=frontend)
        return [name for name in ('dist','node_modules') if (frontend/name).is_dir()]

    @contextmanager
    def stopped_service(self):
        manager=local_manager(self.root) if isinstance(self.service,LocalService) else None
        managed_state=manager.status(self.root)['services']['backend'] if manager else None
        managed_running=bool(managed_state and managed_state['desired']=='running')
        if manager:manager.pause(self.root,('backend',),reason='publish')
        was_running=managed_state['state'] in ('running','starting','stopping') if managed_state else self.service.running()
        restore_running=managed_running if manager else was_running
        original=None
        try:
            if manager and (managed_running or was_running):
                manager.stop(self.root,('backend',),reason='publish',timeout=self.service.stop_timeout)
            elif was_running:self.service.stop()
            # Do not hold the sync lock while waiting for server shutdown/restart.
            yield
        except BaseException as exc:
            original=exc
            raise
        finally:
            if restore_running:
                try:
                    self.service.restart()
                except Exception as recovery:
                    if original is not None:
                        raise RuntimeError(f'同步失败：{original}；服务恢复也失败：{recovery}') from original
                    raise

    def candidate(self):
        path=self.root/'raw/local-sync/candidates'/uuid.uuid4().hex
        path.parent.mkdir(parents=True,exist_ok=True)
        self.git('clone','--config','core.autocrlf=false','--no-hardlinks','--single-branch',
                 '--branch','master',str(self.root),str(path))
        for key in ('user.name','user.email'):
            self.git('config',key,self.git('config','--get',key),root=path)
        self.git('remote','set-url','origin',self.git('remote','get-url','origin'),root=path)
        logging.info('独立验证目录（失败时保留）：%s',path)
        return path

    def activate(self,candidate,target,runtime):
        # Runtime switches precede the final ff-only Git operation; any failure
        # restores the old runtime. A failed ff never resets user edits.
        backups=self.root/'raw/local-sync/runtime-backups'/uuid.uuid4().hex
        backups.mkdir(parents=True)
        switched=[]
        try:
            for name in runtime:
                if name not in ('dist','node_modules'):
                    raise RuntimeError('无效运行目录，未激活')
                source=candidate/'frontend'/name
                active=self.root/'frontend'/name
                old=backups/name
                if active.exists():
                    active.rename(old)
                try:
                    source.rename(active)
                except Exception:
                    if old.exists(): old.rename(active)
                    raise
                switched.append(name)
            self.git('merge','--ff-only',target)
        except Exception:
            for name in reversed(switched):
                active=self.root/'frontend'/name
                active.rename(candidate/'frontend'/name)
                old=backups/name
                if old.exists(): old.rename(active)
            raise

    def publish(self):
        self.assert_branch()
        with self.stopped_service():
            with sync_lock(self.state):
                initial=self.git('rev-parse','HEAD')
                self.recover()
                self.validate(self.root,export=True)
                paths=[path for path in self.changed() if allowed_local_path(path)]
                if paths:
                    from git_paths import commit_selected
                    commit_selected(self.root,paths,'local: publish code and formal notes',self.git)
                candidate=self.candidate()
                self.git('fetch','origin','master',root=candidate)
                remote_head=self.git('rev-parse','FETCH_HEAD',root=candidate)
                outcome=merge_branches(candidate,self.git('rev-parse','HEAD',root=candidate),remote_head,preferred='right',origin='local')
                if not outcome['handled']:self.git('merge','--no-edit',remote_head,root=candidate)
                self.validate(candidate)
                if self.git('status','--porcelain','--untracked-files=all',root=candidate):
                    raise RuntimeError(f'远端合并后的校验改写了正式文件，已保留验证目录：{candidate}')
                target=self.git('rev-parse','HEAD',root=candidate)
                outgoing=history_paths(lambda *args:self.git(*args,root=candidate),remote_head,target)
                forbidden=[path for path in outgoing if not allowed_local_path(path)]
                if forbidden:
                    raise RuntimeError('待上传提交含白名单外文件，未推送：'+', '.join(sorted(forbidden)))
                changed=self.git('diff','--name-only','-z',initial,target,root=candidate).split('\0')
                runtime=self.build([path for path in changed if path],candidate) or []
                self.validate(candidate)
                self.git('fetch',str(candidate),'master')
                self.activate(candidate,target,runtime)
                self.git('push','origin',f'{target}:refs/heads/master')
                logging.info('Git 发布完成：master=%s；接下来确认本地服务恢复',target)
        logging.info('本地代码和正式笔记已上传 master；服务按原运行状态恢复')
        return {'state':'published','head':target,'candidate':str(candidate),'conflict_note_ids':outcome['conflict_note_ids']}

    def pull(self):
        self.assert_branch()
        self.clean()
        initial=self.git('rev-parse','HEAD')
        self.git('fetch','origin','master')
        remote=self.git('rev-parse','FETCH_HEAD')
        if initial==remote:
            logging.info('本地已是最新版本，不停止或重启服务')
            return {'state':'unchanged','head':initial}
        self.git('merge-base','--is-ancestor',initial,remote)
        with self.stopped_service():
            with sync_lock(self.state):
                self.recover()
                self.clean()
                # Validate remote package before any serving files change.
                candidate=self.candidate()
                self.git('fetch','origin','master',root=candidate)
                self.git('merge','--ff-only',remote,root=candidate)
                self.validate(candidate)
                if self.git('status','--porcelain','--untracked-files=all',root=candidate):
                    raise RuntimeError(f'远端校验发现未提交正式内容：{candidate}')
                changes=self.git('diff','--name-only','-z',initial,remote).split('\0')
                runtime=self.build([path for path in changes if path],candidate) or []
                self.validate(candidate)
                self.activate(candidate,remote,runtime)
                logging.info('Git 快进完成：master=%s；接下来确认本地服务恢复',remote)
        logging.info('已快进更新本地代码和笔记；服务按原运行状态恢复')
        return {'state':'updated','head':remote}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('publish','pull'))
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--port',type=int,choices=(8765,),default=8765)
    parser.add_argument('--stop-timeout',type=float,default=600,help='安全停服等待秒数（默认600，不强制杀进程）')
    args=parser.parse_args()
    if args.stop_timeout<=0: parser.error('stop-timeout 必须为正数')
    directory=args.root/'raw/local-sync'; directory.mkdir(parents=True,exist_ok=True)
    logfile=directory/(args.action+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.log')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',
        handlers=[logging.FileHandler(logfile,encoding='utf-8'),logging.StreamHandler(sys.stdout)])
    logging.info('本次同步日志：%s',logfile.resolve())
    try:
        manager=LocalSync(args.root,args.port,stop_timeout=args.stop_timeout)
        with sync_lock(directory):
            result=run_local_sync(manager,args.action)
        logging.info('同步结束：%s',json.dumps(result,ensure_ascii=False))
        return 0
    except SyncBusy:
        logging.error('另一项同步正在运行，请等待完成后再运行。日志：%s',logfile.resolve())
        return 1
    except Exception as exc:
        logging.exception('同步失败；本地提交、远端与故障验证目录均保留：%s',exc)
        logging.error('请保留日志：%s',logfile.resolve())
        return 1

if __name__=='__main__':
    raise SystemExit(main())
