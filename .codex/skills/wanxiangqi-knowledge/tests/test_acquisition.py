import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import acquisition
import reference_store


class AcquisitionTests(unittest.TestCase):
    def test_removing_a_route_retains_catalog_acquisition_node_id(self):
        import json_store
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[4]/'.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);json_store.save(root,[])
            cards=reference_store.normalize_cards(self.rows())
            original=json.loads(json.dumps(cards))
            original[0]['routes'].append(dict(text='梦奇提供兑换券。',evidence_ids=[],kind='hero',requires_names=['梦奇']))
            reference_store.save_json_cards(root,original)
            path=root/'knowledge/cards/heroes/露娜－card-1.json'
            before=json.loads(path.read_text('utf-8'))
            reference_store.save_json_cards(root,cards)
            after=json.loads(path.read_text('utf-8'))
            old=next(n for n in before['nodes'] if n.get('key')=='获得途径')
            new=next(n for n in after['nodes'] if n.get('key')=='获得途径')
            self.assertEqual(old['id'],new['id'])
            self.assertNotIn('梦奇',new['value'])

    def test_mengqi_is_excluded_as_acquisition_but_voucher_and_own_effect_remain(self):
        rows=self.rows()+[dict(id='card:9',name='梦奇',category='heroes',
            description='退场：获得1张1阶英雄兑换券。',properties=dict(type=1,quality=1,relationID=307))]
        result=acquisition.build(rows)
        for cid in ('card:1','card:2','card:3','card:4'):
            self.assertTrue(all('梦奇' not in r['text'] and '梦奇' not in r['requires_names']
                                and 'card:9' not in r['evidence_ids'] for r in result[cid]['routes']))
        self.assertTrue(any('5阶英雄兑换券' in r['text'] for r in result['card:1']['routes']))
        self.assertIn('合成',result['card:2']['routes'][0]['text'])
        self.assertIn('兑换券',result['card:9']['other_uses'])
        for _ in range(2):
            cards=reference_store.normalize_cards(rows)
            luna=next(c for c in cards if c['id']=='card:1')
            self.assertNotIn('梦奇',reference_store.render_card(luna))
            self.assertIn('5阶英雄兑换券',reference_store.render_card(luna))

    def test_fixed_source_card_is_not_confused_with_combat_copy(self):
        rows=self.rows()
        rows[0]['properties']['sourceCards']=[dict(id=20,name='宝盒',desc='获得1张露娜和1张孙悟空。'),dict(id=21,name='升格',desc='召唤物变为其召唤者（无卡牌效果）。')]
        rows.append(dict(id='card:20',name='宝盒',category='talents',description='获得1张露娜和1张孙悟空。',properties={}))
        routes=acquisition.build(rows)['card:1']['routes']
        self.assertTrue(any(r['kind']=='fixed' and '宝盒' in r['text'] for r in routes))
        self.assertFalse(any('升格' in r['text'] for r in routes))

    def test_document_snapshot_hash_is_reused_until_file_changes(self):
        import json_store
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[4]/'.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);(root/'knowledge').mkdir()
            refs=acquisition.register_snapshot(root,self.rows())
            original=Path.read_bytes
            with patch.object(Path,'read_bytes',autospec=True,side_effect=original) as reader:
                json_store.check_evidence(root,refs['card:1'])
                json_store.check_evidence(root,refs['card:3'])
            self.assertEqual(reader.call_count,2)
    def test_updated_card_effect_retains_node_identity(self):
        import json_store
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[4]/'.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);json_store.save(root,[])
            cards=reference_store.normalize_cards(self.rows())
            reference_store.save_json_cards(root,cards)
            path=root/'knowledge/cards/heroes/露娜－card-1.json'
            before=json.loads(path.read_text('utf-8'))
            old=next(n for n in before['nodes'] if n.get('value','').startswith('闪现\n'))
            cards[0]['effect']='闪现\n登场：随机触发3名英雄的整备效果。'
            reference_store.save_json_cards(root,cards)
            after=json.loads(path.read_text('utf-8'))
            new=next(n for n in after['nodes'] if n.get('value','').startswith('闪现\n'))
            self.assertEqual(new['id'],old['id'])
    def rows(self):
        def row(cid,name,category,desc,**props):
            return dict(id=cid,name=name,category=category,description=desc,properties=props,
                        sources=['https://example.com/official'],status='official')
        return [row('card:1','露娜','heroes','闪现\n登场：随机触发2名英雄的整备效果。',type=1,quality=5,relationID=314),
                row('card:2','露娜','heroes','闪现\n登场：随机触发4名英雄的整备效果。',type=9,quality=5,relationID=314),
                row('card:3','甄姬','heroes','登场：获得1张其他的登场英雄牌。',type=1,quality=4,relationID=309),
                row('card:4','曹操','heroes','整备：随机触发1名【三分】英雄的登场效果。',type=1,quality=2,relationID=309),
                row('card:5','闪现突击者','effect-cards','获得2张具有闪现效果的英雄牌。'),
                row('card:6','5阶英雄兑换券','effect-cards','卡牌3选1（5阶英雄牌）。'),
                row('card:7','唤醒','effect-cards','指定1名英雄，触发其登场效果。'),
                row('card:8','临阵磨枪','effect-cards','指定1名英雄，触发其整备效果。')]

    def test_random_routes_and_indirect_generators_have_real_dependencies(self):
        result=acquisition.build(self.rows())
        routes=result['card:1']['routes']
        self.assertTrue(any('闪现突击者' in r['text'] and '有机会' in r['text'] for r in routes))
        chain=next(r for r in routes if '曹操' in r['text'])
        self.assertIn('唤醒',chain['text']);self.assertIn('临阵磨枪',chain['text'])
        self.assertIn('card:3',chain['evidence_ids']);self.assertIn('card:4',chain['evidence_ids'])
        self.assertIn('露娜',result['card:3']['other_uses'])
        self.assertIn('甄姬',result['card:4']['other_uses'])

    def test_awakened_is_not_assumed_in_random_normal_pools(self):
        result=acquisition.build(self.rows())
        self.assertFalse(any('闪现突击者' in r['text'] for r in result['card:2']['routes']))
        self.assertIn('合成',result['card:2']['routes'][0]['text'])

    def test_catalog_sync_regenerates_enrichment_and_keeps_meta_private(self):
        cards=reference_store.normalize_cards(self.rows())
        luna=next(c for c in cards if c['id']=='card:1')
        text=reference_store.render_card(luna)
        self.assertIn('获得途径',text);self.assertIn('闪现突击者',text)
        self.assertNotIn('同步日期',text);self.assertNotIn('游戏版本',text)
        self.assertEqual(cards,reference_store.normalize_cards(self.rows()))

    def test_snapshot_is_real_content_addressed_document_evidence(self):
        import json_store
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[4]/'.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);(root/'knowledge').mkdir()
            refs=acquisition.register_snapshot(root,self.rows())
            json_store.check_evidence(root,refs['card:1'])
            self.assertEqual(refs,acquisition.register_snapshot(root,self.rows()))
            artifact=next((root/'raw/documents').rglob('official-cards.json'))
            artifact.write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):json_store.check_evidence(root,refs['card:1'])

    def test_unknown_card_does_not_invent_acquisition(self):
        self.assertEqual(acquisition.build([dict(id='pending:x',category='heroes',name='未知',properties={},description='')])['pending:x']['routes'],[])
