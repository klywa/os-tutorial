import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from test_knowledge_merge import record
import json_store as store
from knowledge_conflicts import create_request,write_request,get_group,resolve,is_blocked
from workspace import Conflict
class EventTests(unittest.TestCase):
 def test_dedupe_third_version_and_resolve(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();store.save(root,[b]);l=deepcopy(b);r=deepcopy(b);l['body']['nodes'][1]['value']='L';r['body']['nodes'][1]['value']='R';req=create_request(b,l,r);write_request(root,req);write_request(root,req);g=get_group(root,'n');self.assertEqual(len(g['request_ids']),1)
   t=deepcopy(r);t['body']['nodes'][1]['value']='T';write_request(root,create_request(b,l,t))
   with self.assertRaises(Conflict):resolve(root,'n',{'revision':g['revision'],'note_revision':g['note_revision'],'choices':[]})
   g=get_group(root,'n');resolve(root,'n',{'revision':g['revision'],'note_revision':g['note_revision'],'choices':[{'conflict_id':c['id'],'action':'current'} for c in g['conflicts']]});self.assertFalse(is_blocked(root,'n'));write_request(root,req);self.assertFalse(is_blocked(root,'n'))

class RecoveryTests(unittest.TestCase):
 def prepare(self,root):
  b=record();store.save(root,[b]);l=deepcopy(b);r=deepcopy(b);l['body']['nodes'][1]['value']='L';r['body']['nodes'][1]['value']='R';write_request(root,create_request(b,l,r));g=get_group(root,'n')
  return {'revision':g['revision'],'note_revision':g['note_revision'],'choices':[{'conflict_id':c['id'],'action':'incoming','variant_id':c['variant_id']} for c in g['conflicts']]}
 def test_atomic_recovery_and_clone_without_raw(self):
  from unittest.mock import patch
  import knowledge_conflicts as events
  import shutil
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);payload=self.prepare(root)
   with patch.object(events,'immutable_event',side_effect=OSError('interrupted')):
    with self.assertRaises(OSError):resolve(root,'n',payload)
   self.assertTrue((root/store.JOURNAL).exists());store.recover(root);self.assertFalse(is_blocked(root,'n'));saved=store.load_record(root,'n');self.assertTrue(saved['metadata'].get('history') or saved['metadata'].get('history_head'));shutil.rmtree(root/'raw');self.assertFalse(is_blocked(root,'n'))
 def test_manual_text_does_not_inherit_evidence(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);payload=self.prepare(root)
   for c in payload['choices']:c.update(action='manual',text='handwritten')
   resolve(root,'n',payload);saved=store.load_record(root,'n');self.assertEqual(saved['body']['nodes'][1]['value'],'handwritten');self.assertEqual(saved['metadata']['claim_annotations'],[]);self.assertEqual(saved['metadata']['node_annotations']['a']['origin'],'manual')

if __name__=='__main__':unittest.main()

class BranchHistoryTests(unittest.TestCase):
 def test_preferred_head_and_all_archived_branch_versions_are_readable(self):
  import knowledge_history as history
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);store.write_file(root/store.INDEX,{'schema_version':6,'storage_version':2,'notes':[],'aliases':{}});b=record();store.save(root,[b]);b=store.load_record(root,'n');l=deepcopy(b);r=deepcopy(b)
   for src,label in ((l,'L'),(r,'R')):
    src['metadata']['history']=[{'origin':label,'old_evidence':label}]
    for e in history.extract(src):history.immutable(root,e['path'],e['value'])
    src['body']['nodes'][1]['value']=label
   write_request(root,create_request(b,l,r));g=get_group(root,'n');resolve(root,'n',{'revision':g['revision'],'note_revision':g['note_revision'],'choices':[{'conflict_id':c['id'],'action':'incoming','variant_id':c['variant_id']} for c in g['conflicts']]})
   versions=history.version_entries(root,'n');labels=set()
   for version in versions:
    for row in history.history_entries(root,version['record']):
     if row.get('origin') in ('L','R'):labels.add(row['origin'])
   self.assertEqual(labels,{'L','R'});self.assertNotIn('history_parents',store.load_record(root,'n')['metadata'])

class SingleDecisionTests(unittest.TestCase):
 def test_semantic_references_show_each_versions_supporting_text(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();b['body']['supporting_nodes']=[{'id':'old','type':'entry','key':'正文','show_key':False,'value':'旧版选择条件'},{'id':'new','type':'entry','key':'正文','show_key':False,'value':'新版选择条件'}]
   b['body']['semantics']={'general':[{'$text':'old'}]};l=deepcopy(b);r=deepcopy(b)
   l['metadata']['manual_semantics']=True;r['body']['semantics']={'general':[{'$text':'new'}]}
   store.save(root,[l]);write_request(root,create_request(b,l,r));g=get_group(root,'n')
   c=next(c for c in g['conflicts'] if c['path']=='body/semantics')
   self.assertIn('旧版选择条件',c['current']);self.assertIn('新版选择条件',c['incoming'])
 def test_semantic_choices_show_actual_business_values(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();b['body']['semantics']={'topic':'旧主题'};l=deepcopy(b);r=deepcopy(b)
   l['metadata']['manual_semantics']=True;r['body']['semantics']['topic']='新主题'
   store.save(root,[l]);write_request(root,create_request(b,l,r));g=get_group(root,'n')
   c=next(c for c in g['conflicts'] if c['path']=='body/semantics')
   self.assertIn('旧主题',c['current']);self.assertIn('新主题',c['incoming']);self.assertIn('主题',c['incoming'])
 def test_many_requests_same_path_has_one_manual_decision(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();l=deepcopy(b);l['body']['nodes'][1]['value']='L';store.save(root,[l])
   for text in ('R','T'):
    r=deepcopy(b);r['body']['nodes'][1]['value']=text;write_request(root,create_request(b,l,r))
   g=get_group(root,'n');self.assertEqual(len(g['conflicts']),1);c=g['conflicts'][0];self.assertEqual(len(c['variants']),2)
   resolve(root,'n',{'revision':g['revision'],'note_revision':g['note_revision'],'choices':[{'conflict_id':c['id'],'action':'manual','text':'MY MERGE'}]})
   self.assertEqual(store.load_record(root,'n')['body']['nodes'][1]['value'],'MY MERGE');self.assertFalse(is_blocked(root,'n'))
 def test_record_conflict_excludes_leaf_decisions(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'].pop(2);l['body']['nodes'][1]['value']='L';r['body']['nodes'][1]['value']='R';r['body']['semantics']={'general':[{'$text':'b'}]};store.save(root,[l]);write_request(root,create_request(b,l,r));g=get_group(root,'n')
   self.assertEqual([c['path'] for c in g['conflicts']],['record'])

class DecisionValidationTests(unittest.TestCase):
 def test_ambiguous_or_duplicate_choices_preserve_requests(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=record();l=deepcopy(b);l['body']['nodes'][1]['value']='L';store.save(root,[l])
   for text in ('R','T'):
    r=deepcopy(b);r['body']['nodes'][1]['value']=text;write_request(root,create_request(b,l,r))
   g=get_group(root,'n');c=g['conflicts'][0];payload={'revision':g['revision'],'note_revision':g['note_revision'],'choices':[{'conflict_id':c['id'],'action':'incoming'}]}
   with self.assertRaises(ValueError):resolve(root,'n',payload)
   self.assertTrue(is_blocked(root,'n'));self.assertEqual(store.load_record(root,'n')['body']['nodes'][1]['value'],'L')
   payload['choices']=[{'conflict_id':c['id'],'action':'manual','text':'MY MERGE'},{'conflict_id':c['id'],'action':'current'}]
   with self.assertRaises(ValueError):resolve(root,'n',payload)
   self.assertTrue(is_blocked(root,'n'))
   target=next(v for v in c['variants'] if v['value']=='T');payload['choices']=[{'conflict_id':c['id'],'action':'incoming','variant_id':target['variant_id']}];resolve(root,'n',payload)
   self.assertEqual(store.load_record(root,'n')['body']['nodes'][1]['value'],'T');self.assertFalse(is_blocked(root,'n'))
