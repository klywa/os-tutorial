"""File-backed, revocable signed sessions for the explicitly enabled public site."""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import threading
import time

COOKIE = 'os_tutorial_session'


class Unconfigured(ValueError):
    pass


class Auth:
    def __init__(self, config, base_path):
        self.path = Path(config)
        self.base_path = base_path or '/'
        self.attempts = {}
        self.lock = threading.Lock()

    def config(self):
        try:
            value = json.loads(self.path.read_text('utf-8'))
            users = value['users']
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
                result[name]=password
            return secret, result, int(ttl*3600)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise Unconfigured('管理员配置不可用') from exc

    @staticmethod
    def signature(secret, value):
        return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()

    def identity(self, cookie):
        try:
            secret,users,_=self.config()
            jar=SimpleCookie();jar.load(cookie or '')
            token=jar[COOKIE].value
            payload,signature=token.rsplit('.',1)
            if not hmac.compare_digest(self.signature(secret,payload),signature):return None
            value=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            username=value['u']
            if value['exp']<=time.time() or username not in users:return None
            expected=self.signature(secret,username+'\0'+users[username])
            return username if hmac.compare_digest(expected,value['v']) else None
        except (Unconfigured,ValueError,TypeError,KeyError):
            return None

    def login(self, username, password, peer):
        secret,users,ttl=self.config()
        with self.lock:
            now=time.monotonic()
            failures=[t for t in self.attempts.get(peer,[]) if now-t<900]
            self.attempts[peer]=failures
            if len(failures)>=10:return 429,None
            if not isinstance(username,str) or not isinstance(password,str) or not hmac.compare_digest(
                    hashlib.sha256(password.encode()).digest(),hashlib.sha256(users.get(username,secrets.token_hex(32)).encode()).digest()):
                failures.append(now);return 401,None
            self.attempts.pop(peer,None)
        value={'u':username,'exp':int(time.time())+ttl,'v':self.signature(secret,username+'\0'+users[username]),'nonce':secrets.token_hex(12)}
        payload=base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')
        return 200,self.cookie(payload+'.'+self.signature(secret,payload),ttl)

    def cookie(self, token='', ttl=0):
        return f'{COOKIE}={token}; Path={self.base_path}; Max-Age={ttl}; HttpOnly; Secure; SameSite=Lax'
