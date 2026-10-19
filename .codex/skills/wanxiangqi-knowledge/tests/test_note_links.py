import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from lineup_catalog import LineupCatalog
from note_links import auto_link,associate,recover_links

class NoteLinkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root)
  wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'card:1','name':'甲'},{'id':'card:2','name':'乙'}])
  self.cat=LineupCatalog(self.root)
 def note(self,nid,title):
  with workspace.store_lock(self.root):
   workspace.persist(self.root,workspace.notes(self.root)+[{'id':nid,'type':'lineup','title':title,'aliases':[],'entities':[],'claims':[]}])
  return next(n for n in workspace.notes(self.root) if n['id']==nid)
 def lineup(self,name='网站名',common='主名',aliases=None):
  self.cat.save({'name':name,'common_name':common,'heroes':['card:2' if self.cat.roster() else 'card:1'],'aliases':aliases or []})
  return self.cat.roster()[-1]
 def payload(self,uid,nid,action='primary',title=None):
  row=next(r for r in self.cat.roster() if r['id']==uid);note=next(n for n in workspace.notes(self.root) if n['id']==nid)
  return {'lineup':uid,'note':nid,'action':action,'title':title or note['title'],'revision':row['revision'],'note_revision':note['revision']}
 def test_unique_name_auto_links_but_ambiguous_or_partial_does_not(self):
  row=self.lineup(aliases=['别名']);self.note('one',' 别名 ');self.note('two','主名攻略')
  auto_link(self.root);r=self.cat.roster()[0]
  self.assertEqual(r['primary_note_id'],'one');self.assertEqual(r['note_ids'],['one'])
  other=self.lineup('另一套','主名');self.note('three','主名');auto_link(self.root)
  self.assertFalse(any('three' in r['note_ids'] for r in self.cat.roster()))
 def test_replace_unlinks_old_and_prevents_automatic_rebound(self):
  row=self.lineup();self.note('one','主名');auto_link(self.root);self.note('two','新笔记')
  associate(self.root,self.payload(row['id'],'two','replace'))
  auto_link(self.root)
  self.assertEqual(self.cat.roster()[0]['note_ids'],['two'])
  self.assertEqual(len(workspace.notes(self.root)),2)
 def test_variant_rename_conflict_and_manual_unlink(self):
  row=self.lineup();self.note('one','主名');self.note('two','另一篇');auto_link(self.root)
  with self.assertRaises(ValueError):associate(self.root,self.payload(row['id'],'two','variant','主名'))
  associate(self.root,self.payload(row['id'],'two','variant','变体攻略'))
  r=self.cat.roster()[0];self.assertEqual(r['note_links'],[{'note':'one','role':'primary'},{'note':'two','role':'variant'}])
  self.assertEqual(next(n for n in workspace.notes(self.root) if n['id']=='two')['title'],'变体攻略')
  associate(self.root,self.payload(row['id'],'one','unlink'));auto_link(self.root)
  self.assertNotIn('one',self.cat.roster()[0]['note_ids'])
 def test_stale_save_is_atomic_and_journal_recovers_after_rename(self):
  row=self.lineup();self.note('one','第一篇')
  payload=self.payload(row['id'],'one',title='改名')
  with self.assertRaises(workspace.Conflict):associate(self.root,{**payload,'note_revision':'stale'})
  self.assertEqual(workspace.notes(self.root)[0]['title'],'第一篇')
  with patch('note_links.apply_links',side_effect=OSError('interrupted')):
   with self.assertRaises(OSError):associate(self.root,payload)
  recover_links(self.root)
  self.assertEqual(workspace.notes(self.root)[0]['title'],'改名')
  self.assertEqual(self.cat.roster()[0]['primary_note_id'],'one')
 def test_legacy_multiple_links_have_no_guessed_primary(self):
  row=self.lineup();self.note('one','甲笔记');self.note('two','乙笔记')
  with self.cat.topics.db() as db:db.executemany('INSERT INTO lineup_notes VALUES(?,?)',[(row['id'],'one'),(row['id'],'two')])
  current=self.cat.roster()[0]
  self.assertIsNone(current['primary_note_id'])
  self.assertEqual({x['role'] for x in current['note_links']},{'legacy'})
 def test_invalid_rename_does_not_poison_recovery(self):
  row=self.lineup();self.note('one','原笔记')
  with self.assertRaises(ValueError):associate(self.root,self.payload(row['id'],'one',title='ABC'))
  self.assertFalse((self.root/'knowledge/pending-note-link.json').exists())
  recover_links(self.root)
  associate(self.root,self.payload(row['id'],'one',title='有效中文标题'))
  self.assertEqual(self.cat.roster()[0]['primary_note_id'],'one')
 def test_disabled_deleted_and_manual_name_save_triggers(self):
  row=self.lineup();self.note('one','新常用名')
  self.cat.save_batch({'items':[{'id':row['id'],'revision':row['revision'],'common_name':'新常用名'}]})
  current=self.cat.roster()[0];self.assertEqual(current['primary_note_id'],'one')
  self.cat.delete(current['id'],{'revision':current['revision']})
  self.note('two','新常用名');auto_link(self.root)
  self.assertNotIn('two',self.cat.roster()[0]['note_ids'])
 def test_api_revision_and_read_does_not_create_links(self):
  import threading,json,urllib.request,urllib.error
  from server import create_server
  row=self.lineup();self.note('one','主名')
  with self.cat.topics.db() as db:
   db.execute('DELETE FROM lineup_notes');db.execute('DELETE FROM lineup_note_roles')
  server=create_server(self.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  base=f'http://127.0.0.1:{server.server_port}/api/'
  try:
   rows=__import__('json').load(urllib.request.urlopen(base+'notes'))
   self.assertEqual(rows[0]['lineup_ids'],[])
   self.assertEqual(rows[0]['association_candidates'],[row['id']])
   payload=self.payload(row['id'],'one',title='改名后主笔记')
   request=urllib.request.Request(base+'topics/lineups/associate',json.dumps(payload).encode(),{'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
   with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
   self.assertEqual(caught.exception.code,409)
   detail=json.load(urllib.request.urlopen(base+'notes/one'))
   self.assertEqual(detail['lineup_links'],[{'lineup':row['id'],'role':'primary'}])
  finally:server.shutdown();server.server_close();thread.join()
