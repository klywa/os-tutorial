import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tutorial
import analyze_cached
import acquire_observed


class TutorialTests(unittest.TestCase):
    def setUp(self):
        fixture_root = tutorial.ROOT / 'raw/reports/test-fixtures'
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=fixture_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = {'id': 'BV1JGpM62EC5:p1', 'title': '测试：教学/示例',
                       'url': 'https://www.bilibili.com/video/BV1JGpM62EC5/?p=1',
                       'author': '老师', 'duration': 100}
        self.record = {'schema_version': 1, 'source': self.source, 'status': 'completed',
                       'review': {'full_transcript_read': True, 'checked_intervals': [[0, 100]]},
                       'unresolved': [], 'events': [{
            'id': 'BV1JGpM62EC5:p1:e001', 'start': 10, 'end': 20, 'scene': '实战',
            'timing': '选择天赋时', 'content': '对照阵容选择可兑现的成长',
            'background': {'text': '三个选项', 'basis': '明确说明'},
            'goal': {'text': '学会权衡', 'basis': '分析推断'},
            'quote': '要根据阵容考虑最合适的', 'segment_ids': [1],
            'template_id': 'talent-fit', 'screenshots': [{'path': 'tutorial/assets/example.jpg',
            'time': 15, 'reviewed': True, 'observation': '画面出现选择界面'}]}]}
        p = self.root / 'proposal/tutorial/assets/example.jpg'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'example-fixture')
        self.asr = self.root / 'raw/sources/BV1JGpM62EC5_p1/asr.corrected.json'
        tutorial.write(self.asr, {'segments': [{'id': 1, 'start': 10, 'end': 20,
                           'text': self.record['events'][0]['quote']}]})

    def test_raw_asr_without_correction_is_valid(self):
        self.asr.rename(self.asr.with_name('asr.raw.json'))
        self.record['transcript_file'] = 'asr.raw.json'
        self.assertEqual(tutorial.validate_record(self.root, self.record), [])

    def test_missing_empty_and_wrong_time_asr_are_rejected(self):
        for value in ({'segments': []}, {'segments': [{'id': 1, 'start': 50, 'end': 60,
                         'text': self.record['events'][0]['quote']}]}, None):
            if value is None:
                self.asr.unlink()
            else:
                tutorial.write(self.asr, value)
            self.assertTrue(tutorial.validate_record(self.root, self.record))

    def test_far_frame_is_not_synchronous_evidence(self):
        r = copy.deepcopy(self.record)
        r['events'][0]['end'] = 80
        r['events'][0]['screenshots'][0]['time'] = 75
        self.assertTrue(tutorial.validate_record(self.root, r))

    def test_existing_record_never_calls_acquisition(self):
        tutorial.save_record(self.root, self.record)
        def forbidden(*args):
            self.fail('existing record triggered acquisition')
        result = tutorial.prepare_source(self.root, self.source, acquire=forbidden)
        self.assertTrue(result['reused_record'])

    def test_analysis_rerun_does_not_read_or_replace_assets(self):
        tutorial.save_record(self.root, self.record)
        tutorial.write(self.root / 'proposal/tutorial/batch.json', [self.source])
        annotation = self.root / 'annotations.json'
        tutorial.write(annotation, {'source_id': self.source['id']})
        image = self.root / 'proposal/tutorial/assets/example.jpg'
        before = image.read_bytes()
        with patch.object(analyze_cached, 'ROOT', self.root), patch.object(sys, 'argv', ['analyze', str(annotation)]), \
                patch.object(analyze_cached.shutil, 'copy2', side_effect=AssertionError('Asset write')):
            analyze_cached.main()
        self.assertEqual(image.read_bytes(), before)

    def test_observed_acquisition_respects_markdown_only_record(self):
        folder = self.root / 'proposal/tutorial/records'
        folder.mkdir(parents=True)
        (folder / (tutorial.safe_title(self.source['title']) + '.md')).write_text('old', encoding='utf8')
        observed = self.root / 'observed.json'
        tutorial.write(observed, {'source': self.source})
        with patch.object(acquire_observed, 'ROOT', self.root), \
                patch.object(sys, 'argv', ['acquire', str(observed), '--model-dir', str(self.root)]):
            self.assertEqual(acquire_observed.main(), 0)
        self.assertFalse((self.asr.parent / 'metadata.json').exists())

    def test_titles_are_safe_and_collision_preserves_both(self):
        a = tutorial.save_record(self.root, self.record)
        other = copy.deepcopy(self.record)
        other['source']['id'] = 'BV1tkHS6VECD:p1'
        other['source']['url'] = 'https://www.bilibili.com/video/BV1tkHS6VECD/?p=1'
        other['events'][0]['id'] = 'BV1tkHS6VECD:p1:e001'
        tutorial.write(self.root / 'raw/sources/BV1tkHS6VECD_p1/asr.corrected.json', tutorial.read(self.asr))
        b = tutorial.save_record(self.root, other)
        self.assertNotEqual(a, b)
        self.assertEqual(len(list(a.parent.glob('*.json'))), 2)
        self.assertNotIn('/', a.name)

    def test_missing_or_unreviewed_or_out_of_range_screenshot_rejected(self):
        for change in ({'path': 'tutorial/assets/missing.jpg'}, {'reviewed': False}, {'time': 22},
                       {'path': '../outside.jpg'}):
            r = copy.deepcopy(self.record)
            r['events'][0]['screenshots'][0].update(change)
            self.assertTrue(tutorial.validate_record(self.root, r))

    def test_finished_requires_full_read_and_review_coverage(self):
        for review in ({'full_transcript_read': False, 'checked_intervals': [[0, 100]]},
                       {'full_transcript_read': True, 'checked_intervals': [[0, 5]]}):
            r = copy.deepcopy(self.record)
            r['review'] = review
            self.assertTrue(tutorial.validate_record(self.root, r))

    def test_stats_exclude_failed_pending_and_unrelated_sources(self):
        tutorial.save_record(self.root, self.record)
        sources = [self.source, {'id': 'BV1tkHS6VECD:p1', 'title': '待处理', 'status': 'pending'}]
        data = tutorial.aggregate(self.root, sources, [])
        self.assertEqual(data['stats']['planned'], 2)
        self.assertEqual(data['stats']['completed'], 1)
        self.assertEqual(data['stats']['events'], 1)
        self.assertEqual(data['stats']['duration'], 100)
        self.assertEqual(data['stats']['scenes'], {'实战': 1})

    def test_repeated_events_count_one_video_for_template(self):
        r = copy.deepcopy(self.record)
        second = copy.deepcopy(r['events'][0])
        second['id'] += '-repeat'
        r['events'].append(second)
        tutorial.save_record(self.root, r)
        d = tutorial.aggregate(self.root, [self.source], [])
        self.assertEqual(d['templates'][0]['event_count'], 2)
        self.assertEqual(d['templates'][0]['video_count'], 1)

    def test_report_escapes_script_and_is_deterministic(self):
        self.record['source']['title'] = '</script><script>alert(1)</script>'
        tutorial.save_record(self.root, self.record)
        d = tutorial.aggregate(self.root, [self.source], [])
        first = tutorial.render_report(d)
        self.assertEqual(first, tutorial.render_report(d))
        self.assertNotIn('</script><script>alert(1)', first)
        self.assertIn('application/json', first)
        self.assertNotIn('fetch(', first)

    def test_changed_screenshot_digest_cannot_be_completed_evidence(self):
        r = copy.deepcopy(self.record)
        r['events'][0]['screenshots'][0]['sha256'] = '0' * 64
        self.assertTrue(tutorial.validate_record(self.root, r))

    def test_quote_must_come_from_referenced_asr_when_available(self):
        raw = self.root / 'raw/sources/BV1JGpM62EC5_p1/asr.corrected.json'
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps({'segments': [{'id': 1, 'start': 10, 'end': 20,
                                                'text': '这是闲聊，并非记录中的教学原话'}]}), encoding='utf8')
        self.assertTrue(tutorial.validate_record(self.root, self.record))

    def test_invalid_existing_record_is_retained_and_not_counted(self):
        tutorial.save_record(self.root, self.record)
        p, r = tutorial.records(self.root)[self.source['id']]
        r['schema_version'] = 0
        p.write_text(json.dumps(r), encoding='utf8')
        before = p.read_bytes()
        d = tutorial.aggregate(self.root, [self.source], [])
        self.assertEqual(d['stats']['completed'], 0)
        self.assertEqual(d['stats']['events'], 0)
        self.assertEqual(p.read_bytes(), before)

    def test_existing_markdown_alone_blocks_acquisition(self):
        folder = self.root / 'proposal/tutorial/records'
        folder.mkdir(parents=True)
        (folder / (tutorial.safe_title(self.source['title']) + '.md')).write_text('人工旧记录', encoding='utf8')
        def forbidden(*args):
            self.fail('Markdown record triggered acquisition')
        r = tutorial.prepare_source(self.root, self.source, acquire=forbidden)
        self.assertTrue(r['reused_record'])


if __name__ == '__main__':
    unittest.main()
