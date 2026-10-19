"""Cross-process request-start limiter and endpoint circuits; never holds a knowledge lock."""
import sqlite3,time
from pathlib import Path
from contextlib import contextmanager

class Deferred(RuntimeError):
 category='risk'
 code=429
 def __init__(self,scope,until):
  self.until=until
  super().__init__(f'HTTP 429: {scope} 请求等待自动恢复')

class NetworkGate:
 def __init__(self,root,interval=2):
  self.path=Path(root)/'raw/crawler/network.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True);self.interval=interval
  with self.db() as db:
   db.execute('CREATE TABLE IF NOT EXISTS limits(scope TEXT PRIMARY KEY, next REAL NOT NULL)')
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=10)
  try:
   with db:yield db
  finally:db.close()
 def defer(self,scope,seconds=60):
  with self.db() as db:
   db.execute('INSERT INTO limits VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET next=MAX(next,excluded.next)',(scope,time.time()+seconds))
 def probe(self,scope):
  # At most one explicit probe per endpoint per minute across all processes.
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');now=time.time()
   previous=db.execute('SELECT next FROM limits WHERE scope=?',('probe:'+scope,)).fetchone()
   if previous and previous[0]>now:return
   db.execute('INSERT OR REPLACE INTO limits VALUES(?,?)',('probe:'+scope,now+60))
   db.execute('DELETE FROM limits WHERE scope=?',(scope,))
 def wait(self,scope):
  while True:
   with self.db() as db:
    db.execute('BEGIN IMMEDIATE');now=time.time()
    circuit=db.execute('SELECT next FROM limits WHERE scope=?',(scope,)).fetchone()
    if circuit and circuit[0]>now:raise Deferred(scope,circuit[0])
    previous=db.execute("SELECT next FROM limits WHERE scope='__start__'").fetchone()
    delay=max(0,(previous[0] if previous else 0)-now)
    if not delay:
     db.execute("INSERT OR REPLACE INTO limits VALUES('__start__',?)",(now+self.interval,));return
   time.sleep(min(delay,.5))
