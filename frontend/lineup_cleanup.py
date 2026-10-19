"""Recoverable roster cleanup, protected by associations and a versioned preview."""
import hashlib,json,uuid,sqlite3
from pathlib import Path
import workspace,wxq
from lineup_catalog import LineupCatalog

class Cleanup:
 def __init__(self,root):
  self.root=Path(root);self.catalog=LineupCatalog(root)
  with self.catalog.topics.db() as db:db.execute('CREATE TABLE IF NOT EXISTS cleanup_previews(token TEXT PRIMARY KEY,fingerprint TEXT,payload TEXT)')
 def snapshot(self,db):
  rows=self.catalog.roster(db)
  fingerprint=hashlib.sha256(json.dumps([(r['id'],r['revision'],r['note_ids'],r['deleted_at'],r['merged_into']) for r in rows],sort_keys=True).encode()).hexdigest()
  return rows,fingerprint
 def preview(self):
  with self.catalog.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');rows,fingerprint=self.snapshot(db)
   remove=[r for r in rows if not r['deleted_at'] and not r['merged_into'] and not r['note_ids']]
   keep=[r for r in rows if not r['deleted_at'] and not r['merged_into'] and r['note_ids']]
   token=uuid.uuid4().hex;payload={'token':token,'remove':[{'id':r['id'],'name':r['display_name']} for r in remove],'keep':[{'id':r['id'],'name':r['display_name']} for r in keep]}
   db.execute('INSERT INTO cleanup_previews VALUES(?,?,?)',(token,fingerprint,json.dumps(payload,ensure_ascii=False)))
  return payload
 def apply(self,token):
  with workspace.store_lock(self.root,wait=True):
   backup=self.root/'raw/crawler/backups'/('lineup-cleanup-'+uuid.uuid4().hex+'.sqlite3');backup.parent.mkdir(parents=True,exist_ok=True)
   with self.catalog.topics.db() as src:
    dest=sqlite3.connect(backup);src.backup(dest);dest.close()
   with self.catalog.topics.db() as db:
    db.execute('BEGIN IMMEDIATE');preview=db.execute('SELECT * FROM cleanup_previews WHERE token=?',(token,)).fetchone()
    if not preview:raise KeyError('清理预览不存在')
    rows,fingerprint=self.snapshot(db)
    if fingerprint!=preview['fingerprint']:raise workspace.Conflict('名单或笔记关联已更新，请重新预览')
    removed=[]
    for row in rows:
     if row['deleted_at'] or row['merged_into'] or row['note_ids']:continue
     fields=json.dumps(sorted(set(row['manual_fields'])|{'deleted_at','enabled'}))
     db.execute('UPDATE topic_lineups SET deleted_at=?,restore_enabled=enabled,enabled=0,manual_fields=?,revision=revision+1 WHERE id=?',(wxq.now(),fields,row['id']));removed.append(row['id'])
    if removed:self.catalog.bump(db)
    db.execute('DELETE FROM cleanup_previews WHERE token=?',(token,))
  return {'removed':removed,'backup':str(backup),'roster':self.catalog.roster()}
