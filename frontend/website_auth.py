"""File-backed, revocable signed sessions for the explicitly enabled public site."""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
from pathlib import Path
import secrets
import os
import threading
import time

COOKIE = 'os_tutorial_session'


class Unconfigured(ValueError):
    pass


class Auth:
    def __init__(self, config, base_path, *, secure=True, cookie_name=COOKIE):
        self.path = Path(config)
        self.base_path = base_path or '/'
        self.secure=secure
        self.cookie_name=cookie_name
        self.attempts = {}
        self.lock = threading.Lock()

    def config(self):
        try:
            value = json.loads(self.path.read_text('utf-8'))
            version=value.get('schema_version',1)
            if version not in (1,2):raise ValueError()
            users = value['accounts'] if version==2 else value['users']
            secret = value['sessionSecret']
            ttl = value.get('sessionTtlHours',168)
            if not isinstance(secret,str) or len(secret)<32 or not isinstance(ttl,(int,float)) or not 0<ttl<=168:
                raise ValueError()
            if not isinstance(users,list) or not users:
                raise ValueError()
            result = {}
            for row in users:
                name,password=row['username'],row['password']
                if not isinstance(name,str) or not name or not isinstance(password,str) or not password or name in result:
                    raise ValueError()
                role=row.get('role','admin')
                if role not in ('admin','annotator') or (version==1 and role!='admin'):
                    raise ValueError()
                result[name]={'password':password,'role':role}
            return secret, result, int(ttl*3600)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise Unconfigured('管理员配置不可用') from exc

    @staticmethod
    def signature(secret, value):
        return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()

    def _token(self, cookie):
        try:
            secret,users,_=self.config()
            jar=SimpleCookie();jar.load(cookie or '')
            token=jar[self.cookie_name].value
            payload,signature=token.rsplit('.',1)
            if not hmac.compare_digest(self.signature(secret,payload),signature):return None
            value=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            username=value['u']
            if value['exp']<=time.time() or username not in users:return None
            user=users[username]
            expected=self.fingerprint(secret,username,user)
            role=value.get('role',user['role'])
            allowed=['admin','annotator'] if user['role']=='admin' else ['annotator']
            if role not in allowed or not hmac.compare_digest(expected,value['v']):return None
            return value,{'username':username,'account_role':user['role'],'role':role,'allowed_roles':allowed}
        except (Unconfigured,ValueError,TypeError,KeyError,CookieError):
            return None

    def actor(self,cookie):
        token=self._token(cookie)
        return token[1] if token else None

    def identity(self,cookie):
        actor=self.actor(cookie)
        return actor['username'] if actor else None

    def fingerprint(self,secret,username,user):
        return self.signature(secret,username+'\0'+user['password']+'\0'+user['role'])

    def issue(self,secret,username,user,ttl,role=None):
        value={'u':username,'exp':int(time.time())+ttl,'v':self.fingerprint(secret,username,user),
               'role':role or user['role'],'nonce':secrets.token_hex(12)}
        payload=base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')
        return self.cookie(payload+'.'+self.signature(secret,payload),ttl)

    def switch_role(self,cookie,role):
        actor=self.actor(cookie)
        if not actor or role not in actor['allowed_roles']:
            raise PermissionError('账号没有切换到该身份的权限')
        secret,users,ttl=self.config()
        token=self._token(cookie)
        if token:ttl=min(ttl,max(0,int(token[0]['exp']-time.time())))
        return self.issue(secret,actor['username'],users[actor['username']],ttl,role)

    def login(self, username, password, peer):
        secret,users,ttl=self.config()
        with self.lock:
            now=time.monotonic()
            failures=[t for t in self.attempts.get(peer,[]) if now-t<900]
            self.attempts[peer]=failures
            if len(failures)>=10:return 429,None
            if not isinstance(username,str) or not isinstance(password,str) or not hmac.compare_digest(
                    hashlib.sha256(password.encode()).digest(),hashlib.sha256(users.get(username,{'password':secrets.token_hex(32)})['password'].encode()).digest()):
                failures.append(now);return 401,None
            self.attempts.pop(peer,None)
        return 200,self.issue(secret,username,users[username],ttl)

    def cookie(self, token='', ttl=0):
        return f'{self.cookie_name}={token}; Path={self.base_path}; Max-Age={ttl}; HttpOnly;'+(' Secure;' if self.secure else '')+' SameSite=Lax'


class LocalAuth(Auth):
    """Loopback-only role simulation; missing cookies keep existing local admin behavior."""
    def __init__(self,path):
        path=Path(path)
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            secret=secrets.token_urlsafe(48)
            value={'schema_version':2,'sessionSecret':secret,'sessionTtlHours':168,
                   'accounts':[{'username':'local','password':secrets.token_urlsafe(48),'role':'admin'}]}
            temporary=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
            temporary.write_text(json.dumps(value),encoding='utf-8')
            os.chmod(temporary,0o600);os.replace(temporary,path)
        super().__init__(path,'/',secure=False,cookie_name='os_tutorial_local_session')

    def actor(self,cookie):
        return super().actor(cookie) or {'username':'local','account_role':'admin','role':'admin',
                                       'allowed_roles':['admin','annotator']}
