import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import json_store as store
import knowledge_history

class ConsolidationTests(unittest.TestCase):
 def setUp(self):
  folder=Path(__file__).resolve().parents[4]/'raw/test-temp';folder.mkdir(parents=True,exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=folder);self.root=Path(self.temp.name)
  self.rows=[{'body':{'schema_version':6,'nodes':[{'id':nid,'type':'heading','level':1,'title':nid}]},'metadata':{'id':nid,'title':nid,'type':'other','path':'knowledge/other/'+nid+'.json'}} for nid in ('source','target')]
  store.save(self.root,self.rows,storage_version=2)
 def tearDown(self):self.temp.cleanup()
 def plan(self):
  rows={r['metadata']['id']:r for r in store.records(self.root)}
  return [rows['target']],{'source':{'revision':rows['source']['metadata']['revision'],'target':'target'}}
 def test_atomic_retirement_alias_and_archive(self):
  unrelated={'body':{'schema_version':6,'nodes':[{'id':'u','type':'heading','level':1,'title':'unrelated'}]},'metadata':{'id':'unrelated','title':'unrelated','type':'other','path':'knowledge/other/unrelated.json'}}
  store.save(self.root,[unrelated],partial=True)
  unchanged=(self.root/'knowledge/other/unrelated.json').read_bytes()
  incoming,retire=self.plan();store.commit(self.root,incoming,retire=retire)
  self.assertEqual({r['metadata']['id'] for r in store.records(self.root)},{'target','unrelated'})
  self.assertEqual(unchanged,(self.root/'knowledge/other/unrelated.json').read_bytes())
  self.assertEqual(store.resolve_note(self.root,'source')['id'],'target')
  self.assertFalse((self.root/'knowledge/other/source.json').exists())
  self.assertTrue(list((self.root/knowledge_history.folder('source')/'versions').glob('*.json')))
  store.commit(self.root,store.records(self.root),retire=retire)
 def test_source_revision_and_missing_target_abort_without_writes(self):
  incoming,retire=self.plan();retire['source']['revision']='stale'
  with self.assertRaises(ValueError):store.commit(self.root,incoming,retire=retire)
  self.assertEqual(len(store.records(self.root)),2)
  incoming,retire=self.plan();incoming[0]['metadata']['revision']='stale'
  with self.assertRaises(ValueError):store.commit(self.root,incoming,retire=retire)
  self.assertEqual(len(store.records(self.root)),2)
 def test_cli_commit_adapter_forwards_explicit_retire_map(self):
  import wxq
  incoming,retire=self.plan()
  with patch.object(store,'commit',return_value={'notes':[]}) as commit:
   wxq.commit_notes(self.root,incoming,retire=retire)
   commit.assert_called_once_with(self.root,incoming,retire=retire)
  incoming,retire=self.plan();retire['source']['target']='missing'
  with self.assertRaises(ValueError):store.commit(self.root,incoming,retire=retire)
  self.assertEqual(len(store.records(self.root)),2)
 def test_blocked_source_and_protected_target_abort(self):
  incoming,retire=self.plan()
  with patch('knowledge_conflicts.is_blocked',return_value=True):
   with self.assertRaises(ValueError):store.commit(self.root,incoming,retire=retire)
  incoming[0]['body']['nodes'][0]['title']='new';incoming[0]['metadata']['title']='new'
  with patch.object(store,'manual_nodes',return_value={'target'}):
   with self.assertRaises(ValueError):store.commit(self.root,incoming,retire=retire)
  self.assertEqual(len(store.records(self.root)),2)
 def test_interruption_recovers_targets_aliases_and_retirement(self):
  incoming,retire=self.plan();original=store.write_file
  incoming[0]['body']['nodes'].append({'id':'chapter','type':'heading','level':2,'title':'merged chapter'})
  def fail(path,value):
   if Path(path)==self.root/store.INDEX:raise OSError('crash before index')
   return original(path,value)
  with patch.object(store,'write_file',side_effect=fail):
   with self.assertRaises(OSError):store.commit(self.root,incoming,retire=retire)
  store.recover(self.root)
  self.assertEqual(store.resolve_note(self.root,'source')['id'],'target')
  self.assertEqual(store.resolve_note(self.root,'source')['document']['nodes'][-1]['title'],'merged chapter')
  self.assertFalse((self.root/'knowledge/other/source.meta.json').exists())

if __name__=='__main__':unittest.main()
