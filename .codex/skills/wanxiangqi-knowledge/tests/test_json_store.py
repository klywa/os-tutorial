import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json_document
import json_store


class StoreTests(unittest.TestCase):
    def test_edit_retains_route_display_identity_and_original_evidence(self):
        record = self.record
        body = record['body'] = json_document.parse('# 测试\n\n## 前期\n\n**开局：** 路线原文\n')
        entry = body['nodes'][-1]
        body['supporting_nodes'] = [{'id':'support','type':'entry','key':'正文','show_key':False,'value':'路线原文'}]
        record['metadata']['claim_annotations'] = [{'id':'c','text_ref':'support','section':'前期','evidence':[{'source':'s'}]}]
        json_store.save(self.root, [record])
        note = json_store.notes(self.root)[0]
        note['document']['nodes'][-1]['value'] = '新路线原文'
        updated = json_store.edit(self.root, 'test', {'revision':note['revision'],'document':note['document']})
        claim = updated['claims'][0]
        self.assertEqual(claim['display_ref'], entry['id'])
        self.assertEqual(claim['text_ref'], 'support')
        self.assertEqual(claim['text'], '路线原文')
        self.assertEqual(claim['evidence'], [{'source':'s'}])
        self.assertEqual(json_document.claim_display_refs(updated['document'], updated['claims']), {'c':entry['id']})

    def setUp(self):
        folder = Path(__file__).resolve().parents[4] / 'raw/test-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.temp.name)
        self.record = {'body': json_document.parse('# 测试\n\n## 英雄\n\n**花木兰：** 原文。\n'),
                       'metadata': {'id': 'test', 'type': 'other', 'title': '测试', 'path': 'knowledge/other/测试.json', 'claims': []}}

    def tearDown(self):
        self.temp.cleanup()

    def test_light_index_and_body_metadata_separation(self):
        json_store.save(self.root, [self.record])
        index = json.loads((self.root / 'knowledge/index.meta.json').read_text('utf-8'))
        self.assertNotIn('body', index['notes'][0])
        note = json_store.notes(self.root)[0]
        self.assertEqual(note['document']['nodes'][2]['value'], '原文。')
        self.assertEqual(json_store.validate(self.root)['errors'], [])
        self.assertTrue(all(p.suffix == '.json' for p in (self.root / 'knowledge').rglob('*') if p.is_file()))

    def test_recover_interrupted_pair_and_idempotence(self):
        original = json_store.write_file
        calls = []
        def fail(path, value):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated crash')
            return original(path, value)
        with patch.object(json_store, 'write_file', side_effect=fail):
            with self.assertRaises(OSError):
                json_store.save(self.root, [self.record])
        json_store.recover(self.root)
        before = {p: p.read_bytes() for p in (self.root / 'knowledge').rglob('*.json')}
        json_store.save(self.root, json_store.records(self.root))
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_edit_conflict_and_manual_provenance(self):
        json_store.save(self.root, [self.record])
        note = json_store.notes(self.root)[0]
        body = note['document']
        body['nodes'][2]['value'] = '修改。'
        saved = json_store.edit(self.root, 'test', {'revision': note['revision'], 'document': body})
        self.assertEqual(saved['document']['nodes'][2]['value'], '修改。')
        self.assertTrue(saved['history'])
        with self.assertRaises(ValueError):
            json_store.edit(self.root, 'test', {'revision': note['revision'], 'document': body})

    def test_visible_edit_updates_linked_claim_and_semantic_text(self):
        note = {'id':'linked','type':'other','title':'测试','path':'knowledge/other/测试.json',
                'claims':[{'id':'claim-one','section':'英雄','text':'原文。','kind':'general_strategy','evidence':[]}],
                'meta':{'description':'原文。'}}
        record = json_store.from_legacy(note, '# 测试\n\n## 英雄\n\n原文。\n')
        json_store.save(self.root, [record])
        old = json_store.notes(self.root)[0]
        body = old['document'];body['nodes'][2]['value'] = '新说明。'
        saved = json_store.edit(self.root, 'linked', {'revision':old['revision'],'document':body})
        self.assertEqual(saved['claims'][0]['text'], '新说明。')
        self.assertEqual(saved['claims'][0]['origin'], 'manual')
        self.assertEqual(saved['claims'][0].get('evidence', []), [])
        texts={n['id']:n.get('value','') for n in saved['document']['nodes']}
        self.assertEqual(json_store.resolve_value(saved['document']['semantics'],texts)['description'], '新说明。')

    def test_invalid_semantic_reference_is_rejected(self):
        self.record['body']['semantics'] = {'description': {'$text':'missing'}}
        with self.assertRaises(ValueError):
            json_store.save(self.root, [self.record])

    def test_history_is_flat_and_all_manual_changes_are_protected(self):
        self.record['body']['semantics'] = {'description':'原始条件'}
        json_store.save(self.root, [self.record])
        for i in range(5):
            old = json_store.notes(self.root)[0]
            body = old['document'];body['nodes'][1]['title'] = '章节'+str(i)
            body['semantics']['description'] = '条件'+str(i)
            json_store.edit(self.root, 'test', {'revision':old['revision'],'document':body})
        record = json_store.records(self.root)[0]
        self.assertEqual(len(record['metadata']['history']), 5)
        self.assertNotIn('history', record['metadata']['history'][-1]['previous']['metadata'])
        incoming = json.loads(json.dumps(record))
        incoming['body']['semantics']['description'] = '被覆盖'
        json_store.commit(self.root, [incoming])
        saved = json_store.notes(self.root)[0]
        self.assertEqual(saved['document']['semantics']['description'], '条件4')
        self.assertTrue(saved['conflicts'])

    def test_legacy_manual_claim_is_protected_without_node_annotations(self):
        note={'id':'manual','type':'other','title':'测试','path':'knowledge/other/测试.json',
              'claims':[{'id':'human','text':'手写结论','section':'英雄','origin':'manual','kind':'general_strategy'}]}
        record=json_store.from_legacy(note,'# 测试\n\n## 英雄\n\n手写结论\n')
        json_store.save(self.root,[record])
        incoming=json_store.records(self.root)[0]
        incoming['body']['nodes'][2]['value']='自动覆盖'
        json_store.commit(self.root,[incoming])
        self.assertEqual(json_store.notes(self.root)[0]['document']['nodes'][2]['value'],'手写结论')
        self.assertTrue(json_store.notes(self.root)[0]['conflicts'])

    def test_old_markdown_writes_are_rejected_and_registry_is_redirected(self):
        import wxq
        json_store.save(self.root,[self.record])
        with self.assertRaises(ValueError):wxq.atomic_text(self.root/'knowledge/other/错误.md','错误')
        wxq.atomic_json(self.root/'knowledge/source-registry.json',[{'id':'source'}])
        self.assertFalse((self.root/'knowledge/source-registry.json').exists())
        self.assertEqual(wxq.read_json(self.root/'knowledge/source-registry.json'),[{'id':'source'}])

    def test_schema6_card_export_is_json_only_and_roundtrips(self):
        import reference_store
        json_store.save(self.root,[self.record])
        card={'id':'card:1','name':'测试卡','category':'heroes','aliases':[],'awakened':False,'status':'official',
              'tier':1,'effect':'作用','skills':[],'skills_source':None,'stats':{},'attributes':{},
              'retrieved_at':None,'version':None,'sources':[],'faction':{'id':'none','name':'无'}}
        reference_store._save_cards(self.root,[card])
        loaded=reference_store.json_cards(self.root)[0]
        self.assertEqual(loaded['effect'],'作用')
        self.assertEqual(loaded['id'],'card:1')
        self.assertFalse(list((self.root/'knowledge').rglob('*.md')))

    def test_interrupted_migration_resumes_card_export_and_cleanup(self):
        import wxq, migrate_json_knowledge
        legacy={'id':'legacy','type':'other','title':'测试','path':'knowledge/other/测试.md','claims':[]}
        wxq.atomic_json(self.root/'knowledge/index.json',{'notes':[legacy]})
        wxq.atomic_text(self.root/legacy['path'],'# 测试\n\n原文。\n')
        with patch('reference_store._save_cards',side_effect=OSError('card export interrupted')):
            with self.assertRaises(OSError):migrate_json_knowledge.migrate(self.root,apply=True)
        result=migrate_json_knowledge.migrate(self.root,apply=True)
        self.assertEqual(result['validation']['errors'],[])
        self.assertFalse(list((self.root/'knowledge').rglob('*.md')))
        self.assertFalse((self.root/'raw/knowledge/pending-json-migration.json').exists())

    def test_delete_evidenced_node_keeps_history_and_removes_current_reference(self):
        note={'id':'delete','type':'other','title':'测试','path':'knowledge/other/测试.json',
              'claims':[{'id':'original','section':'英雄','text':'原文。','kind':'general_strategy','evidence':[]}],
              'meta':{'description':'原文。'}}
        record=json_store.from_legacy(note,'# 测试\n\n## 英雄\n\n原文。\n')
        json_store.save(self.root,[record]);old=json_store.notes(self.root)[0]
        body=old['document'];body['nodes']=body['nodes'][:2]
        saved=json_store.edit(self.root,'delete',{'revision':old['revision'],'document':body})
        self.assertEqual(saved['claims'],[])
        self.assertEqual(saved['document']['semantics']['description'],'')
        current=json_store.records(self.root)[0]
        self.assertEqual(current['metadata']['retired_claim_annotations'][0]['id'],'original')
        self.assertEqual(current['metadata']['history'][-1]['previous']['body']['nodes'][2]['value'],'原文。')

    def test_commit_accepts_unchanged_legacy_gaps_but_requires_new_evidence(self):
        note={'id':'legacy-gap','type':'other','title':'测试','path':'knowledge/other/测试.json',
              'claims':[{'id':'gap','section':'英雄','text':'尚无统一停级点。','kind':'general_strategy','evidence':[]}]}
        record=json_store.from_legacy(note,'# 测试\n\n## 英雄\n\n尚无统一停级点。\n')
        json_store.save(self.root,[record])
        json_store.commit(self.root,json_store.records(self.root))
        incoming=json_store.records(self.root)[0]
        incoming['body']['nodes'].append({'id':'unsupported','type':'entry','key':'新结论','show_key':True,'value':'未经核实的规则。'})
        with self.assertRaises(ValueError):json_store.commit(self.root,[incoming])

    def test_fresh_initialization_is_json_only_and_refuses_existing_material(self):
        path=self.root/'knowledge/other/未迁移.md';path.parent.mkdir(parents=True);path.write_text('保留原文','utf-8')
        with self.assertRaises(ValueError):json_store.initialize(self.root)
        self.assertEqual(path.read_text('utf-8'),'保留原文')
        path.unlink()
        json_store.initialize(self.root)
        self.assertTrue(json_store.enabled(self.root))
        self.assertEqual(json_store.notes(self.root),[])
        self.assertFalse((self.root/'knowledge/index.json').exists())


if __name__ == '__main__':
    unittest.main()
