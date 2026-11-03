"""Three way merge regression tests."""
import sys, unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from knowledge_merge import merge_record

def record():
 return {'body':{'schema_version':6,'nodes':[{'id':'h','type':'heading','level':1,'title':'N'},{'id':'a','type':'entry','key':'A','value':'old','show_key':True},{'id':'b','type':'entry','key':'B','value':'old','show_key':True}]},'metadata':{'id':'n','type':'other','title':'N','path':'knowledge/other/n.json'}}
class MergeTests(unittest.TestCase):
 def test_independent_and_unchanged_inputs(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'][1]['value']='left';r['body']['nodes'][2]['value']='right';before=deepcopy([b,l,r]);m=merge_record(b,l,r)
  self.assertFalse(m['conflicts']);self.assertEqual([n.get('value') for n in m['record']['body']['nodes']],[None,'left','right']);self.assertEqual([b,l,r],before)
 def test_conflicting_and_identical_edits(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'][1]['value']='left';r['body']['nodes'][1]['value']='right';self.assertTrue(merge_record(b,l,r)['conflicts']);self.assertFalse(merge_record(b,l,l)['conflicts'])
 def test_delete_edit(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'].pop(1);r['body']['nodes'][1]['value']='right';self.assertTrue(merge_record(b,l,r)['conflicts'])
 def test_parallel_inserts(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'].insert(2,dict(b['body']['nodes'][1],id='x'));r['body']['nodes'].insert(2,dict(b['body']['nodes'][1],id='y'));m=merge_record(b,l,r);self.assertFalse(m['conflicts']);self.assertEqual({n['id'] for n in m['record']['body']['nodes']},{'h','a','b','x','y'})

class EvidenceTests(unittest.TestCase):
 def test_selected_text_evidence_and_protection(self):
  b=record();l=deepcopy(b);r=deepcopy(b)
  l['metadata']['claim_annotations']=[{'id':'cl','text_ref':'a','origin':'manual','evidence':[{'source':'L'}]}]
  l['metadata']['node_annotations']={'a':{'origin':'manual'}}
  r['body']['nodes'][1]['value']='new';r['metadata']['claim_annotations']=[{'id':'cr','text_ref':'a','evidence':[{'source':'R'}]}]
  m=merge_record(b,l,r)['record'];self.assertEqual([c['id'] for c in m['metadata']['claim_annotations']],['cr']);self.assertEqual(m['metadata']['node_annotations']['a']['origin'],'manual')
 def test_same_text_evidence_union_and_metadata(self):
  b=record();l=deepcopy(b);r=deepcopy(b)
  for x,source in ((l,'L'),(r,'R')):x['metadata']['claim_annotations']=[{'id':'c','text_ref':'a','evidence':[{'source':source}]}]
  l['metadata']['aliases']=['X'];r['metadata']['topic']='Y';m=merge_record(b,l,r)
  self.assertFalse(m['conflicts']);self.assertEqual(len(m['record']['metadata']['claim_annotations'][0]['evidence']),2);self.assertEqual(m['record']['metadata']['aliases'],['X'])
 def test_identity_collision(self):
  l=record();r=deepcopy(l);r['body']['nodes'][1]['value']='other';self.assertTrue(merge_record(None,l,r)['conflicts'])

class ProtectionTests(unittest.TestCase):
 def test_manual_text_requires_explicit_resolution(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['metadata']['node_annotations']={'a':{'origin':'manual'}};r['body']['nodes'][1]['value']='overwrite'
  self.assertTrue(merge_record(b,l,r)['conflicts'])

class ReferenceTests(unittest.TestCase):
 def test_deletion_cannot_leave_semantic_dangling_reference(self):
  b=record();b['body']['semantics']={'general':[{'$text':'a'}]};l=deepcopy(b);r=deepcopy(b);l['body']['nodes'].pop(1)
  m=merge_record(b,l,r)
  self.assertTrue(m['conflicts'])

class OrderingTests(unittest.TestCase):
 def test_parallel_insertion_identity_collision(self):
  b=record();l=deepcopy(b);r=deepcopy(b);l['body']['nodes'].append({'id':'x','type':'entry','key':'L','value':'same'});r['body']['nodes'].append({'id':'x','type':'entry','key':'R','value':'same'});self.assertTrue(merge_record(b,l,r)['conflicts'])
 def test_contradictory_order(self):
  b=record();b['body']['nodes'].append(dict(b['body']['nodes'][1],id='c'));l=deepcopy(b);r=deepcopy(b);l['body']['nodes'][1:]=[b['body']['nodes'][2],b['body']['nodes'][1],b['body']['nodes'][3]];r['body']['nodes'][1:]=[b['body']['nodes'][1],b['body']['nodes'][3],b['body']['nodes'][2]];self.assertTrue(any(c['path'].endswith('/order') for c in merge_record(b,l,r)['conflicts']))

if __name__=='__main__':unittest.main()
