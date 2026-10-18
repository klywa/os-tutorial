import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq,workspace,tactics

DIMS=('heroes','mechanism','tempo','equipment','talents','skills')
def variant():
 return {'id':'skill-loop','name':'技能循环','condition_refs':['change'],'baseline_refs':['base'],'claim_refs':['change'], 'late_variant_ids':[],'operation_route_ids':[], 'differences':{d:{'status':'different' if d=='mechanism' else 'unknown','claim_refs':['change'] if d=='mechanism' else []} for d in DIMS}}
def note():
 return {'id':'generic','type':'lineup','title':'通用打法','core':[],'entities':[],'related':[], 'meta':{**workspace.default_meta({'core':[]}),'major_variants':[variant()]},'claims':[{'id':'base','section':'核心机制','text':'共通成长规则','kind':'mechanic','evidence':[]},{'id':'change','section':'阵容组成','text':'技能循环改变等级来源','kind':'conditional_strategy','evidence':[]}]}

class MajorVariantsTests(unittest.TestCase):
 def test_html_export_uses_same_chapters_and_internal_anchors(self):
  from export_reading import render_html
  from lineup_layout import reading_document
  n=note();out=render_html(n)
  for s in reading_document(n)['sections']:self.assertIn('id="'+s['id']+'"',out)
  for c in n['claims']:self.assertEqual(out.count(c['text']),1)
  self.assertIn('href="#chapter-',out)
  self.assertIn('<strong>比较主干</strong>',out)
 def test_legacy_claim_ids_work_with_new_variant_refs(self):
  n=note();base=n['claims'][0];del base['id']
  n['meta']['major_variants'][0]['baseline_refs']=[tactics.claim_id(base)]
  tactics.validate(n['meta'],lambda _:None,n['claims'])
 def test_baseline_comparison_keeps_primary_text_in_linked_chapter(self):
  from lineup_layout import reading_document
  n=note();n['claims'][0]['section']='推荐装备'
  n['meta']['major_variants'][0]['differences']['equipment']={'status':'same','claim_refs':['base']}
  doc=reading_document(n);equipment=next(s for s in doc['sections'] if s['title']=='推荐装备')
  major=next(s for s in doc['sections'] if s['title']=='主要变阵')
  self.assertIn('共通成长规则',equipment['markdown']);self.assertNotIn('共通成长规则',major['markdown'])
 def test_known_comparison_requires_evidence_and_all_dimensions(self):
  n=note();tactics.validate(n['meta'],lambda _:None,n['claims'])
  for status in ('same','different'):
   m=copy.deepcopy(n['meta']);m['major_variants'][0]['differences']['skills']={'status':status,'claim_refs':[]}
   with self.assertRaises(ValueError):tactics.validate(m,lambda _:None,n['claims'])
  m=copy.deepcopy(n['meta']);del m['major_variants'][0]['differences']['tempo']
  with self.assertRaises(ValueError):tactics.validate(m,lambda _:None,n['claims'])
 def test_dangling_claim_or_removed_composition_rejected(self):
  n=note()
  for key in ('condition_refs','baseline_refs','claim_refs','late_variant_ids','operation_route_ids'):
   m=copy.deepcopy(n['meta']);m['major_variants'][0][key]=['absent']
   with self.assertRaises(ValueError):tactics.validate(m,lambda _:None,n['claims'])
 def test_remap_nested_refs_and_clear_marks_unknown(self):
  m=note()['meta'];tactics.remap_claims(m,{'change'},'manual')
  v=m['major_variants'][0];self.assertEqual(v['condition_refs'],['manual']);self.assertEqual(v['differences']['mechanism']['claim_refs'],['manual'])
  tactics.remap_claims(m,{'manual'},None)
  self.assertEqual(v['differences']['mechanism'],{'status':'unknown','claim_refs':[]})
 def test_all_lineups_share_reading_without_repeating_claims(self):
  from lineup_layout import reading_document
  n=note();document=reading_document(n);self.assertTrue(document['profile'])
  out=wxq.render_note(n,{})
  self.assertIn('## 主要变阵',out);self.assertLess(out.index('## 核心机制'),out.index('## 主要变阵'))
  for c in n['claims']:self.assertEqual(out.count(c['text']),1)
  self.assertEqual(out,'# '+n['title']+'\n\n'+''.join('## '+s['title']+'\n\n'+s['markdown'] for s in document['sections']))
 def test_empty_major_variants_do_not_promote_accessory_or_routes(self):
  n=note();n['meta']['major_variants']=[];n['claims'][1]['text']='决赛圈临时上太乙真人或钟馗应对单核'
  out=wxq.render_note(n,{})
  self.assertIn('暂无已确认的主要变阵',out);self.assertEqual(out.count(n['claims'][1]['text']),1)
 def test_schema_four_roundtrip_keeps_legacy_and_manual_protection(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);wxq.init_store(root);n=note();workspace.validate_meta(root,n['meta']);workspace.persist(root,[n])
   index=wxq.read_json(root/'knowledge/index.json');self.assertEqual(index['schema_version'],4)
   stored=index['notes'][0];self.assertEqual(stored['meta']['major_variants'],n['meta']['major_variants'])
   stored['manual_meta']=True
   incoming=copy.deepcopy(stored);incoming['meta']['major_variants']=[]
   merged=workspace.merge_note(stored,incoming);self.assertEqual(merged['meta']['major_variants'],stored['meta']['major_variants'])
 def test_legacy_import_without_new_field_preserves_existing_major_variants(self):
  n=note();incoming=copy.deepcopy(n);del incoming['meta']['major_variants']
  self.assertEqual(workspace.merge_note(n,incoming)['meta'].get('major_variants'),n['meta']['major_variants'])
 def test_reference_links_follow_real_chapters_with_nested_routes(self):
  from lineup_layout import reading_document
  n=note();n['meta']['operation_routes']=[{'id':'r','name':'既有路线','condition':'条件','advantages':'优势','risks':'风险','transition':'转向','variant_ids':[],'claim_refs':['base'],'phases':{'early':['base'],'middle':[],'late':[]}}]
  document=reading_document(n);titles={s['id']:s['title'] for s in document['sections']}
  import re
  for section in document['sections']:
   for label,anchor in re.findall(r'\[([^\]]+)\]\(#(chapter-\d+)\)',section['markdown']):self.assertEqual(titles[anchor],label)
