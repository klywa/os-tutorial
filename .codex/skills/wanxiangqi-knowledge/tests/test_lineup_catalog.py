import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from lineup_catalog import normalize_records,LineupCatalog
from topics import TopicStore

class LineupCatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root)
  wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'card:1','name':'甲'},{'id':'card:2','name':'乙'},{'id':'card:3','name':'丙'}])
  self.store=LineupCatalog(self.root)
 def test_exact_set_dedup_and_preferred_name(self):
  rows=[{'name':'低热名','heroes':['甲','乙'],'usage':.1,'games':100},{'name':'主名','heroes':['乙','甲'],'usage':.2,'games':200},{'name':'另一套','heroes':['甲','丙'],'usage':.3,'games':300},{'name':'未知','heroes':['不存在'],'usage':1}]
  result=normalize_records(rows,[{'id':'card:1','name':'甲'},{'id':'card:2','name':'乙'},{'id':'card:3','name':'丙'}])
  self.assertEqual(len(result['items']),2);self.assertEqual(len(result['errors']),1)
  first=next(r for r in result['items'] if r['name']=='主名');self.assertEqual(first['heroes'],['card:1','card:2']);self.assertIn('低热名',first['aliases'])
 def pair(self):
  self.store.save({'name':'甲阵','heroes':['card:1']});self.store.save({'name':'乙阵','heroes':['card:2']});return self.store.roster()
 def test_batch_names_are_atomic_manual_and_allow_shared_display(self):
  a,b=self.pair();revision=self.store.revision()
  self.store.save_batch({'items':[{'id':r['id'],'revision':r['revision'],'common_name':'共享常用名','aliases':[' 别名 ','别名','']} for r in (a,b)]})
  rows=self.store.roster();self.assertEqual(self.store.revision(),revision+1)
  for r in rows:self.assertEqual(r['common_name'],'共享常用名');self.assertEqual(r['aliases'],['别名']);self.assertIn('common_name',r['manual_fields'])
  self.assertIsNone(self.store.topics.map_lineup('共享常用名'))
  self.store.save_batch({'items':[{'id':rows[0]['id'],'revision':rows[0]['revision'],'common_name':'','aliases':[]}]});self.assertEqual(self.store.roster()[0]['display_name'],'甲阵')
 def test_batch_stale_or_invalid_does_not_partially_save(self):
  a,b=self.pair()
  for change,exception in [({'revision':0},workspace.Conflict),({'aliases':[123]},ValueError),({'heroes':[]},ValueError)]:
   before=self.store.roster()
   with self.assertRaises(exception):self.store.save_batch({'items':[{'id':a['id'],'revision':a['revision'],'common_name':'不应写入'},{'id':b['id'],'revision':b['revision'],'common_name':'乙名',**change}]})
   self.assertEqual(self.store.roster(),before)
 def test_soft_delete_restore_preserves_references_and_previous_enabled(self):
  a,b=self.pair()
  with self.store.topics.db() as db:db.execute('INSERT INTO lineup_notes VALUES(?,?)',(a['id'],'historical-note'))
  self.store.delete(a['id'],{'revision':a['revision']});r=self.store.roster()[0]
  self.assertTrue(r['deleted_at']);self.assertFalse(r['enabled']);self.assertEqual(r['note_ids'],['historical-note']);self.assertIsNone(self.store.topics.map_lineup('甲阵'))
  with self.assertRaises(ValueError):self.store.save({**r,'enabled':True})
  with self.assertRaises(ValueError):self.store.save_batch({'items':[{'id':r['id'],'revision':r['revision'],'common_name':'复活'}]})
  self.store.restore(r['id'],{'revision':r['revision']});r=self.store.roster()[0];self.assertFalse(r['deleted_at']);self.assertTrue(r['enabled'])
  self.store.save({**r,'enabled':False});r=self.store.roster()[0];self.store.delete(r['id'],{'revision':r['revision']});r=self.store.roster()[0];self.store.restore(r['id'],{'revision':r['revision']});self.assertFalse(self.store.roster()[0]['enabled'])
 def test_delete_keeps_resolved_topics_and_sync_cannot_resurrect(self):
  a,b=self.pair();topics=self.store.topics;text=self.root/'raw/topic.md';text.write_text('甲阵主线教学','utf8');topics.setting('validated',True)
  topics.sync([{'id':'s','title':'甲阵','transcript_path':str(text)}]);task=topics.claim();topics.finish(task,{'players':[],'lineups':[{'name':'甲阵','evidence':'甲阵主线教学','grounded':True}]})
  self.assertEqual(topics.project([{'id':'s'}])[0]['topic_lineups'],[a['id']])
  self.store.delete(a['id'],{'revision':a['revision']})
  report={'items':[{'name':'网站改名','heroes':a['heroes'],'aliases':[],'sources':[]}],'errors':[],'scanned':1}
  self.store.apply(self.store.preview(report)['token']);r=self.store.roster()[0]
  self.assertTrue(r['deleted_at']);self.assertFalse(r['enabled']);self.assertEqual(topics.project([{'id':'s'}])[0]['topic_lineups'],[a['id']])
 def test_legacy_write_cannot_enable_deleted_and_merged_cannot_restore(self):
  a,b=self.pair();self.store.delete(a['id'],{'revision':a['revision']});a=self.store.roster()[0]
  with self.assertRaises(ValueError):self.store.topics.save_roster({**a,'enabled':True})
  self.store.restore(a['id'],{'revision':a['revision']});a,b=self.store.roster();self.store.merge({'source':a['id'],'target':b['id'],'source_revision':a['revision'],'target_revision':b['revision']});a=self.store.roster()[0]
  with self.assertRaises(ValueError):self.store.restore(a['id'],{'revision':a['revision']})
 def test_parallel_batch_only_one_can_commit_same_revision(self):
  from concurrent.futures import ThreadPoolExecutor
  a,b=self.pair()
  def save(value):
   try:self.store.save_batch({'items':[{'id':a['id'],'revision':a['revision'],'common_name':value}]});return 'saved'
   except workspace.Conflict:return 'conflict'
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(save,['一','二'])),['conflict','saved'])
 def test_stable_import_manual_protection_and_revision(self):
  report={'items':[{'name':'甲乙','heroes':['card:1','card:2'],'aliases':[],'sources':[]}],'errors':[],'scanned':1,'scope':{}}
  preview=self.store.preview(report);self.store.apply(preview['token']);first=self.store.roster()[0]
  updated=self.store.save({**first,'name':'人工名','sort_order':7});self.assertEqual(updated[0]['name'],'人工名')
  with self.assertRaises(workspace.Conflict):self.store.save({**first,'name':'过期修改'})
  self.store.apply(self.store.preview(report)['token']);row=self.store.roster()[0]
  self.assertEqual(row['id'],first['id']);self.assertEqual(row['name'],'人工名');self.assertEqual(row['sort_order'],7)
 def test_complete_composition_only_and_stale_roster_result(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2'],'aliases':[]})
  topics=TopicStore(self.root);row=self.store.roster()[0]
  self.assertEqual(topics.candidate_target({'name':'未知','grounded':False,'evidence':'甲乙成员教学','heroes':['card:1','card:2'],'complete':True},[row]),row['id'])
  self.assertIsNone(topics.candidate_target({'name':'未知','grounded':False,'evidence':'甲乙成员教学','heroes':['card:1'],'complete':False},[row]))
 def test_roster_change_rejects_running_result(self):
  topics=self.store.topics;topics.setting('validated',True)
  text=self.root/'raw/text.md';text.write_text('主要教学正文','utf8')
  topics.sync([{'id':'source:1','title':'教学','transcript_path':str(text)}]);task=topics.claim()
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']})
  self.assertFalse(topics.finish(task,{'players':[],'lineups':[]}));self.assertEqual(topics.snapshot()['counts'].get('queued'),1)
 def test_preview_conflict_and_transaction_rollback(self):
  report={'items':[{'name':'导入','heroes':['card:1'],'aliases':[],'sources':[]}],'errors':[],'scanned':1}
  preview=self.store.preview(report);self.store.save({'name':'人工','heroes':['card:2']})
  with self.assertRaises(workspace.Conflict):self.store.apply(preview['token'])
  self.assertEqual([r['name'] for r in self.store.roster()],['人工'])
 def test_merge_redirects_manual_theme_and_preserves_notes(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});self.store.save({'name':'乙丙','heroes':['card:2','card:3']})
  a,b=self.store.roster()
  self.store.merge({'source':a['id'],'target':b['id'],'source_revision':a['revision'],'target_revision':b['revision']})
  source={'id':'s','manual_values':{'topic_lineups':[a['id']]}}
  self.assertEqual(self.store.topics.project([source])[0]['topic_lineups'],[b['id']])
  self.assertEqual(self.store.roster()[0]['merged_into'],b['id'])
 def test_different_sets_with_same_imported_name_stay_ambiguous(self):
  report={'items':[{'name':'同名','heroes':['card:1'],'aliases':[],'sources':[]},{'name':'同名','heroes':['card:2'],'aliases':[],'sources':[]}],'scanned':2,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);self.assertEqual(len(self.store.roster()),2)
  self.assertIsNone(self.store.topics.map_lineup('同名'))
  row=self.store.roster()[0];self.store.save({**row,'sort_order':8});self.assertEqual(len(self.store.roster()),2)
 def test_binding_requires_real_note_and_revision(self):
  self.store.save({'name':'阵容','heroes':['card:1']});row=self.store.roster()[0]
  with self.assertRaises(ValueError):self.store.bind({'lineup':row['id'],'note_ids':['invented'],'revision':row['revision']})
  with self.assertRaises(workspace.Conflict):self.store.bind({'lineup':row['id'],'note_ids':[],'revision':0})
 def test_members_need_verbatim_evidence(self):
  from topics import validate_result
  data={'players':[],'lineups':[{'name':'甲乙','evidence':'甲乙教学主线','complete':True,'members':[{'name':'甲','evidence':'这里没有对应名字'}]}]}
  with self.assertRaises(ValueError):validate_result(data,'甲乙教学主线。这里没有对应名字',[])
 def test_import_does_not_resurrect_merged_composition(self):
  report={'items':[{'name':'甲','heroes':['card:1'],'aliases':[],'sources':[]},{'name':'乙','heroes':['card:2'],'aliases':[],'sources':[]}],'scanned':2,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);a,b=self.store.roster()
  self.store.merge({'source':a['id'],'target':b['id'],'source_revision':a['revision'],'target_revision':b['revision']})
  self.store.apply(self.store.preview(report)['token']);rows=self.store.roster()
  self.assertEqual(len(rows),2);self.assertFalse(rows[0]['enabled']);self.assertEqual(rows[0]['merged_into'],b['id'])
 def test_same_name_can_be_disambiguated_by_complete_members(self):
  roster=[{'id':'a','name':'同名','enabled':True,'aliases':[],'heroes':['card:1']},{'id':'b','name':'同名','enabled':True,'aliases':[],'heroes':['card:2']}]
  c={'name':'同名','evidence':'同名的教学','grounded':True,'heroes':['card:2'],'complete':True}
  self.assertEqual(self.store.topics.candidate_target(c,roster),'b')
 def test_evidence_length_is_bounded(self):
  from topics import validate_result
  data={'players':[],'lineups':[{'name':'甲','evidence':'甲'*81}]}
  with self.assertRaises(ValueError):validate_result(data,'甲'*81,[])
 def test_website_reads_all_pages_and_detects_incomplete_result(self):
  import json
  from unittest.mock import patch
  from lineup_catalog import fetch_website
  class Response:
   def __init__(self,value):self.value=value
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self):return self.value.encode('utf8')
  def lineup(name,hero):return {'lineupKey':hero,'heroes':[{'id':hero,'name':name}],'count':50,'appearanceRate':.1,'recommendedUnits':[{'heroId':hero,'itemIds':['a','b','c'],'appearanceRate':1,'count':50}]}
  responses=['<script src="/assets/index-test.js"></script>','assets/desktop-main-test.js','[{value:"v261015",label:"v261015"}]',json.dumps({'lineups':[lineup('甲','1')],'total':2}),json.dumps({'lineups':[lineup('乙','2')],'total':2}),json.dumps({'variants':[],'variantCount':0}),json.dumps({'variants':[],'variantCount':0})]
  with patch('lineup_catalog.urllib.request.urlopen',side_effect=[Response(r) for r in responses]),patch('lineup_catalog.time.sleep'):
   report=fetch_website(self.root)
  self.assertEqual(report['pages'],2);self.assertEqual(report['scanned'],2);self.assertEqual(len(report['items']),2)
  responses[4]=json.dumps({'lineups':[],'total':2})
  with patch('lineup_catalog.urllib.request.urlopen',side_effect=[Response(r) for r in responses]),patch('lineup_catalog.time.sleep'):
   with self.assertRaises(ValueError):fetch_website(self.root)
 def test_confirmed_alias_is_manual_revisioned_and_survives_import(self):
  report={'items':[{'name':'甲','heroes':['card:1'],'aliases':[],'sources':[]}],'scanned':1,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);row=self.store.roster()[0];topics=self.store.topics
  text=self.root/'raw/text.md';text.write_text('甲的主线教学','utf8');topics.setting('validated',True)
  topics.sync([{'id':'s','title':'甲','transcript_path':str(text)}]);task=topics.claim()
  topics.finish(task,{'players':[],'lineups':[{'name':'别称','evidence':'甲的主线教学','grounded':False}]})
  candidate=topics.pending()[0];before=self.store.revision();topics.resolve(candidate['id'],{'target':row['id'],'remember_alias':True})
  self.assertGreater(self.store.revision(),before)
  with self.assertRaises(workspace.Conflict):self.store.save(row)
  self.store.apply(self.store.preview(report)['token']);self.assertIn('别称',self.store.roster()[0]['aliases'])
 def test_member_edit_rechecks_automatic_composition_mapping(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});row=self.store.roster()[0];topics=self.store.topics
  text=self.root/'raw/text.md';text.write_text('甲和乙的主线教学','utf8');topics.setting('validated',True)
  source={'id':'s','title':'教学','transcript_path':str(text)};topics.sync([source]);task=topics.claim()
  topics.finish(task,{'players':[],'lineups':[{'name':'未知名字','grounded':False,'evidence':'甲和乙的主线教学','complete':True,'members':[{'id':'card:1','name':'甲','evidence':'甲和乙的主线教学'},{'id':'card:2','name':'乙','evidence':'甲和乙的主线教学'}]}]})
  self.assertEqual(topics.project([source])[0]['topic_lineups'],[row['id']])
  self.store.save({**row,'heroes':['card:2','card:3']})
  self.assertEqual(topics.project([source])[0]['topic_lineups'],[]);self.assertEqual(len(topics.pending()),1)
 def test_stale_candidate_confirmation_is_rejected(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});uid=self.store.roster()[0]['id'];topics=self.store.topics
  text=self.root/'raw/text.md';text.write_text('甲和乙的主线教学','utf8');topics.setting('validated',True)
  source={'id':'s','title':'教学','transcript_path':str(text)};topics.sync([source]);task=topics.claim()
  topics.finish(task,{'players':[],'lineups':[{'name':'未知','grounded':False,'evidence':'甲和乙的主线教学'}]});candidate=topics.pending()[0]
  source['ignored']=True;topics.sync([source])
  with self.assertRaises(workspace.Conflict):topics.resolve(candidate['id'],{'target':uid})
 def test_full_reextract_preserves_ignored_waiting_and_manual_values(self):
  topics=self.store.topics;text=self.root/'raw/text.md';text.write_text('测试主题正文','utf8')
  rows=[{'id':'ready','title':'教学','transcript_path':str(text),'manual_values':{'topic_players':[]}},{'id':'ignored','title':'忽略','ignored':True,'transcript_path':str(text)},{'id':'waiting','title':'待稿'},{'id':'silent','transcript_path':str(text),'transcript_status':'no_speech'}]
  topics.sync(rows);topics.setting('paused',True);result=topics.control('reextract')
  self.assertTrue(result['batch']['id']);self.assertTrue(result['paused']);self.assertEqual(result['counts'],{'queued':1,'ignored':1,'waiting':1,'no_speech':1})
  self.assertEqual(topics.project([rows[0]])[0]['topic_players'],[])
 def test_composition_pass_cannot_add_a_player_or_a_topic(self):
  from unittest.mock import patch
  from topic_model import LocalModel
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});uid=self.store.roster()[0]['id'];model=LocalModel(self.root)
  primary={'players':[{'id':'player:1','evidence':'棋手一教学'}],'lineups':[{'name':'原文打法','evidence':'甲和乙的主线教学'}]}
  composition={'players':[{'id':'player:2','evidence':'额外棋手'}],'lineups':[{'name':'原文打法','members':[{'name':'甲','evidence':'甲和乙的主线教学'},{'name':'乙','evidence':'甲和乙的主线教学'}],'complete':True},{'name':'不该新增','members':[],'complete':False}]}
  with patch.object(model,'tokens',return_value=[1]),patch.object(model,'decode',return_value='甲和乙的主线教学'),patch.object(model,'ask',side_effect=[primary,composition]) as ask:
   result=model.extract('棋手一教学','甲和乙的主线教学',[{'id':'player:1','name':'棋手一'}])
  self.assertEqual(ask.call_count,2);self.assertEqual([p['id'] for p in result['players']],['player:1']);self.assertEqual([r['name'] for r in result['lineups']],['原文打法'])
  self.assertEqual(self.store.topics.candidate_target(result['lineups'][0],self.store.roster()),uid)
 def test_long_summary_does_not_repeat_last_chunk_composition(self):
  from unittest.mock import patch
  from topic_model import LocalModel
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});model=LocalModel(self.root)
  def ask(content,players,valid_text,composition=False):
   self.assertFalse(composition,'No full roster composition is evidenced in these chunks')
   return {'players':[],'lineups':[{'name':'未知打法','evidence':'原文打法教学'}]}
  with patch.object(model,'tokens',side_effect=[[1],list(range(5000)),[1]]),patch.object(model,'decode',return_value='原文打法教学'),patch.object(model,'ask',side_effect=ask) as request:
   result=model.extract('教学','原文打法教学',[])
  self.assertEqual(request.call_count,3);self.assertEqual(result['provenance']['chunks'],2)
 def test_common_name_display_and_manual_clear_survives_sync(self):
  report={'items':[{'name':'网站甲乙','heroes':['card:1','card:2'],'aliases':[],'sources':[]}],'scanned':1,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);row=self.store.roster()[0]
  self.store.save({**row,'common_name':'常用打法','aliases':['别名']});row=self.store.roster()[0]
  self.assertEqual(row.get('display_name'),'常用打法');self.assertEqual(self.store.topics.map_lineup('常用打法'),row['id'])
  self.store.save({**row,'common_name':''});self.store.apply(self.store.preview(report)['token'])
  self.assertEqual(self.store.roster()[0]['common_name'],'');self.assertEqual(self.store.roster()[0]['display_name'],'网站甲乙')
 def test_shared_common_name_does_not_merge_or_guess(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2'],'common_name':'共同打法'})
  self.store.save({'name':'甲丙','heroes':['card:1','card:3'],'common_name':'共同打法'})
  rows=self.store.roster();self.assertEqual([r.get('display_name') for r in rows],['共同打法','共同打法'])
  self.assertIsNone(self.store.topics.map_lineup('共同打法'))
 def test_variants_stay_children_and_map_to_unique_parent(self):
  report={'items':[{'name':'主打法','heroes':['card:1','card:2'],'aliases':[],'sources':[], 'variants':[{'heroes':['card:1','card:3'],'sources':[{'games':51}]}]}],'scanned':1,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);rows=self.store.roster()
  self.assertEqual(len(rows),1);self.assertEqual(len(rows[0].get('variants',[])),1)
  c={'name':'未知名','evidence':'甲丙主线教学','grounded':False,'complete':True,'heroes':['card:1','card:3']}
  self.assertEqual(self.store.topics.candidate_target(c,rows),rows[0]['id'])
 def test_detail_variants_all_pages_and_sample_filter(self):
  from lineup_catalog import fetch_variants
  pages=[{'variants':[{'heroes':[{'id':'1'},{'id':'3'}],'count':51}], 'variantCount':2},{'variants':[{'heroes':[{'id':'2'},{'id':'3'}],'count':49}],'variantCount':2}]
  result=fetch_variants(lambda url,payload:__import__('json').dumps(pages[payload['page']-1]),{'minimumCount':50},{'lineupKey':'root'})
  self.assertEqual(result['scanned'],2);self.assertEqual(len(result['items']),1);self.assertEqual(len(result['pages']),2)
  with self.assertRaises(ValueError):fetch_variants(lambda *args:__import__('json').dumps(pages[0]),{'minimumCount':50},{'lineupKey':'root'})
 def test_naming_review_conflict_and_manual_protection(self):
  self.store.save({'name':'甲乙','heroes':['card:1','card:2']});row=self.store.roster()[0]
  self.store.add_naming(row['id'],{'name':'常用甲乙','reason':'只有一个来源','evidence':[{'url':'https://a.example/post','quote':'常用甲乙攻略'}]})
  c=self.store.naming()[0]
  with self.assertRaises(workspace.Conflict):self.store.resolve_naming(c['id'],{'action':'common','target':row['id'],'revision':0,'candidate_revision':c['revision']})
  self.store.resolve_naming(c['id'],{'action':'common','target':row['id'],'revision':row['revision'],'candidate_revision':c['revision']})
  self.assertEqual(self.store.roster()[0]['display_name'],'常用甲乙');self.assertFalse(self.store.naming())
 def test_removing_automatic_name_match_rechecks_saved_evidence(self):
  self.store.save({'name':'甲乙','common_name':'旧名','heroes':['card:1','card:2']});row=self.store.roster()[0];topics=self.store.topics
  text=self.root/'raw/text.md';text.write_text('旧名教学攻略','utf8');topics.setting('validated',True);source={'id':'s','title':'教学','transcript_path':str(text)}
  topics.sync([source]);task=topics.claim();topics.finish(task,{'players':[],'lineups':[{'name':'旧名','evidence':'旧名教学攻略','grounded':True}]})
  self.assertEqual(topics.project([source])[0]['topic_lineups'],[row['id']])
  self.store.save({**row,'common_name':'新名'})
  self.assertEqual(topics.project([source])[0]['topic_lineups'],[])
 def test_manual_variant_removal_survives_other_edits_and_sync(self):
  report={'items':[{'name':'主','heroes':['card:1','card:2'],'sources':[],'aliases':[],'variants':[{'heroes':['card:1','card:3']}]}],'scanned':1,'errors':[]}
  self.store.apply(self.store.preview(report)['token']);row=self.store.roster()[0]
  self.store.save_variants({'lineup':row['id'],'revision':row['revision'],'variants':[]});row=self.store.roster()[0]
  self.store.save({k:v for k,v in row.items() if k!='common_name'});self.store.apply(self.store.preview(report)['token'])
  self.assertFalse(self.store.roster()[0]['variants'])
 def test_model_checks_complete_child_without_loading_all_variants(self):
  from unittest.mock import patch
  from topic_model import LocalModel
  self.store.save({'name':'主','common_name':'常用','heroes':['card:1','card:2']});row=self.store.roster()[0]
  self.store.save_variants({'lineup':row['id'],'revision':row['revision'],'variants':[{'heroes':['card:1','card:3']}]})
  model=LocalModel(self.root);primary={'players':[],'lineups':[{'name':'常用','evidence':'甲丙这套常用主线教学'}]};detail={'players':[],'lineups':[{'name':'常用','complete':True,'members':[{'name':n,'evidence':'甲丙这套常用主线教学'} for n in ['甲','丙']]}]}
  with patch.object(model,'tokens',return_value=[1]),patch.object(model,'decode',return_value='甲丙这套常用主线教学'),patch.object(model,'ask',side_effect=[primary,detail]):result=model.extract('教学','甲丙这套常用主线教学',[])
  self.assertTrue(result['lineups'][0].get('complete'))
 def test_incomplete_import_rejected_before_preview_and_apply(self):
  report={'items':[{'name':'主','heroes':['card:1'],'sources':[],'aliases':[]}],'errors':['未知英雄'],'scanned':2}
  with self.assertRaises(ValueError):self.store.preview(report)
  clean={**report,'errors':[]};token=self.store.preview(clean)['token']
  with self.store.topics.db() as db:db.execute('UPDATE lineup_imports SET payload=? WHERE token=?',(__import__('json').dumps(report),token))
  with self.assertRaises(ValueError):self.store.apply(token)
  self.assertFalse(self.store.roster())
 def test_naming_evidence_change_invalidates_old_decision(self):
  self.store.save({'name':'主','heroes':['card:1']});row=self.store.roster()[0]
  item={'name':'常用','evidence':[{'url':'https://a.example','quote':'旧依据'}]};cid=self.store.add_naming(row['id'],item);old=self.store.naming()[0]
  self.store.add_naming(row['id'],{**item,'evidence':[{'url':'https://b.example','quote':'新依据'}]})
  with self.assertRaises(workspace.Conflict):self.store.resolve_naming(cid,{'action':'common','target':row['id'],'revision':row['revision'],'candidate_revision':old['revision']})
  self.assertEqual(self.store.roster()[0]['common_name'],'')
 def test_legacy_edit_keeps_manual_common_name_and_variant_protection(self):
  self.store.save({'name':'主','heroes':['card:1'],'common_name':''});row=self.store.roster()[0]
  self.store.save_variants({'lineup':row['id'],'revision':row['revision'],'variants':[]});row=self.store.roster()[0]
  self.store.topics.save_roster({'id':row['id'],'revision':row['revision'],'name':'主改名','aliases':[],'enabled':True})
  self.assertTrue({'common_name','variants'}.issubset(self.store.roster()[0]['manual_fields']))
