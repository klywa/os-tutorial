import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import wxq


class LineupLayoutTests(unittest.TestCase):
    def test_lixin_places_each_claim_once_and_keeps_unmapped_claims(self):
        note = {'id': 'yaomei-sacrifice-lixin', 'type': 'lineup', 'title': '瑶妹牺牲流李信',
                'meta': {}, 'claims': [
                    {'id': 'ban-core', 'kind': 'conditional_strategy', 'section': '禁用阵营适用情况', 'text': '禁用示例'},
                    {'id': 'equip-warplane', 'kind': 'conditional_strategy', 'section': '推荐装备', 'text': '嬴政换装示例'},
                    {'id': 'future-claim', 'kind': 'general_strategy', 'section': '新增规则', 'text': '未来结论不能丢失'}]}
        before = copy.deepcopy(note)
        output = wxq.render_note(note, {})
        self.assertEqual(note, before)
        self.assertIn('## 阵容概览与成员清单', output)
        self.assertLess(output.index('## 禁用阵营与适用条件'), output.index('禁用示例'))
        self.assertLess(output.index('## 对局威胁与应对'), output.index('嬴政换装示例'))
        for claim in note['claims']:
            self.assertEqual(output.count(claim['text']), 1)

    def test_other_lineups_keep_legacy_layout(self):
        note = {'id': 'another-lineup', 'type': 'lineup', 'title': '其他阵容', 'claims': [], 'entities': []}
        output = wxq.render_note(note, {})
        self.assertIn('## 阵容组成', output)
        self.assertNotIn('## 运营路线选择', output)


if __name__ == '__main__':
    unittest.main()
