"""Coverage is about current substantive prose, not headings or missing-data notes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
sys.path.insert(0, str(ROOT / 'frontend'))
import dashboard


def heading(title, level=2):
    return {'type': 'heading', 'id': 'h-' + title, 'level': level, 'title': title}


def entry(value, key='正文'):
    return {'type': 'entry', 'id': 'e-' + str(len(value)), 'key': key, 'value': value, 'show_key': False}


class ContentTests(unittest.TestCase):
    def test_placeholders_even_with_named_entities_are_not_content(self):
        for text in ('', '  **待补充**。', '暂无已确认策略。', '李信的购买策略尚未整理。',
                     '暂无可靠统计。', '具体克制方法待确认。', '未找到可靠的针对建议。',
                     '[视频来源](https://example.com)', '详见[关联知识](knowledge://note/test)。',
                     '| 英雄 | 建议 |\n| --- | --- |\n| 李信 | 待补充 |',
                     '李信：暂无。', '李信：未知。', '克制方法：待补'):
            with self.subTest(text=text):
                self.assertFalse(dashboard.substantive(text))

    def test_mixed_gaps_and_negative_actions_remain_content(self):
        for text in ('出价上限未确认；先保留购买李信的预算。', '不要为重复牌提前升本。',
                     '尚未6级且能稳住血量时，优先比较扶摇直上。',
                     '刘邦细节待补充。控制尚未发挥就阵亡时给东皇太一名刀。',
                     '没有吸血装备时，用回复辅助保证续航。', '不要等待确认后再购买核心。',
                     '没有必要补充低星挂件。'):
            with self.subTest(text=text):
                self.assertTrue(dashboard.substantive(text))

    def test_seven_fields_and_nested_prose(self):
        nodes = [heading('样例', 1), entry('李信', '核心英雄')]
        titles = ['前期英雄组成与运营', '英雄', '韩信与姬小满分支拍卖', '推荐装备',
                  '推荐天赋及原因', '克制与风险', '关键操作顺序']
        for title in titles:
            nodes += [heading(title), heading('细节', 3), entry('利用控制打断对手核心。' if title == '克制与风险' else '先补主力，保留关键资源。')]
        result = dashboard.coverage({'nodes': nodes})
        self.assertEqual(len(result), 7)
        self.assertTrue(all(x['covered'] for x in result.values()))
        self.assertEqual(result['auction']['node_id'], 'h-' + titles[2])

    def test_headings_supporting_nodes_opening_and_offense_do_not_cover(self):
        nodes = [heading('样例', 1), entry('李信', '核心英雄'), heading('英雄'),
                 heading('克制手段'), entry('暂无已确认的针对策略。'),
                 heading('制敌手段'), entry('用控制针对依赖施法的敌人。')]
        result = dashboard.coverage({'nodes': nodes, 'supporting_nodes': [entry('实际操作建议')]})
        self.assertFalse(any(x['covered'] for x in result.values()))
        self.assertEqual(result['counter']['section'], '克制手段')
        self.assertIsNone(result['auction']['node_id'])

    def test_later_substantive_section_is_navigation_target(self):
        nodes = [heading('拍卖'), entry('待补充'), heading('拍卖补充'), entry('优先竞拍当前缺失的核心。')]
        self.assertEqual(dashboard.coverage({'nodes': nodes})['auction']['section'], '拍卖补充')

    def test_general_self_risk_does_not_establish_how_to_counter_the_lineup(self):
        text = '李白100级不可选中仅覆盖斩击期间，起手与两次技能间仍可能受伤；6级免控也有15秒和压制例外。具体对手克制与完整终局名单未确认。'
        self.assertFalse(dashboard.coverage({'nodes': [heading('克制与风险'), entry(text)]})['counter']['covered'])
        self.assertTrue(dashboard.coverage({'nodes': [heading('克制与风险'), entry('利用两次技能间隙集火李白，打断起手施法。')]})['counter']['covered'])

    def test_source_labels_do_not_establish_equipment_coverage(self):
        for key in ('来源', '视频来源', '参考资料', '证据'):
            self.assertFalse(dashboard.coverage({'nodes': [heading('关键装备'), entry('主播实战复盘', key)]})['equipment']['covered'])

    def test_prefixed_stage_headings_and_nested_route_stages_are_rhythm(self):
        for nodes in (
            [heading('原低阶登场路线：前期英雄组成与运营'), entry('低阶合成稳定后再升本。')],
            [heading('三阶貂蝉施法固化路线'), heading('前期', 3), entry('先用当前低阶战力保血。')],
        ):
            self.assertTrue(dashboard.coverage({'nodes': nodes})['rhythm']['covered'])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / 'temp/dashboard-tests'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'knowledge/lineups').mkdir(parents=True)
        self.rows = []
        self.write_index()

    def write_index(self):
        (self.root / 'knowledge/index.meta.json').write_text(json.dumps({'notes': self.rows}), encoding='utf-8')

    def add(self, nid, kind='lineup', nodes=None):
        path = f'knowledge/lineups/{nid}.json'
        self.rows.append({'id': nid, 'type': kind, 'title': nid, 'path': path, 'revision': nid})
        (self.root / path).write_text(json.dumps({'nodes': nodes or []}), encoding='utf-8')
        self.write_index()

    def test_empty_denominators_are_null(self):
        result = dashboard.snapshot(self.root)
        self.assertEqual(result['counts'], {'player': 0, 'lineup': 0})
        self.assertIsNone(result['summary']['rate'])
        self.assertTrue(all(x['rate'] is None for x in result['fields']))

    def test_counts_formulas_and_cache_invalidation_without_index_revision_change(self):
        self.add('player', 'player')
        self.add('other', 'other')
        self.add('one', nodes=[heading('英雄'), entry('李信承担输出。')])
        self.add('two')
        first = dashboard.snapshot(self.root)
        self.assertEqual(first['counts'], {'player': 1, 'lineup': 2})
        self.assertEqual(first['summary']['covered'], 1)
        self.assertEqual(first['summary']['total'], 14)
        self.assertAlmostEqual(first['summary']['rate'], 1 / 14)
        self.assertEqual(next(f for f in first['fields'] if f['id'] == 'heroes')['rate'], .5)
        self.assertEqual(first['notes'][0]['rate'], 1 / 7)
        self.assertEqual(dashboard.snapshot(self.root)['revision'], first['revision'])
        (self.root / self.rows[2]['path']).write_text(json.dumps({'nodes': []}), encoding='utf-8')
        second = dashboard.snapshot(self.root)
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(second['summary']['covered'], 0)
        self.rows = self.rows[:2]
        self.write_index()
        self.assertEqual(dashboard.snapshot(self.root)['counts']['lineup'], 0)

    def test_all_fields_covered_and_duplicate_index_rows_count_once(self):
        nodes = []
        for title in ('运营节奏', '英雄', '拍卖', '关键装备', '推荐天赋', '克制手段', '关键操作'):
            nodes += [heading(title), entry('控制对手核心，优先保留资源。')]
        self.add('full', nodes=nodes)
        self.rows.append(self.rows[0].copy())
        self.write_index()
        result = dashboard.snapshot(self.root)
        self.assertEqual(result['counts']['lineup'], 1)
        self.assertEqual(result['summary']['rate'], 1)

    def test_missing_or_invalid_note_fails_instead_of_changing_denominator(self):
        self.add('bad')
        path = self.root / self.rows[0]['path']
        for text in ('invalid json', '{}'):
            path.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'bad'):
                dashboard.snapshot(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'bad'):
            dashboard.snapshot(self.root)

    def test_changed_snapshot_is_retried_not_cached(self):
        self.add('one')
        original = dashboard.fingerprint
        calls = 0

        def moving(*args):
            nonlocal calls
            calls += 1
            return (*original(*args), calls)

        with patch.object(dashboard, 'fingerprint', side_effect=moving):
            with self.assertRaisesRegex(ValueError, '更新'):
                dashboard.snapshot(self.root)

    def test_missing_player_body_is_an_error_not_a_valid_count(self):
        self.add('player', 'player')
        (self.root / self.rows[0]['path']).unlink()
        with self.assertRaisesRegex(ValueError, 'player'):
            dashboard.snapshot(self.root)


if __name__ == '__main__':
    unittest.main()
