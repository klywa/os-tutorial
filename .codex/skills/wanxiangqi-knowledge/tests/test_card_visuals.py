import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)

    def test_image_cache_deduplicates_and_preserves_previous_on_failure(self):
        from card_images import sync_images, image_fields, image_file
        rows = [{'id': 'card:1', 'properties': {'thumb': 'https://game.gtimg.cn/a.png', 'cardImage':'https://game.gtimg.cn/a.png'}}]
        png = b'\x89PNG\r\n\x1a\nfixture'
        with patch('card_images.fetch_image', return_value=png) as fetch:
            self.assertEqual(sync_images(self.root, rows)['downloaded'], 1)
            self.assertEqual(sync_images(self.root, rows)['downloaded'], 0)
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(image_file(self.root, 'card:1', 'thumb').read_bytes(), png)
        rows[0]['properties']['thumb'] = 'https://game.gtimg.cn/b.png'
        with patch('card_images.fetch_image', side_effect=OSError('offline')):
            self.assertTrue(sync_images(self.root, rows)['errors'])
        self.assertEqual(image_fields(self.root, 'card:1')['image_status'], 'ready')
        self.assertEqual(image_file(self.root, 'card:1', 'thumb').read_bytes(), png)
        with self.assertRaises(KeyError):
            image_file(self.root, '../secrets', 'thumb')

    def test_overview_validates_members_and_remaps_references(self):
        import overview
        from tactics import references, remap_claims
        meta = {'players': [], 'compositions': {'early': [], 'middle': [], 'late':[{'hero':'card:1','necessity':'required'}]}}
        data = overview.default_overview(meta)
        preset = data['presets'][0]
        preset['placements'] = [{'hero':'card:1','row':0,'col':0,'equipment':['card:2']}]
        preset['stages']['late']['claim_refs'] = ['claim-a']
        meta['overview'] = data
        rows = [{'id':'card:1','category':'heroes'}, {'id':'card:2','category':'equipment'}]
        overview.validate(meta, rows, [{'id':'claim-a'}])
        self.assertIn('card:2', references(meta))
        remap_claims(meta, ['claim-a'], 'claim-b')
        self.assertEqual(preset['stages']['late']['claim_refs'], ['claim-b'])
        bad = deepcopy(meta)
        bad['overview']['presets'][0]['placements'][0]['col'] = 7
        with self.assertRaises(ValueError): overview.validate(bad, rows)
        bad = deepcopy(meta)
        bad['overview']['presets'][0]['placements'][0]['hero'] = 'card:2'
        with self.assertRaises(ValueError): overview.validate(bad, rows)
        meta['compositions']['late'] = []
        with self.assertRaises(ValueError): overview.validate(meta, rows)

    def test_overview_save_claim_edit_and_dependency_projection(self):
        import workspace
        from overview import default_overview
        wxq.atomic_json(self.root/'entities/heroes.json', [{'id':'card:1','name':'英雄','category':'heroes','properties':{'type':1},'sources':[]}])
        wxq.atomic_json(self.root/'entities/equipment.json', [{'id':'card:2','name':'装备','category':'equipment','properties':{'type':5},'sources':[]}])
        wxq.commit_notes(self.root, [{'id':'visual-fixture','type':'lineup','title':'概览验收','claims':[],'entities':[]}])
        note=workspace.notes(self.root)[0]
        note=workspace.edit(self.root,note['id'],{'revision':note['revision'],'sections':{'知识内容':'原有建议'}})
        meta=deepcopy(note['meta'])
        meta['compositions']['late']=[{'hero':'card:1','necessity':'required','role':'','replaces':'','replacement_note':''}]
        meta['overview']=default_overview(meta)
        meta['overview']['presets'][0]['placements']=[{'hero':'card:1','row':0,'col':0,'equipment':['card:2']}]
        meta['overview']['presets'][0]['stages']['late']['claim_refs']=[note['claims'][0]['id']]
        saved=workspace.edit(self.root,note['id'],{'revision':note['revision'],'meta':meta})
        self.assertIn('card:2',saved['entities'])
        updated=workspace.edit(self.root,saved['id'],{'revision':saved['revision'],'sections':{'知识内容':'人工修改后的建议'},'meta':deepcopy(saved['meta'])})
        self.assertEqual(updated['meta']['overview']['presets'][0]['stages']['late']['claim_refs'],[updated['claims'][0]['id']])
        with self.assertRaises(workspace.Conflict):
            workspace.edit(self.root,saved['id'],{'revision':saved['revision'],'meta':meta})
        self.assertEqual(workspace.notes(self.root)[0]['meta']['overview'],updated['meta']['overview'])

    def test_overview_defaults_keep_variants_separate(self):
        from overview import default_overview
        meta = {'late_variants':[{'id':'one','name':'甲','members':[{'hero':'card:1'}]}, {'id':'two','name':'乙','members':[{'hero':'card:2'}]}]}
        result = default_overview(meta)
        self.assertEqual([p['variant_id'] for p in result['presets']], ['one','two'])
        self.assertTrue(all(not p['placements'] for p in result['presets']))
        self.assertNotIn('overview', meta)
