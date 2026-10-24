"""Explicit lineup-note roles, exact automatic links, and recoverable rename + binding."""
import json,uuid
from pathlib import Path
from copy import deepcopy
import workspace,wxq

JOURNAL='raw/knowledge/pending-note-link.json'

def schema(db):
 db.executescript("""CREATE TABLE IF NOT EXISTS lineup_note_roles(lineup TEXT,note TEXT,role TEXT NOT NULL,PRIMARY KEY(lineup,note));
 CREATE UNIQUE INDEX IF NOT EXISTS one_lineup_primary ON lineup_note_roles(lineup) WHERE role='primary';
 CREATE TABLE IF NOT EXISTS lineup_note_exclusions(lineup TEXT,note TEXT,PRIMARY KEY(lineup,note));
 CREATE TABLE IF NOT EXISTS lineup_note_operations(id TEXT PRIMARY KEY);""")

def links(db,uid):
 rows=db.execute('SELECT n.note,r.role FROM lineup_notes n LEFT JOIN lineup_note_roles r ON r.lineup=n.lineup AND r.note=n.note WHERE n.lineup=? ORDER BY n.note',(uid,)).fetchall()
 return sorted([{'note':r['note'],'role':r['role'] or ('primary' if len(rows)==1 else 'legacy')} for r in rows],key=lambda r:(r['role']!='primary',r['note']))

def auto_link_locked(root):
 from lineup_catalog import LineupCatalog
 root=Path(root)
 if (root/JOURNAL).exists():return []
 catalog=LineupCatalog(root);notes=[n for n in workspace.notes(root) if n['type']=='lineup'];changed=[]
 with catalog.topics.db() as db:
  db.execute('BEGIN IMMEDIATE');roster=catalog.roster(db)
  for note in sorted(notes,key=lambda n:n['id']):
   title=note['title'].strip()
   hits=[r for r in roster if r['enabled'] and not r['deleted_at'] and not r['merged_into'] and title and title in [r['common_name'].strip(),*[a.strip() for a in r['aliases']]]]
   if len(hits)!=1:continue
   row=hits[0];uid=row['id']
   if note['id'] in row['note_ids'] or db.execute('SELECT 1 FROM lineup_note_exclusions WHERE lineup=? AND note=?',(uid,note['id'])).fetchone():continue
   if any(link['role'] in ['primary','legacy'] for link in row['note_links']):continue  # Existing primary or unresolved legacy links always require a decision.
   db.execute('INSERT INTO lineup_notes VALUES(?,?)',(uid,note['id']))
   db.execute("INSERT INTO lineup_note_roles VALUES(?,?,'primary')",(uid,note['id']))
   db.execute('UPDATE topic_lineups SET revision=revision+1 WHERE id=?',(uid,))
   row['note_ids'].append(note['id']);row['note_links']=[{'note':note['id'],'role':'primary'}];changed.append({'lineup':uid,'note':note['id']})
  if changed:catalog.bump(db)
 return changed

def auto_link(root):
 with workspace.store_lock(root,wait=True):
  recover_links_locked(root)
  return auto_link_locked(root)

def apply_links(db,operation):
 if db.execute('SELECT 1 FROM lineup_note_operations WHERE id=?',(operation['id'],)).fetchone():return
 uid=operation['lineup']
 db.execute('DELETE FROM lineup_notes WHERE lineup=?',(uid,));db.execute('DELETE FROM lineup_note_roles WHERE lineup=?',(uid,))
 for link in operation['links']:
  db.execute('INSERT INTO lineup_notes VALUES(?,?)',(uid,link['note']))
  db.execute('INSERT INTO lineup_note_roles VALUES(?,?,?)',(uid,link['note'],link['role']))
 for note in operation['excluded']:db.execute('INSERT OR IGNORE INTO lineup_note_exclusions VALUES(?,?)',(uid,note))
 if operation['action']!='unlink':db.execute('DELETE FROM lineup_note_exclusions WHERE lineup=? AND note=?',(uid,operation['note']))
 db.execute('UPDATE topic_lineups SET revision=revision+1 WHERE id=?',(uid,))
 db.execute('INSERT INTO lineup_note_operations VALUES(?)',(operation['id'],))

def recover_links_locked(root):
 from lineup_catalog import LineupCatalog
 root=Path(root);path=root/JOURNAL;op=wxq.read_json(path)
 if not op:return
 catalog=LineupCatalog(root)
 with catalog.topics.db() as db:
  db.execute('BEGIN IMMEDIATE')
  if not db.execute('SELECT 1 FROM lineup_note_operations WHERE id=?',(op['id'],)).fetchone():
   note=next((n for n in workspace.notes(root) if n['id']==op['note']),None)
   if not note:raise ValueError('关联恢复找不到笔记，原材料已保留')
   if note['title']!=op['title']:
    workspace.edit_locked(root,op['note'],{'revision':op['note_revision'],'title':op['title']},recover_first=False)
   apply_links(db,op);catalog.bump(db)
 path.unlink(missing_ok=True)

def recover_links(root):
 with workspace.store_lock(root,wait=True):
  workspace.recover(root)
  recover_links_locked(root)

def associate(root,payload):
 from lineup_catalog import LineupCatalog
 root=Path(root)
 if set(payload)-{'lineup','note','revision','note_revision','action','title'}:raise ValueError('关联字段无效')
 action=payload.get('action','primary')
 if action not in ['primary','replace','variant','unlink']:raise ValueError('关联操作无效')
 title=payload.get('title','')
 if not isinstance(title,str) or not title.strip():raise ValueError('笔记名称不能为空')
 title=title.strip()
 with workspace.store_lock(root,wait=True):
  workspace.recover(root);recover_links_locked(root)
  catalog=LineupCatalog(root)
  with catalog.topics.db() as db:
   db.execute('BEGIN IMMEDIATE')
   row=next((r for r in catalog.roster(db) if r['id']==payload.get('lineup')),None)
   note=next((n for n in workspace.notes(root) if n['id']==payload.get('note')),None)
   if not row or row['deleted_at'] or row['merged_into'] or not row['enabled']:raise ValueError('目标阵容不可关联')
   if not note or note['type']!='lineup':raise ValueError('只能关联阵容笔记')
   if row['revision']!=payload.get('revision') or note['revision']!=payload.get('note_revision'):raise workspace.Conflict('阵容或笔记已更新，请刷新；草稿已保留')
   current=row['note_links'];primary=next((r['note'] for r in current if r['role']=='primary'),None)
   if action=='primary' and current and primary!=note['id']:raise workspace.Conflict('该阵容已有笔记，请选择替换或作为变体')
   if action=='variant' and (not primary or primary==note['id']):raise ValueError('请先指定其他主笔记，再添加变体')
   names={n['id']:n['title'].strip() for n in workspace.notes(root)}
   if action!='unlink' and any(r['note']!=note['id'] and names.get(r['note'])==title for r in current if action!='replace' or r['role']!='primary'):raise ValueError('笔记名称不能与该阵容下其他笔记重名')
   excluded=[];after=[r for r in current if r['note']!=note['id']]
   if action=='unlink':excluded=[note['id']];title=note['title']
   else:
    if action=='replace':
     excluded=[r['note'] for r in after if r['role']=='primary'];after=[r for r in after if r['role']!='primary']
    after.append({'note':note['id'],'role':'variant' if action=='variant' else 'primary'})
   op={'id':uuid.uuid4().hex,'lineup':row['id'],'note':note['id'],'note_revision':note['revision'],'title':title,'links':after,'excluded':excluded,'action':action}
   if title!=note['title']:
    workspace.edit(root,note['id'],{'revision':note['revision'],'title':title},_locked=True,_recover_first=False,_dry_run=True)
   wxq.atomic_json(root/JOURNAL,op)
   if title!=note['title']:workspace.edit_locked(root,note['id'],{'revision':note['revision'],'title':title},recover_first=False)
   apply_links(db,op);catalog.bump(db)
  (root/JOURNAL).unlink(missing_ok=True)
  auto_link_locked(root)
 return catalog.roster()

def after_knowledge_save(root):
 root=Path(root)
 if (root/'raw/crawler/topics.sqlite3').is_file() and not (root/JOURNAL).exists():auto_link_locked(root)

def project_notes(root):
 import json_store
 if json_store.enabled(root):return json_store.notes(root,public=True)
 from lineup_catalog import LineupCatalog
 catalog=LineupCatalog(root);roster=catalog.roster()
 with catalog.topics.db() as db:excluded={(r['lineup'],r['note']) for r in db.execute('SELECT * FROM lineup_note_exclusions')}
 result=[]
 for note in workspace.notes(root):
  relations=[{'lineup':r['id'],'role':link['role']} for r in roster for link in r['note_links'] if link['note']==note['id']]
  candidates=[r['id'] for r in roster if note['type']=='lineup' and r['enabled'] and not r['deleted_at'] and not r['merged_into'] and note['title'].strip() in [r['common_name'].strip(),*[a.strip() for a in r['aliases']]] and note['id'] not in r['note_ids'] and (r['id'],note['id']) not in excluded]
  result.append({**note,'lineup_links':relations,'lineup_ids':[r['lineup'] for r in relations],'association_candidates':candidates})
 return result
