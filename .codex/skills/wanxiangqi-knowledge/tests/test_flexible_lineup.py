import unittest
import tempfile
from pathlib import Path
from copy import deepcopy
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import wxq, workspace
from reference_store import enrich_meta

class FlexibleLineupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)
        self.claim = {'id':'growth','section':'核心机制','text':'测试条件策略','kind':'conditional_strategy','condition':'测试','evidence':[]}
        self.meta = workspace.default_meta({'core':[]})
        self.meta.update(operation_routes=[{'id':'steady','name':'稳健节奏','condition':'测试条件','advantages':'稳定','risks':'成型较慢','transition':'质量不足时调整','phases':{'early':['growth'],'middle':[],'late':[]},'claim_refs':['growth'],'variant_ids':['a','b']}], late_variants=[
            {'id':'a','name':'甲组合','condition':'获得甲','members':[{'hero':'pending:甲','necessity':'required','role':'输出','replaces':'','replacement_note':''}],'core_heroes':['pending:甲'],'required_factions':['faction:dahe'],'ban_conditions':[{'faction':'faction:sanfen','status':'playable','reason':'确认可用'}],'ban_combinations':[],'claim_refs':['growth']},
            {'id':'b','name':'乙组合','condition':'获得乙','members':[{'hero':'pending:乙','necessity':'required','role':'输出','replaces':'','replacement_note':''}],'core_heroes':['pending:乙'],'required_factions':['faction:sanfen'],'ban_conditions':[{'faction':'faction:dahe','status':'playable','reason':'确认可用'}],'ban_combinations':[],'claim_refs':['growth']}])
        self.note = {'id':'flexible','title':'测试通用打法','type':'lineup','core':[],'entities':[],'claims':[self.claim],'meta':self.meta,'related':[]}


    def test_reimport_corrected_explicit_claim_updates_in_place(self):
        old={'id':'stable','section':'阵容组成','text':'先前描述','kind':'general_strategy','evidence':[{'source':'old:p1','start':1,'end':2}]}
        revised={**old,'text':'经核对的修正描述','evidence':[{'source':'old:p1','start':3,'end':4}]}
        merged=workspace.merge_note({'claims':[old]}, {'claims':[revised]})
        self.assertEqual(merged['claims'],[revised])
        protected=workspace.merge_note({'claims':[old],'manual_sections':['阵容组成']}, {'claims':[revised]})
        self.assertEqual(protected['claims'],[old])
        self.assertEqual(protected['conflicts'][0]['kind'],'section')

    def test_reimport_correction_keeps_history_and_rejects_new_strategy_under_same_id(self):
        old={'id':'stable','section':'阵容组成','text':'原结论','version':'v1','condition':'条件甲','kind':'conditional_strategy','evidence':[{'source':'old:p1','start':1,'end':2}]}
        revised={**old,'text':'核对后的修正文案'}
        merged=workspace.merge_note({'claims':[old]}, {'claims':[revised]})
        self.assertEqual(merged['history'][0]['previous']['claims'],[old])
        for changed in ({'version':'v2'},{'condition':'条件乙'},{'evidence':[{'source':'new:p1','start':3,'end':4}]}):
            with self.assertRaises(ValueError):
                workspace.merge_note({'claims':[old]}, {'claims':[{**revised,**changed}]})

    def test_malformed_relationship_and_ban_metadata_rejected(self):
        import tactics
        cases=[]
        for value in ([{}], [None], [3]):
            broken=deepcopy(self.meta)
            broken['operation_routes'][0]['variant_ids']=value
            cases.append(broken)
        for field,value in [('reason',[]),('factions',[{}])]:
            broken=deepcopy(self.meta)
            broken['late_variants'][0]['ban_combinations']=[{'factions':['faction:dahe'],'status':'unknown','reason':'待确认',field:value}]
            cases.append(broken)
        for broken in cases:
            with self.assertRaises(ValueError):
                tactics.validate(broken,lambda ref: None,[self.claim])

    def test_finish_cleanup_failure_does_not_mark_source_complete(self):
        import media
        from unittest.mock import patch
        folder=wxq.source_dir(self.root,'cleanup:p1')
        folder.mkdir(parents=True,exist_ok=True)
        wxq.atomic_json(folder/'review.json',{'approved':True,'checked_intervals':[[1,2]]})
        wxq.atomic_json(folder/'state.json',{'stage':'prepared'})
        wxq.atomic_json(folder/'asr.raw.json',{})
        wxq.atomic_json(folder/'asr.corrected.json',{})
        wxq.atomic_json(self.root/'knowledge/index.json',{'notes':[{'claims':[{'evidence':[{'source':'cleanup:p1','start':1,'end':2}]}]}]})
        with patch('reference_store.transcript_errors',return_value=[]), patch.object(Path,'unlink',side_effect=PermissionError('file busy')):
            with self.assertRaises(PermissionError):
                media.finish(self.root,'cleanup:p1')
        self.assertEqual(wxq.read_json(folder/'state.json')['stage'],'prepared')

    def test_condition_render_has_only_one_temporal_suffix(self):
        note={**self.note,'claims':[{**self.claim,'condition':'资源充足时'}]}
        rendered=wxq.render_note(note,{})
        self.assertIn('当资源充足时，',rendered)
        self.assertNotIn('资源充足时时',rendered)

    def test_missing_tactics_record_fields_rejected_before_save(self):
        import tactics
        for kind,fields in [('operation_routes',('claim_refs','variant_ids','condition','advantages','risks','transition')),('late_variants',('claim_refs','core_heroes','required_factions','ban_conditions','ban_combinations','condition'))]:
            for field in fields:
                broken=deepcopy(self.meta)
                del broken[kind][0][field]
                with self.assertRaises(ValueError):
                    tactics.validate(broken,lambda ref: None,[self.claim])

    def test_one_blocked_variant_does_not_hide_other_route(self):
        self.assertEqual(workspace.availability(self.note,['faction:dahe']),'playable')
        self.assertEqual(workspace.availability(self.note,['faction:dahe','faction:sanfen']),'unplayable')
        self.assertEqual(workspace.availability(self.note,['faction:zhulu']),'unknown')

    def test_multiple_individually_supported_bans_need_joint_evidence(self):
        self.meta['late_variants'][0]['ban_conditions'].append({'faction':'faction:zhulu','status':'playable','reason':'单独确认'})
        self.assertEqual(workspace.availability(self.note,['faction:sanfen','faction:zhulu']),'unknown')
        self.meta['late_variants'][0]['ban_combinations']=[{'factions':['faction:sanfen','faction:zhulu'],'status':'playable','reason':'联合确认'}]
        self.assertEqual(workspace.availability(self.note,['faction:sanfen','faction:zhulu']),'playable')

    def test_shared_dependency_cannot_be_overridden(self):
        self.meta['required_factions']=['faction:dahe']
        self.assertEqual(workspace.availability(self.note,['faction:dahe']),'unplayable')

    def test_edit_roundtrip_and_manual_protection(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        changed=deepcopy(current['meta'])
        changed['operation_routes'][0]['risks']='人工风险说明'
        saved=workspace.edit(self.root,current['id'],{'revision':current['revision'],'meta':changed})
        self.assertEqual(workspace.notes(self.root)[0]['meta'],changed)
        self.assertEqual(wxq.read_json((self.root / saved['path']).with_suffix('.json'))['meta'],changed)
        merged=workspace.merge_note(saved,self.note)
        self.assertEqual(merged['meta']['operation_routes'][0]['risks'],'人工风险说明')
        self.assertTrue(merged['conflicts'])
        text=(self.root / saved['path']).read_text(encoding='utf-8')
        self.assertIn('稳健节奏',text)
        self.assertIn('甲组合',text)
        self.assertNotIn('growth',text)
        before=(self.root / 'knowledge/index.json').read_bytes()
        workspace.migrate(self.root)
        self.assertEqual(before,(self.root / 'knowledge/index.json').read_bytes())

    def test_invalid_claim_and_variant_references_rejected(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        for field,value in [('claim_refs',['missing']),('variant_ids',['missing'])]:
            broken=deepcopy(current['meta'])
            broken['operation_routes'][0][field]=value
            with self.assertRaises(ValueError):
                workspace.edit(self.root,current['id'],{'revision':current['revision'],'meta':broken})

    def test_variant_dependencies_stay_local(self):
        self.meta['late_variants'][0]['required_factions']=[]
        heroes=[{'id':'pending:甲','name':'甲','category':'heroes','properties':{'relationID':321}}]
        result=enrich_meta(self.meta,heroes)
        self.assertEqual(result['required_factions'],[])
        self.assertIn('faction:dahe',result['late_variants'][0]['required_factions'])

    def test_unknown_entity_and_duplicate_variant_rejected(self):
        for mutation in ['unknown','duplicate']:
            broken=deepcopy(self.meta)
            if mutation=='unknown': broken['late_variants'][0]['members'][0]['hero']='card:no-such-card'
            else: broken['late_variants'][1]['id']='a'
            with self.assertRaises(ValueError): workspace.validate_meta(self.root,broken)

    def test_section_edit_preserves_and_protects_route_references(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        saved=workspace.edit(self.root,current['id'],{'revision':current['revision'],'sections':{'核心机制':'人工替换建议'},'meta':deepcopy(current['meta'])})
        refs=saved['meta']['operation_routes'][0]['phases']['early']
        self.assertEqual(len(refs),1)
        self.assertEqual(next(c['text'] for c in saved['claims'] if c.get('id')==refs[0]),'人工替换建议')
        merged=workspace.merge_note(saved,self.note)
        self.assertEqual(merged['meta']['operation_routes'][0]['phases']['early'],refs)

    def test_recovery_preserves_new_metadata(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        wxq.atomic_json(self.root / 'knowledge/pending-save.json',{'index':{'schema_version':3,'notes':[current]},'obsolete':[]})
        workspace.recover(self.root)
        self.assertEqual(workspace.notes(self.root)[0]['meta']['late_variants'][0]['name'],'甲组合')
        self.assertFalse((self.root / 'knowledge/pending-save.json').exists())

    def test_semantic_dedup_remaps_incoming_claim_ids(self):
        folder=wxq.source_dir(self.root,'BVTEST:p1')
        wxq.atomic_json(folder / 'metadata.json',{'id':'BVTEST:p1','url':'https://www.bilibili.com/video/BVTEST','duration':10})
        for name in ['asr.raw.json','asr.corrected.json']:
            wxq.atomic_json(folder / name,{'segments':[{'start':0,'end':5,'text':'模拟测试来源'}]})
        self.claim['evidence']=[{'source':'BVTEST:p1','start':0,'end':5}]
        wxq.commit_notes(self.root,[self.note])
        incoming=deepcopy(self.note)
        incoming['claims'][0]['id']='incoming-growth'
        for route in incoming['meta']['operation_routes']:
            route['claim_refs']=['incoming-growth']
            route['phases']['early']=['incoming-growth']
        for variant in incoming['meta']['late_variants']: variant['claim_refs']=['incoming-growth']
        wxq.commit_notes(self.root,[incoming])
        saved=workspace.notes(self.root)[0]
        self.assertEqual(saved['meta']['operation_routes'][0]['phases']['early'],['growth'])
        self.assertEqual(len(saved['claims']),1)
        before=(self.root / 'knowledge/index.json').read_bytes()
        wxq.commit_notes(self.root,[incoming])
        self.assertEqual(before,(self.root / 'knowledge/index.json').read_bytes())

    def test_pending_heroes_are_not_faction_filters(self):
        self.meta['late_variants'][0]['ban_combinations']=[{'factions':['pending:联合阵营'],'status':'unknown','reason':'待确认'}]
        workspace.persist(self.root,[self.note])
        ids=[f['id'] for f in workspace.factions(self.root)]
        self.assertNotIn('pending:甲',ids)
        self.assertNotIn('pending:乙',ids)
        self.assertIn('pending:联合阵营',ids)

    def test_edit_without_meta_protects_remapped_references(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        saved=workspace.edit(self.root,current['id'],{'revision':current['revision'],'sections':{'核心机制':'新人工建议'}})
        merged=workspace.merge_note(saved,self.note)
        self.assertEqual(merged['meta'],saved['meta'])

    def test_tactics_export_preserves_inference_and_condition(self):
        from tactics import render
        self.claim['inference']=True
        text='\n'.join(render(self.meta,[self.claim],{}))
        self.assertIn('推测：测试条件策略',text)
        self.assertIn('适用条件：测试',text)

    def test_protected_sections_cannot_leave_dangling_import_references(self):
        workspace.persist(self.root,[self.note])
        current=workspace.notes(self.root)[0]
        current['manual_sections']=['核心机制']
        incoming=deepcopy(self.note)
        incoming['claims'][0]['id']='filtered'
        incoming['claims'][0]['text']='不同的新建议'
        incoming['meta']['operation_routes'][0]['phases']['early']=['filtered']
        merged=workspace.merge_note(current,incoming)
        from tactics import validate
        with self.assertRaises(ValueError):
            validate(merged['meta'],lambda ref:None,merged['claims'])

    def test_variant_heroes_participate_in_entity_associations(self):
        wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'card:100','name':'测试英雄','category':'heroes'}])
        self.meta['late_variants'][0]['members'][0]['hero']='card:100'
        self.meta['late_variants'][0]['core_heroes']=['card:100']
        workspace.persist(self.root,[self.note])
        saved=workspace.notes(self.root)[0]
        self.assertIn('card:100',saved['entities'])
        self.assertNotIn('card:100',saved['core'])
        self.assertEqual(wxq.related(self.root,['card:100'])[0]['id'],'flexible')
