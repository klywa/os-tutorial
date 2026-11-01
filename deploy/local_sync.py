#!/usr/bin/env python3
"""Explicit local publish/pull workflow; never force-push or kill arbitrary processes."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'frontend'))
from website_sync import sync_lock
from git_history import history_paths


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
    if parts[0] == 'knowledge':
        return path == 'knowledge/index.meta.json' or (len(parts)==3 and parts[1] in {'players','lineups','other'} and basename.endswith('.json'))
    if parts[0] == 'website-data':
        return basename.endswith(('.json','.img'))
    if parts[0] in {'frontend','deploy','docs'} or path.startswith('.codex/skills/wanxiangqi-knowledge/'):
        return basename.endswith(('.py','.ts','.tsx','.js','.jsx','.json','.css','.html','.md','.txt','.ps1','.sh','.zsh',
                                  '.yml','.yaml','.toml','.service','.timer','.sudoers','.fragment'))
    return False


class LocalService:
    def __init__(self, root, port=8765, *, stop_timeout=600, clock=time.monotonic, sleep=time.sleep):
        self.root, self.port = Path(root).resolve(), port
        self.url = f'http://127.0.0.1:{port}'
        self.stop_timeout, self.clock, self.sleep = stop_timeout, clock, sleep
        self.stopping = False

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
            raise RuntimeError('端口已有服务但不支持安全停止；请先在原窗口 Ctrl+C，升级一次后重试。不自动杀进程。') from exc
        except (ValueError, TypeError) as exc:
            raise RuntimeError('本地服务身份响应无效，未停止任何服务') from exc
        if (not isinstance(status,dict) or status.get('mode')!='local' or status.get('port')!=self.port or
                not isinstance(status.get('root'),str) or
                os.path.normcase(str(Path(status['root']).resolve()))!=os.path.normcase(str(self.root))):
            raise RuntimeError('端口属于其他项目或公网服务，未停止任何服务')
        return True

    def stop(self):
        request=urllib.request.Request(self.url+'/api/local-service/stop', data=b'{}', method='POST',
            headers={'Origin':self.url,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=5) as response:
            if response.status!=202:
                raise RuntimeError('本地服务未确认安全停止')
        self.stopping = True
        self.wait_stopped()

    def wait_stopped(self):
        deadline = self.clock() + self.stop_timeout
        next_progress = self.clock()
        while self.occupied():
            now = self.clock()
            if now >= deadline:
                raise RuntimeError('等待本地服务退出超时；未拉取覆盖文件；原服务仍在安全关闭，不会强制杀进程')
            if now >= next_progress:
                logging.info('等待本项目后台任务安全结束并关闭服务…（最多 %s 秒）', self.stop_timeout)
                next_progress = now + 15
            self.sleep(min(0.5, deadline-now))
        self.stopping = False
        logging.info('本项目本地服务已停止')

    def restart(self):
        if self.stopping:
            # A confirmed shutdown can stop accepting HTTP while workers drain.
            # Wait for that known instance, rather than classifying it as foreign.
            self.wait_stopped()
        if self.running():
            return
        directory=self.root/'raw/local-sync'; directory.mkdir(parents=True,exist_ok=True)
        logfile=directory/('server-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.log')
        options={'cwd':self.root,'stdin':subprocess.DEVNULL,'stderr':subprocess.STDOUT}
        if os.name=='nt':
            options['creationflags']=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            options['start_new_session']=True
        with logfile.open('ab') as output:
            process=subprocess.Popen([sys.executable,str(self.root/'frontend/server.py'),
                '--root',str(self.root),'--port',str(self.port)],stdout=output,**options)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(f'本地服务重启失败，日志：{logfile}')
            try:
                if self.running():
                    logging.info('本地服务已隐藏重启：%s（日志：%s）',self.url,logfile)
                    return
            except RuntimeError:
                pass  # Port can accept before the HTTP status endpoint is ready.
            time.sleep(0.2)
        raise RuntimeError(f'等待重启健康检查超时，未强制杀进程；请检查日志：{logfile}')


class LocalSync:
    def __init__(self,root=ROOT,port=8765,*,service=None,validate=None,build=None,stop_timeout=600):
        self.root=Path(root).resolve()
        self.state=self.root/'raw/site-state'
        self.service=service or LocalService(self.root,port,stop_timeout=stop_timeout)
        self.validate=validate or self.validate_data
        self.build=build or self.build_frontend

    def run(self,args,root=None,env=None):
        logging.info('执行：%s',' '.join(map(str,args)))
        result=subprocess.run(list(map(str,args)),cwd=root or self.root,env=env,check=False,
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
        was_running=self.service.running()
        try:
            if was_running:
                self.service.stop()
            # Do not hold the sync lock while waiting for server shutdown/restart.
            yield
        finally:
            if was_running:
                self.service.restart()

    def candidate(self):
        path=self.root/'raw/local-sync/candidates'/uuid.uuid4().hex
        path.parent.mkdir(parents=True,exist_ok=True)
        self.git('clone','--no-hardlinks','--single-branch','--branch','master',str(self.root),str(path))
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
                    self.git('add','--all','--',*paths)
                    self.git('commit','--only','-m','local: publish code and formal notes','--',*paths)
                candidate=self.candidate()
                self.git('fetch','origin','master',root=candidate)
                remote_head=self.git('rev-parse','FETCH_HEAD',root=candidate)
                self.git('merge','--no-edit',remote_head,root=candidate)
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
                logging.info('本地代码和正式笔记已上传 master；服务按原运行状态恢复')
                return {'state':'published','head':target,'candidate':str(candidate)}

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
                logging.info('已快进更新本地代码和笔记；服务按原运行状态恢复')
                return {'state':'updated','head':remote}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('publish','pull'))
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--stop-timeout',type=float,default=600,help='安全停服等待秒数（默认600，不强制杀进程）')
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('port 必须在 1..65535')
    if args.stop_timeout<=0: parser.error('stop-timeout 必须为正数')
    directory=args.root/'raw/local-sync'; directory.mkdir(parents=True,exist_ok=True)
    logfile=directory/(args.action+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.log')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',
        handlers=[logging.FileHandler(logfile,encoding='utf-8'),logging.StreamHandler(sys.stdout)])
    logging.info('本次同步日志：%s',logfile.resolve())
    try:
        manager=LocalSync(args.root,args.port,stop_timeout=args.stop_timeout)
        with sync_lock(directory):
            result=getattr(manager,args.action)()
        logging.info('同步结束：%s',json.dumps(result,ensure_ascii=False))
        return 0
    except Exception as exc:
        logging.exception('同步失败；本地提交、远端与故障验证目录均保留：%s',exc)
        logging.error('请保留日志：%s',logfile.resolve())
        return 1

if __name__=='__main__':
    raise SystemExit(main())
