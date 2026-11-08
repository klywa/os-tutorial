"""Authenticated local controller; durable child monitoring lives in Node."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent
_launchers=[]  # Keep Popen handles for reaping; monitoring belongs to Node.
sys.path.insert(0,str(HERE.parent/'frontend'))
from website_sync import sync_lock,SyncBusy


def _directory(root):
    return Path(root).resolve()/'raw/local-services'


def _request(root,action,data=None,*,timeout=8):
    root=Path(root).resolve()
    control=json.loads((_directory(root)/'control.json').read_text(encoding='utf-8'))
    if (os.path.normcase(str(Path(control['root']).resolve()))!=os.path.normcase(str(root)) or
            not isinstance(control.get('port'),int) or not 0<control['port']<65536):
        raise RuntimeError('本地管理器身份不匹配；未修改任何服务')
    request=urllib.request.Request(f"http://127.0.0.1:{control['port']}/{action}",
        data=None if data is None else json.dumps(data).encode(),
        headers={'Authorization':'Bearer '+control['token'],'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:result=json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(json.load(exc).get('error','本地管理器请求失败')) from None
    if (result.get('instance_id')!=control.get('instance_id') or result.get('pid')!=control.get('pid') or
            os.path.normcase(str(Path(result.get('root','')).resolve()))!=os.path.normcase(str(root))):
        raise RuntimeError('本地管理器实例不匹配；未修改任何服务')
    return result


def status(root):
    """Read-only, sanitized state; never returns the control token."""
    try:return _request(root,'status')
    except (FileNotFoundError,ConnectionError,urllib.error.URLError,OSError):
        return {'available':False,'mode':'local','root':str(Path(root).resolve()),'services':{}}


def stored_status(root):
    """Snapshot for service identity endpoints: no recursive manager HTTP."""
    for attempt in range(3):
        try:
            filename=_directory(root)/'status.json'
            value=json.loads(filename.read_text(encoding='utf-8'))
            if Path(value['root']).resolve()==Path(root).resolve():
                # A surviving backend must not claim that a dead manager is live.
                # Keep its last diagnostics, but distinguish a stale snapshot from
                # a responsive authenticated status() result.
                if time.time()-filename.stat().st_mtime>10:
                    value={**value,'available':False,'stale':True}
                return value
            break
        except FileNotFoundError:break
        except OSError:
            # Windows atomic replacement and antivirus scanners can briefly
            # deny reads. Never let diagnostics break the service identity API.
            if attempt<2:time.sleep(.01)
            else:return {'available':False,'services':{},'snapshot_error':'temporarily_unavailable'}
        except (ValueError,KeyError):break
    return {'available':False,'services':{}}


def configuration(root):
    root=Path(root).resolve();frontend=root/'frontend'
    python=root/'.wxq-runtime'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    python=str(python) if python.is_file() else sys.executable
    node=shutil.which('node');vite=frontend/'node_modules/vite/bin/vite.js'
    if not node or not vite.is_file():raise RuntimeError('缺少 Node.js 或 Vite，请先安装前端依赖')
    return {'root':str(root),'services':{
        'backend':{'port':8765,'root':str(root),'cwd':str(root),'identity_path':'/api/local-service/status',
                   'stop_path':'/api/local-service/stop','command':[python,str(frontend/'server.py'),'--root',str(root),'--port','8765']},
        'frontend':{'port':5173,'root':str(frontend),'cwd':str(frontend),'identity_path':'/__wxq_local_frontend',
                    'stop_path':'/__wxq_local_frontend/stop','command':[node,str(vite)]}}}


def _bootstrap(root,config=None):
    root=Path(root).resolve();directory=_directory(root);directory.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+20
    while True:
        try:
            with sync_lock(directory/'bootstrap'):
                existing=status(root)
                if existing['available']:return existing
                node=shutil.which('node')
                if not node:raise RuntimeError('未找到 Node.js')
                config=config or configuration(root)
                if Path(config['root']).resolve()!=root:raise ValueError('configuration root mismatch')
                configpath=directory/'config.json';configpath.write_text(json.dumps(config),encoding='utf-8')
                options={'cwd':root,'stdin':subprocess.DEVNULL,'env':{**os.environ,'PYTHONUTF8':'1'}}
                if os.name=='nt':
                    # Node detached mode stays alive independently. Explicit
                    # breakaway also escapes a kill-on-close tool job on Windows.
                    options['creationflags']=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_BREAKAWAY_FROM_JOB
                else:options['start_new_session']=True
                with (directory/'manager-launch.log').open('ab') as output:
                    process=subprocess.Popen([node,str(HERE/'local_supervisor.cjs'),str(configpath)],stdout=output,stderr=output,**options)
                _launchers.append(process)
                while time.monotonic()<deadline:
                    result=status(root)
                    if result['available']:return result
                    if process.poll() is not None:raise RuntimeError(f'本地管理器启动退出 code={process.returncode}；日志：{directory / "manager-launch.log"}')
                    time.sleep(.1)
                raise RuntimeError(f'本地管理器启动超时；日志：{directory / "manager-launch.log"}')
        except SyncBusy:
            if time.monotonic()>=deadline:raise RuntimeError('另一项本地服务启动仍在执行') from None
            time.sleep(.1)


def pause(root,services=('backend',),reason='explicit_stop'):
    if not status(root)['available']:return None
    return _request(root,'pause',{'services':list(services),'reason':reason})


def stop(root,services=('backend','frontend'),reason='explicit_stop',timeout=600):
    result=_request(root,'pause',{'services':list(services),'reason':reason,'stop':True})
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if any(result['services'][name]['state']=='foreign' for name in services):
            raise RuntimeError('端口属于其他项目或实例已变更；未停止原进程')
        if all(result['services'][name]['state']=='paused' for name in services):return result
        time.sleep(.25);result=status(root)
    raise RuntimeError(f'安全停止超时；没有强杀进程或丢弃后台任务。日志：{_directory(root)}')


def resume(root,services=('backend','frontend')):
    _bootstrap(root)
    return _request(root,'resume',{'services':list(services)})


def notify_stop(root,service='backend',supervisor_instance=None):
    """Persist stop intent before acknowledging a direct local stop endpoint.

    A manager-initiated stop already persisted the intent. Recognize its exact
    instance from the private control file without recursively calling HTTP.
    """
    try:
        control=json.loads((_directory(root)/'control.json').read_text(encoding='utf-8'))
    except FileNotFoundError:return
    if supervisor_instance and supervisor_instance==control.get('instance_id'):return
    pause(root,(service,),reason='explicit_stop')


def wait_ready(root,services=('backend','frontend'),timeout=120):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=status(root)
        if all(result.get('services',{}).get(name,{}).get('state')=='running' for name in services):return result
        foreign=[s for s in result.get('services',{}).values() if s['state']=='foreign']
        if foreign:raise RuntimeError('端口属于其他项目或无法确认身份；未停止原进程：'+str(foreign))
        time.sleep(.25)
    raise RuntimeError(f'本地服务就绪超时；日志：{_directory(root)}')


def ensure(root,restart_backend=False,build=False):
    root=Path(root).resolve()
    if build:
        npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
        if not npm:raise RuntimeError('未找到 npm')
        subprocess.run([npm,'run','build','--','--base','/'],cwd=root/'frontend',check=True)
    _bootstrap(root)
    if restart_backend:
        from local_sync import LocalService
        service=LocalService(root)
        if service.running():service.stop()
    resume(root)
    result=wait_ready(root)
    from local_sync import LocalService,LocalFrontend
    backend=LocalService(root);frontend=LocalFrontend(root)
    if not backend.healthy() or not backend.assets_healthy() or not frontend.healthy():
        raise RuntimeError('本地页面、静态资源或 API 验收失败')
    return result
