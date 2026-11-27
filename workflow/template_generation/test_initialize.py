import unittest
from pathlib import Path

from workflow.template_generation.initialize import build_library, read_lineup


ROOT = Path(__file__).resolve().parents[2]


class InitializeTemplateTests(unittest.TestCase):
    def test_knowledge_note_generates_empty_groups_for_explicit_members_and_pairs(self):
        source = ROOT / "knowledge/lineups/开备韩信-姜导.json"
        lineup = read_lineup(source)
        library = build_library(lineup)
        groups = library["groups"]
        by_event = lambda fragment: {
            group["extra_key"] for group in groups if fragment in group["event_name"]
        }

        self.assertEqual(by_event("购买英雄"), {
            "韩信", "亚连", "狂铁", "云中君", "瑶", "牛魔", "弈星", "孙悟空", "雅典娜", "太乙真人",
        })
        self.assertEqual(by_event("第1次拍卖"), {"亚连", "云中君", "瑶"})
        self.assertEqual(by_event("第2次拍卖"), {"韩信", "孙悟空", "雅典娜", "太乙真人"})
        self.assertEqual(by_event("选择天赋"), {"双生相", "虚妄转生", "复印机", "魂祭绝刃"})
        self.assertEqual(by_event("购买效果牌"), {"临阵磨枪", "全军动员", "跳级"})
        self.assertEqual(by_event("转移装备"), {
            "韩信-*-凝渊", "韩信-*-无尽巨剑", "韩信-*-铸梦·逐风", "韩信-*-影牙", "韩信-*-金色圣剑",
            "韩信-*-百锻刀", "瑶-*-名刀·司命", "瑶-*-近卫荣耀", "韩信-*-自然法杖",
        })
        self.assertEqual({group["expression"] for group in groups}, {'我方.阵容名称 == "开备韩信"'})
        self.assertTrue(all(not group["utterances"] and "禁止依赖任何特定局势" in group["instruction"] for group in groups))
        self.assertEqual(len({group["id"] for group in groups}), len(groups))
        self.assertEqual(library, build_library(read_lineup(source)))

    def test_markdown_adapter_matches_explicitly_named_sections(self):
        source = ROOT / "personal/开备韩信-姜导.md"
        if not source.exists():
            self.skipTest("需要本地 Markdown 示例")
        lineup = read_lineup(source)
        pairs = {(gear, hero) for gear, hero in lineup.equipment}
        self.assertIn(("红莲炎甲", "瑶"), pairs)
        self.assertIn(("名刀·司命", "韩信"), pairs)
        self.assertIn("百里玄策", lineup.heroes)
        self.assertIn("虚妄转生", lineup.talents)
        self.assertIn("跳级", lineup.effects)

    def test_excel_adapter_inherits_lineup_through_continuation_rows(self):
        source = ROOT / "personal/阵容定义表.xlsx"
        if not source.exists():
            self.skipTest("需要本地阵容定义表示例")
        lineup = read_lineup(source, lineup_name="逐鹿召唤蒙恬")
        self.assertIn("米莱狄", lineup.heroes)
        self.assertIn("苍", lineup.heroes)
        self.assertIn(("影牙", "苍"), lineup.equipment)


if __name__ == "__main__":
    unittest.main()
