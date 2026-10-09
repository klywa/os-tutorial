import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'wxq.py'
sys.path.insert(0, str(SCRIPT.parent))


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location('wxq', SCRIPT)
            cls.core = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.core)

    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'The skill pipeline has not been implemented')
        temp_root = Path(__file__).parents[4] / '.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_ambiguous_alias_is_not_replaced(self):
        entities = [{'id': 'hero:1', 'name': '甲', 'aliases': ['同音']},
                    {'id': 'hero:2', 'name': '乙', 'aliases': ['同音']}]
        text, changes = self.core.correct_text('同音上场', entities)
        self.assertEqual(text, '同音上场')
        self.assertEqual(changes[0]['status'], 'ambiguous')

    def test_confirmed_alias_is_corrected_without_touching_canonical_name(self):
        text, changes = self.core.correct_text('苏列和苏烈', [
            {'id': 'hero:1', 'name': '苏烈', 'aliases': ['苏列']}])
        self.assertEqual(text, '苏烈和苏烈')
        self.assertEqual(changes[0]['status'], 'confirmed_alias')

    def test_missing_auctions_are_explicit(self):
        result = self.core.render_note({'id': 'a', 'type': 'lineup', 'title': '测试',
                                      'claims': [], 'entities': []}, {})
        for n in ['第一轮拍卖', '第二轮拍卖', '第三轮拍卖']:
            self.assertIn(n + '\n\n暂无已确认的通用策略', result)

    def test_merge_is_idempotent_and_preserves_versions(self):
        a = {'text': '慢升人口', 'version': 'v1', 'condition': '',
             'section': '前期运营及应变', 'evidence': [{'source': 'BV1:p1', 'start': 2, 'end': 5}]}
        b = {**a, 'text': '快升人口', 'version': 'v2'}
        self.assertEqual(len(self.core.merge_claims([a], [a, b])), 2)

    def test_reader_output_hides_provenance_but_preserves_advice_and_relations(self):
        import copy
        note = {'id': 'test', 'type': 'other', 'title': '攻略', 'claims': [{
            'kind': 'conditional_strategy', 'section': '操作', 'text': '保留张良', 'condition': '对手依赖单个输出英雄',
            'inference': True, 'version': 'v1',
            'evidence': [{'source': 'BV1:p1', 'start': 2, 'end': 5, 'frame': 'frames/3.jpg'}]}],
            'related': [{'id': 'player', 'title': '棋手', 'type': 'player'}]}
        before = copy.deepcopy(note)
        output = self.core.render_note(note, {'BV1:p1': {'url': 'https://www.bilibili.com/video/BV1/'}})
        self.assertEqual(note, before)
        self.assertIn('对手依赖单个输出英雄', output)
        self.assertIn('保留张良', output)
        self.assertIn('推测', output)
        self.assertIn('../players/player.md', output)
        for hidden in ['来源结论', '版本：', 'bilibili.com', 'frames/', '2.0–5.0s', '## 知识内容']:
            self.assertNotIn(hidden, output)

    def test_related_notes_found_and_repeat_commit_unchanged(self):
        self.core.init_store(self.root)
        source = {'id': 'BV1:p1', 'url': 'https://example.com', 'duration': 20}
        self.core.atomic_json(self.root / 'knowledge/sources/BV1_p1/metadata.json', source)
        self.core.atomic_json(self.root / 'entities/heroes.json', [{'id': 'hero:1', 'name': '测试英雄'}])
        self.core.atomic_json(self.root / 'knowledge/sources/BV1_p1/asr.raw.json', {'segments': [{'start': 0, 'end': 20, 'text': '测试'}]})
        self.core.atomic_json(self.root / 'knowledge/sources/BV1_p1/asr.corrected.json', {'segments': [{'start': 0, 'end': 20, 'text': '测试'}]})
        note = {'id': 'test', 'type': 'lineup', 'title': '测试', 'entities': ['hero:1'],
                'core': ['hero:1'], 'claims': [{'kind': 'general_strategy', 'section': '核心机制', 'text': '测试机制',
                'version': None, 'condition': '', 'evidence': [{'source': 'BV1:p1', 'start': 2, 'end': 5}]}]}
        self.core.commit_notes(self.root, [note])
        path = self.root / 'knowledge/lineups/test.md'
        before = path.stat().st_mtime_ns
        self.core.commit_notes(self.root, [note])
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(self.core.related(self.root, ['hero:1'])[0]['id'], 'test')

    def test_failed_source_does_not_stop_other_sources(self):
        calls = []
        def work(url):
            calls.append(url)
            if url == 'bad':
                raise RuntimeError('download failed')
            return 'done'
        results = self.core.run_batch(['bad', 'good'], work)
        self.assertEqual(results[0]['status'], 'failed')
        self.assertEqual(results[1]['status'], 'ok')
        self.assertEqual(calls, ['bad', 'good'])

    def test_match_actions_and_unclassified_claims_rejected(self):
        for kind in ['match_action', None]:
            note = {'id': 'action', 'type': 'other', 'title': '单局', 'entities': [],
                    'claims': [{'kind': kind, 'section': '操作', 'text': '这一局先选冰杖',
                                'evidence': [{'source': 'BV1:p1', 'start': 1, 'end': 2}]}]}
            with self.assertRaisesRegex(ValueError, 'kind'):
                self.core.commit_notes(self.root, [note])
            self.assertEqual(self.core.read_json(self.root / 'knowledge/index.json')['notes'], [])

    def test_split_mixed_material_renders_only_reusable_rule(self):
        import copy
        note = {'id': 'mixed', 'type': 'other', 'title': '策略', 'claims': [
            {'kind': 'conditional_strategy', 'section': '站位',
             'text': '对手有范围伤害时分散图腾', 'evidence': [{'source': 'BV1:p1', 'start': 1, 'end': 3}]},
            {'kind': 'match_action', 'section': '站位', 'text': '这一局移到左下角',
             'evidence': [{'source': 'BV1:p1', 'start': 3, 'end': 4}]}]}
        before = copy.deepcopy(note)
        rendered = self.core.render_note(note, {})
        self.assertIn('对手有范围伤害时分散图腾', rendered)
        self.assertNotIn('这一局移到左下角', rendered)
        self.assertEqual(note, before)

    def test_path_traversal_rejected(self):
        self.core.init_store(self.root)
        with self.assertRaises(ValueError):
            self.core.commit_notes(self.root, [{'id': '../escape', 'type': 'other',
                                              'title': 'x', 'claims': [], 'entities': []}])

    def test_atomic_update_keeps_recovery_copy(self):
        p = self.root / 'data.json'
        self.core.atomic_json(p, {'v': 1})
        self.core.atomic_json(p, {'v': 2})
        self.assertEqual(json.loads(p.with_suffix('.json.bak').read_text())['v'], 1)

    def test_lord_nested_hero_remains_hero_not_player_skill(self):
        from official import normalize
        nested = {'id': 1, 'name': '英雄', 'type': 1}
        skill = {'id': 2, 'name': '技能', 'type': 7, 'previewCards': [nested]}
        data = normalize({'lords': [{'lordId': 10, 'name': '棋手',
                           'talent': [{'cards': [skill]}]}]}, 'https://example.com', 'today')
        self.assertIn('card:1', data['heroes'])
        self.assertNotIn('card:1', data['player-skills'])
        self.assertIn('card:2', data['player-skills'])

    def test_unmanaged_markdown_is_not_overwritten(self):
        self.core.init_store(self.root)
        p = self.root / 'knowledge/other/existing.md'
        p.write_text('手写内容', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.core.commit_notes(self.root, [{'id': 'existing', 'type': 'other',
                                               'title': 'x', 'claims': [], 'entities': []}])
        self.assertEqual(p.read_text(encoding='utf-8'), '手写内容')

    def test_interrupted_commit_replays_idempotently(self):
        from unittest.mock import patch
        self.core.init_store(self.root)
        note = {'id': 'resume', 'type': 'other', 'title': '恢复', 'claims': [], 'entities': []}
        original = self.core.atomic_text
        def fail_index(path, text):
            if str(path).endswith('index.json'):
                raise OSError('interrupted')
            return original(path, text)
        with patch.object(self.core, 'atomic_text', side_effect=fail_index):
            with self.assertRaises(OSError):
                self.core.commit_notes(self.root, [note])
        pending = self.core.read_json(self.root / 'knowledge/pending-commit.json')
        self.core.commit_notes(self.root, pending['notes'])
        self.assertEqual(len(self.core.read_json(self.root / 'knowledge/index.json')['notes']), 1)

    def test_source_without_asr_cannot_be_committed(self):
        self.core.init_store(self.root)
        self.core.atomic_json(self.root / 'knowledge/sources/BV1_p1/metadata.json', {'id': 'BV1:p1'})
        note = {'id': 'no-asr', 'type': 'other', 'title': 'x', 'entities': [], 'claims': [{
            'section': '知识内容', 'text': 'x', 'evidence': [{'source': 'BV1:p1', 'start': 0, 'end': 1}]}]}
        with self.assertRaises(ValueError):
            self.core.commit_notes(self.root, [note])

    def test_finished_bv_uses_local_cache_without_network(self):
        from media import prepare
        self.core.init_store(self.root)
        folder = self.root / 'knowledge/sources/BV1test_p1'
        self.core.atomic_json(folder / 'metadata.json', {'id': 'BV1test:p1'})
        self.core.atomic_json(folder / 'state.json', {'stage': 'complete'})
        result = prepare(self.root, 'https://www.bilibili.com/video/BV1test/?p=1')
        self.assertEqual(result, [{'id': 'BV1test:p1', 'stage': 'complete', 'cached': True}])

    def test_finish_rejects_empty_review_intervals(self):
        from media import finish
        self.core.init_store(self.root)
        folder = self.root / 'knowledge/sources/BV1_p1'
        self.core.atomic_json(folder / 'review.json', {'approved': True})
        self.core.atomic_json(folder / 'asr.raw.json', {'segments': [1]})
        self.core.atomic_json(folder / 'asr.corrected.json', {'segments': [1]})
        self.core.atomic_json(self.root / 'knowledge/index.json', {'notes': [{'claims': [{
            'evidence': [{'source': 'BV1:p1', 'start': 1, 'end': 2}]}]}]})
        with self.assertRaises(ValueError):
            finish(self.root, 'BV1:p1')

    def test_resumes_correction_from_existing_raw_asr(self):
        from media import transcribe
        self.core.init_store(self.root)
        folder = self.root / 'knowledge/sources/BV1_p1'
        self.core.atomic_json(self.root / 'entities/heroes.json', [{'id': 'card:1', 'name': '苏烈', 'aliases': ['苏列']}])
        raw = {'segments': [{'id': 0, 'start': 0, 'end': 1, 'text': '苏列'}]}
        self.core.atomic_json(folder / 'asr.raw.json', raw)
        result = transcribe(self.root, 'BV1:p1', folder / 'missing-audio.wav', 'invalid-model')
        self.assertEqual(result['segments'][0]['text'], '苏烈')
        self.assertEqual(self.core.read_json(folder / 'asr.raw.json'), raw)

    def test_short_stream_download_resumes_until_complete(self):
        from media import download_observed
        from unittest.mock import patch
        import io
        class Response(io.BytesIO):
            def __init__(self, content, range_header):
                super().__init__(content)
                self.status = 206
                self.headers = {'Content-Range': range_header}
        first = Response(b'12345', 'bytes 0-9/10')
        second = Response(b'67890', 'bytes 5-9/10')
        with patch('urllib.request.urlopen', side_effect=[first, second]):
            result = download_observed('https://example.com/video', self.root / 'video.m4s')
        self.assertTrue(result['complete'])
        self.assertEqual((self.root / 'video.m4s').read_bytes(), b'1234567890')

    def test_installed_decoder_accepts_faster_whisper_arguments(self):
        import wave
        from faster_whisper.audio import decode_audio
        p = self.root / 'silent.wav'
        with wave.open(str(p), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\x00\x00' * 1600)
        self.assertEqual(len(decode_audio(str(p))), 1600)


if __name__ == '__main__':
    unittest.main()
