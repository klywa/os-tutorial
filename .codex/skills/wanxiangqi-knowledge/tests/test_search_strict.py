import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / 'frontend'))
from crawler import Runtime, config, title_keywords


class StrictSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Runtime(self.tmp.name)
        self.addCleanup(self.runtime.media_pool.shutdown, wait=False)
        self.addCleanup(self.runtime.scan_pool.shutdown, wait=False)
        self.store = self.runtime.store

    def row(self, n, title):
        return {'bvid': f'BV{n:010d}', 'title': title, 'description': '姜导 韩信',
                'published': '2026-10-18', 'view_count': 100, 'duration': 60}

    def scan(self, payload, pages, detail=None):
        job = self.store.new_job(payload)
        with patch('crawler.Bilibili') as adapter, patch('crawler.register_discovered') as register:
            adapter.return_value.search_page.side_effect = lambda k, p, o: pages[(k, p)]
            if detail:
                adapter.return_value.detail.side_effect = detail
            self.runtime.scan(job)
            return self.store.job(job['id']), adapter, register

    def test_title_all_words_or_html_case_and_no_description(self):
        keys = ['姜导 韩信', '大河龙蛇', 'ASR 教学']
        self.assertEqual(title_keywords('<em>韩信</em>的姜导教学', keys), ['姜导 韩信'])
        self.assertEqual(title_keywords('大河龙蛇&amp;教学', keys), ['大河龙蛇'])
        self.assertEqual(title_keywords('教学：asr', keys), ['ASR 教学'])
        self.assertEqual(title_keywords('韩信', keys), [])
        self.assertEqual(title_keywords('', keys), [])

    def test_new_defaults_validation_and_saved_legacy_defaults(self):
        self.assertTrue(config({})['strict_match'])
        for bad in ['false', 1, None]:
            with self.assertRaises(ValueError):
                config({'strict_match': bad})
        with self.store.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('search', json.dumps({'keywords': ['甲']})))
        self.assertTrue(self.store.settings()['search']['strict_match'])

    def test_independent_caps_skip_progress_and_actual_conditions(self):
        a, b = '姜导 韩信', '大河龙蛇'
        snap, adapter, register = self.scan({'keywords': [a, b], 'scan_limit': 2, 'process_limit': 1}, {
            (a, 1): ([self.row(1, '无关'), self.row(2, '韩信姜导 大河龙蛇'), self.row(3, '姜导韩信')], True),
            (b, 1): ([self.row(2, '韩信姜导 大河龙蛇'), self.row(4, '大河龙蛇')], False)})
        self.assertEqual(snap['scanned'], 4)
        self.assertEqual(snap['scan_counts'], {a: 2, b: 2})
        self.assertEqual(snap['title_skipped'], 1)
        self.assertEqual(snap['matched'], 2)
        self.assertEqual(snap['limited'], 1)
        self.assertEqual(len(self.store.tasks()), 1)
        self.assertEqual(set(snap['items'][0]['keywords']), {a, b})
        self.assertEqual(adapter.return_value.search_page.call_count, 2)
        self.assertNotIn('BV0000000001', [c.args[1]['bvid'] for c in register.call_args_list])

    def test_preview_detail_fallback_and_disabled_mode(self):
        pages = {('姜导 韩信', 1): ([self.row(1, ''), self.row(2, '无关'), self.row(3, '')], False)}
        snap, adapter, register = self.scan({'keywords': ['姜导 韩信'], 'mode': 'preview'}, pages,
            lambda b: self.row(1 if b.endswith('1') else 3, '韩信姜导' if b.endswith('1') else ''))
        self.assertEqual(snap['matched'], 1)
        self.assertEqual(snap['title_skipped'], 2)
        self.assertEqual(self.store.tasks(), [])
        snap, _, _ = self.scan({'keywords': ['姜导 韩信'], 'strict_match': False},
            {('姜导 韩信', 1): ([self.row(5, '无关')], False)})
        self.assertEqual(snap['matched'], 1)

    def test_legacy_job_keeps_non_strict_behavior_and_no_match_progress(self):
        job = self.store.new_job({'keywords': ['姜导 韩信']})
        cfg = {k: v for k, v in job['config'].items() if k != 'strict_match'}
        with self.store.db() as db:
            db.execute('UPDATE jobs SET config=? WHERE id=?', (json.dumps(cfg), job['id']))
        with patch('crawler.Bilibili') as adapter, patch('crawler.register_discovered'):
            adapter.return_value.search_page.return_value = ([self.row(1, '无关')], False)
            self.runtime.scan(self.store.job(job['id']))
        self.assertEqual(self.store.job(job['id'])['matched'], 1)
        snap, _, _ = self.scan({'keywords': ['姜导 韩信']},
            {('姜导 韩信', 1): ([self.row(n, '无关') for n in range(2, 7)], False)})
        self.assertEqual(snap['scanned'], 5)
        self.assertEqual(snap['title_skipped'], 5)
        self.assertEqual(snap['scan_counts'], {'姜导 韩信': 5})

    def test_second_page_truncation_reports_limit(self):
        snap, adapter, _ = self.scan({'keywords': ['甲'], 'scan_limit': 3, 'mode': 'preview'}, {
            ('甲', 1): ([self.row(1, '甲'), self.row(2, '甲')], True),
            ('甲', 2): ([self.row(3, '甲'), self.row(4, '甲')], False)})
        self.assertEqual(snap['scanned'], 3)
        self.assertEqual(snap['limited'], 1)

    def test_stop_during_search_prevents_registration(self):
        job = self.store.new_job({'keywords': ['甲', '乙']})
        def page(*args):
            self.store.stop(job['id'])
            return [self.row(1, '甲乙')], True
        with patch('crawler.Bilibili') as adapter, patch('crawler.register_discovered') as register:
            adapter.return_value.search_page.side_effect = page
            self.runtime.scan(job)
        self.assertFalse(register.called)
        self.assertEqual(self.store.job(job['id'])['items'], [])
        self.assertEqual(adapter.return_value.search_page.call_count, 1)

    def test_creator_filter_keeps_description_matching(self):
        self.store.save_creator({'url': 'https://space.bilibili.com/123', 'date_from': '2026-10-01'})
        job = self.store.new_job({'keywords': ['姜导 韩信']}, '123')
        with patch('crawler.Bilibili') as adapter, patch('crawler.register_discovered'):
            adapter.return_value.creator_page.return_value = ([self.row(1, '无关')], False)
            self.runtime.scan(job)
        self.assertEqual(self.store.job(job['id'])['matched'], 1)

