import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import wxq


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).parents[4] / '.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)
        self.store = importlib.import_module('reference_store')

    def hero(self, eid='card:1', faction=321, awake=False):
        return {'id': eid, 'category': 'heroes', 'name': '英雄', 'aliases': [],
                'description': '图腾成长', 'sources': ['https://example.com/official'],
                'retrieved_at': '2026-10-10', 'version': None,
                'properties': {'type': 9 if awake else 1, 'quality': 4,
                    'relationID': faction, 'relationName': '大河流域',
                    'heroCard': None if awake else {'awakeingCard': {'id': 3},
                        'skillList': [{'id': 10, 'name': '技能', 'desc': '<b>伤害</b>',
                            'enhanceSkill': {'params': [{'level': 40, 'desc': '强化'}]}}],
                        'properties': {'HP': 330, 'attackSpeed': 6000,
                            'criticalRate': 2500, 'criticalEffect': 4000}}}}

    def test_card_units_and_awakened_skill_provenance(self):
        cards = self.store.normalize_cards([self.hero(), self.hero('card:3', awake=True)])
        first, awakened = cards
        self.assertEqual(first['faction']['id'], 'faction:dahe')
        self.assertEqual(first['stats']['攻击速度'], 0.6)
        self.assertEqual(first['stats']['暴击率'], '25%')
        self.assertEqual(first['stats']['暴击效果'], '140%')
        self.assertEqual(awakened['skills_source'], 'card:1')
        self.assertEqual(awakened['skills'][0]['effect'], '伤害')
        self.assertEqual(awakened['stats'], {})

    def test_awakened_card_without_nested_link_uses_unique_official_counterpart(self):
        first = self.hero(); first['properties']['heroCard']['awakeingCard'] = None
        cards = self.store.normalize_cards([first, self.hero('card:3', awake=True)])
        self.assertEqual(cards[1]['skills_source'], 'card:1')
        self.assertIn('对应普通英雄', self.store.render_card(cards[1]))

    def test_critical_support_but_not_optional_or_early_faction(self):
        rows = [self.hero(), self.hero('card:2', 320), self.hero('card:4', 319)]
        meta = {'core_heroes': ['card:1'], 'required_factions': [], 'ban_conditions': [],
                'compositions': {'early': [{'hero': 'card:4', 'necessity': 'required'}],
                    'middle': [{'hero': 'card:2', 'necessity': 'required', 'role': '炸盾'}],
                    'late': [{'hero': 'card:4', 'necessity': 'optional'}]}}
        result = self.store.enrich_meta(meta, rows)
        self.assertEqual(result['required_factions'], ['faction:dahe', 'faction:zhulu'])
        self.assertTrue(all(c['status'] == 'unplayable' for c in result['ban_conditions']))
        self.assertIn('炸盾', result['ban_conditions'][1]['reason'])

    def test_catalog_export_idempotent_and_keeps_effect(self):
        wxq.atomic_json(self.root / 'entities/heroes.json', [self.hero()])
        self.store.export_cards(self.root)
        data = (self.root / 'knowledge/cards/index.json').read_bytes()
        self.store.export_cards(self.root)
        self.assertEqual(data, (self.root / 'knowledge/cards/index.json').read_bytes())
        self.assertIn('图腾成长', next((self.root / 'knowledge/cards').glob('heroes/*.md')).read_text('utf8'))

    def test_partial_official_failure_preserves_existing_reference(self):
        from unittest.mock import patch
        from official import sync_official
        wxq.atomic_json(self.root / 'entities/heroes.json', [self.hero()])
        with patch('official.fetch', side_effect=OSError('network unavailable')):
            result = sync_official(self.root)
        self.assertTrue(result['errors'])
        self.assertEqual(wxq.read_json(self.root / 'knowledge/cards/index.json')['cards'][0]['id'], 'card:1')

    def test_pending_entity_remains_readable_without_official_identity(self):
        row = self.hero('pending:heroes:未知英雄'); row['status'] = 'pending'
        wxq.atomic_json(self.root / 'entities/heroes.json', [row])
        self.store.export_cards(self.root)
        card = wxq.read_json(self.root / 'knowledge/cards/index.json')['cards'][0]
        self.assertEqual(card['status'], 'pending')
        self.assertEqual(card['id'], 'pending:heroes:未知英雄')

    def test_dependency_enrichment_is_idempotent(self):
        meta = {'core_heroes': ['card:1'], 'required_factions': [], 'compositions': {},
                'ban_conditions': [{'faction': 'faction:dahe', 'status': 'unknown', 'reason': '原备注'}]}
        first = self.store.enrich_meta(meta, [self.hero()])
        self.assertEqual(first, self.store.enrich_meta(first, [self.hero()]))

    def test_optional_member_clears_derived_dependency_and_restores_explicit_condition(self):
        meta = {'core_heroes': ['card:1'], 'required_factions': [],
                'compositions': {'middle': [{'hero': 'card:2', 'necessity': 'required'}]},
                'ban_conditions': [{'faction': 'faction:zhulu', 'status': 'playable', 'reason': '已有替代方案'}]}
        rows = [self.hero(), self.hero('card:2', 320)]
        result = self.store.enrich_meta(meta, rows)
        result['compositions']['middle'][0]['necessity'] = 'optional'
        result = self.store.enrich_meta(result, rows)
        self.assertEqual(result['required_factions'], ['faction:dahe'])
        self.assertEqual(next(c for c in result['ban_conditions'] if c['faction'] == 'faction:zhulu'),
                         meta['ban_conditions'][0])

    def test_transcript_validation_tracks_metadata_and_correction_inputs(self):
        folder = self.source()
        self.store.export_transcripts(self.root)
        wxq.atomic_json(folder / 'corrections.json', [{'segment': 1, 'original': '词',
            'candidate': '候选', 'status': 'ambiguous'}])
        self.assertTrue(self.store.transcript_errors(self.root, 'BV1:p1'))
        self.store.export_transcripts(self.root)
        self.assertFalse(self.store.transcript_errors(self.root, 'BV1:p1'))
        metadata = wxq.read_json(folder / 'metadata.json'); metadata['title'] = '修订标题'
        wxq.atomic_json(folder / 'metadata.json', metadata)
        self.assertTrue(self.store.transcript_errors(self.root, 'BV1:p1'))

    def source(self):
        f = wxq.source_dir(self.root, 'BV1:p1'); f.mkdir(parents=True)
        wxq.atomic_json(f / 'metadata.json', {'id': 'BV1:p1', 'title': '视频', 'part': 1,
                                             'url': 'https://www.bilibili.com/video/BV1', 'duration': 35})
        wxq.atomic_json(f / 'state.json', {'stage': 'complete'})
        segments = [{'id': 1, 'start': 0, 'end': 5, 'text': '刘邦'},
                    {'id': 2, 'start': 30, 'end': 35, 'text': '当局买牌'}]
        wxq.atomic_json(f / 'asr.raw.json', {'segments': segments})
        wxq.atomic_json(f / 'asr.corrected.json', {'segments': segments})
        return f

    def test_transcript_full_text_gaps_idempotence_and_manual_protection(self):
        f = self.source(); original = (f / 'asr.raw.json').read_bytes()
        self.store.export_transcripts(self.root)
        p = self.root / 'raw/BV1_p1.md'; text = p.read_text('utf8')
        self.assertIn('当局买牌', text); self.assertIn('00:30', text)
        self.assertIn('转写间隔', text)
        self.store.export_transcripts(self.root); self.assertEqual(text, p.read_text('utf8'))
        p.write_text(text + '人工修改', encoding='utf8')
        result = self.store.export_transcripts(self.root)
        self.assertTrue(result['errors']); self.assertTrue(p.read_text('utf8').endswith('人工修改'))
        self.assertEqual(original, (f / 'asr.raw.json').read_bytes())

    def test_transcript_rejects_invalid_time_order(self):
        f = self.source()
        wxq.atomic_json(f / 'asr.corrected.json', {'segments': [
            {'start': 4, 'end': 2, 'text': '错误'}]})
        self.assertTrue(self.store.export_transcripts(self.root)['errors'])
        self.assertFalse((self.root / 'raw/BV1_p1.md').exists())

    def test_decoder_boundary_overlap_is_preserved(self):
        f = self.source()
        wxq.atomic_json(f / 'asr.corrected.json', {'segments': [
            {'start': 0, 'end': 5.14, 'text': '上段'},
            {'start': 5, 'end': 8, 'text': '下段'}]})
        result = self.store.export_transcripts(self.root)
        self.assertFalse(result['errors'])
        self.assertIn('00:05.00', (self.root / 'raw/BV1_p1.md').read_text('utf8'))

    def test_finish_requires_current_exported_transcript(self):
        from media import finish
        f = self.source(); wxq.atomic_json(f / 'state.json', {'stage': 'prepared'})
        wxq.atomic_json(f / 'review.json', {'approved': True, 'checked_intervals': [[0, 35]]})
        wxq.commit_notes(self.root, [{'id': 'topic', 'type': 'other', 'title': '知识',
            'entities': [], 'claims': [{'section': '知识内容', 'text': '机制', 'kind': 'mechanic',
            'version': None, 'condition': '', 'inference': False,
            'evidence': [{'source': 'BV1:p1', 'start': 0, 'end': 5}]}]}])
        with self.assertRaisesRegex(ValueError, 'Missing exported transcript'):
            finish(self.root, 'BV1:p1')
        self.store.export_transcripts(self.root, ['BV1:p1'])
        self.assertEqual(finish(self.root, 'BV1:p1')['stage'], 'complete')


if __name__ == '__main__':
    unittest.main()
