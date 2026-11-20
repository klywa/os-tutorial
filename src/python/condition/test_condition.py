"""Run with python -m unittest src.python.condition.test_condition."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import ConditionError, choose_utterance, evaluate_condition, validate_expression
from . import literal_in_bindings, numeric_utterance_bindings, render_bound_utterance


CATALOG_DIR = Path(__file__).resolve().parents[2] / "condition"
EVENT = {"事件": "上阵英雄", "参数": {"arg1": "弈星"}}


class ConditionTests(unittest.TestCase):
    def test_numeric_slots_read_actual_count_and_required_numeric_operands(self):
        name = "解释为何选择天赋"
        count = '玩家.战场.计数(阵营, "无阵营")'
        rule = f'arg2 is "协同一致" and {count} >= 2 and {count} <= 5'
        self.assertEqual(numeric_utterance_bindings(rule, name), (count,))
        self.assertEqual(numeric_utterance_bindings(f'not ({count} < 2) or {count} >= 4', name), ())
        self.assertEqual(numeric_utterance_bindings(f'{count} == 2 or {count} >= 4', name), (count,))
        self.assertEqual(numeric_utterance_bindings(f'{count} == 2 or 玩家.血量 >= 4', name), ())
        self.assertEqual(numeric_utterance_bindings('玩家.主C.已觉醒 == true', name), ())
        self.assertEqual(numeric_utterance_bindings(
            '12 <= 玩家.战场.求和(等级) and 玩家.血量 > 玩家.剩余能量', name),
            ('玩家.战场.求和(等级)', '玩家.血量', '玩家.剩余能量'))
        event = {"事件":name, "参数":{"arg2":"协同一致"}}
        group = {"event_name":name, "expression":rule, "utterances":[f"场上有{{{count}}}名无阵营英雄。"]}
        for amount in (1,2,3):
            state = {"玩家":{"战场":[{"阵营":"无阵营"} for _ in range(amount)]}}
            expected = f"场上有{amount}名无阵营英雄。" if amount >= 2 else None
            self.assertEqual(choose_utterance({"groups":[group]},event,state), expected)
        self.assertIsNone(choose_utterance({"groups":[group]},event,{"玩家":{"战场":[{}]}}))
        self.assertEqual(render_bound_utterance('有{玩家.战场.计数(阵营,"含}引号")}名。',
                         {'玩家.战场.计数(阵营, "含}引号")':'2'}), "有2名。")

    def test_only_required_positive_literal_membership_can_bind_utterances(self):
        event = "解释为何选择天赋"
        membership = '玩家.主C in ["嬴政", "蒙犽", "孙膑"]'
        expected = {"玩家.主C": ["嬴政", "蒙犽", "孙膑"]}
        self.assertEqual(literal_in_bindings(f'arg2 is "穷兵黩武" and ({membership})', event), expected)
        self.assertEqual(literal_in_bindings(f'{membership} and (true or false)', event), expected)
        for expression in (f'{membership} or true', f'not ({membership})',
                           '玩家.主C in 玩家.战场', '玩家.主C in []',
                           f'{membership} and 玩家.主C in ["嬴政"]'):
            with self.subTest(expression=expression):
                self.assertEqual(literal_in_bindings(expression, event), {})
        self.assertEqual(literal_in_bindings('玩家.主C in [{"类型":"英雄","名称":"蒙犽"}]', event),
                         {"玩家.主C": ["蒙犽"]})

    def test_matcher_renders_one_actual_candidate_after_picking_the_line(self):
        event = {"事件":"解释为何选择天赋", "参数":{"arg2":"穷兵黩武"}}
        group = {"event_name":event["事件"], "expression":'arg2 is "穷兵黩武" and 玩家.主C in ["嬴政","蒙犽","孙膑"]',
                 "utterances":["选穷兵黩武，{玩家.主C}施法能召唤玄雍士兵。"]}
        for hero in ("嬴政","蒙犽","孙膑"):
            state = {"玩家":{"主C":{"name":hero}}}
            self.assertEqual(choose_utterance({"groups":[group]}, event, state),
                             f"选穷兵黩武，{hero}施法能召唤玄雍士兵。")
        self.assertIsNone(choose_utterance({"groups":[group]}, event, {}))
        self.assertIsNone(choose_utterance({"groups":[group]}, event, {"玩家":{"主C":"吕布"}}))
        self.assertEqual(render_bound_utterance("{{玩家.主C}} {{{玩家.主C}}} {arg1}", {"玩家.主C":"蒙犽"}),
                         "{{玩家.主C}} {{蒙犽}} {arg1}")
    def test_each_card_form_has_reviewable_tags(self):
        tags = json.loads((CATALOG_DIR / "card-tags.json").read_text(encoding="utf-8"))
        cards = json.loads((CATALOG_DIR.parents[1] / "website-data/cards.json").read_text(encoding="utf-8"))
        kinds = {"heroes": "英雄", "equipment": "装备", "effect-cards": "效果牌", "talents": "天赋"}
        expected = {c["id"]: c for c in cards if c["category"] in kinds}
        self.assertEqual(set(expected), set(tags))
        for key, row in tags.items():
            with self.subTest(card=key):
                card = expected[key]
                self.assertEqual((row["name"], row["type"], row["awakened"]),
                                 (card["name"], kinds[card["category"]], bool(card.get("awakened"))))
                self.assertTrue(row["tags"])
                self.assertEqual(len(row["tags"]), len(set(row["tags"])))
                self.assertTrue(all(isinstance(tag, str) and tag == tag.strip() and tag for tag in row["tags"]))

    def test_portable_card_tags_follow_the_export(self):
        catalog = json.loads((CATALOG_DIR / "catalog.json").read_text(encoding="utf-8"))
        catalog["card_tags"] = {"fixture": {"name": "弈星", "type": "英雄", "awakened": False,
                                             "tags": ["审核后的标签"]}}
        self.assertTrue(evaluate_condition(EVENT, 'arg1.标签 has "审核后的标签"', {}, {"condition_catalog": catalog}))
        self.assertFalse(evaluate_condition(EVENT, 'arg1.标签 has "提供棋手经验"', {}, {"condition_catalog": catalog}))

    def test_shared_examples(self):
        cases = json.loads((CATALOG_DIR / "cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(name=case["name"]):
                args = (json.dumps(case["event"]).encode(), case["expression"], json.dumps(case["state"]))
                if "parameters" in case:
                    catalog = json.loads((CATALOG_DIR / "catalog.json").read_text(encoding="utf-8"))
                    catalog["events"]["自定义事件"] = {"parameters": case["parameters"]}
                    args += (catalog,)
                if case.get("error"):
                    with self.assertRaises(ConditionError) as raised:
                        evaluate_condition(*args)
                    if "column" in case:
                        self.assertEqual(raised.exception.column, case["column"])
                else:
                    self.assertIs(evaluate_condition(*args), case["result"])

    def test_validates_even_when_branch_cannot_win(self):
        with self.assertRaises(ConditionError):
            validate_expression("上阵英雄", "true or arg1. typo")

    def test_mixed_membership_requires_a_type_on_both_sides(self):
        with self.assertRaises(ConditionError):
            evaluate_condition(EVENT, "玩家.手牌 has arg1", {"玩家": {"手牌": ["弈星"]}})
        with self.assertRaises(ConditionError):
            validate_expression("上阵英雄", '玩家.手牌 has "弈星"')
        self.assertTrue(evaluate_condition(
            EVENT, "玩家.战场 has arg1", {"玩家": {"战场": ["弈星"]}}
        ))

    def test_empty_list_requires_scalar_operand(self):
        with self.assertRaises(ConditionError):
            validate_expression("上阵英雄", "[] has []")

    def test_units_preserve_concrete_identity_and_legacy_hero_fields(self):
        name = "解释为何对目标使用效果牌"
        unit = {"类型": "单位", "name": "电磁弹簧", "等级": 99}
        hero = {"名称": "电磁弹簧", "等级": 12}
        derivative = {"类型": "衍生物", "名称": "电磁弹簧"}
        state = {"玩家": {"战场": [unit, derivative, hero], "主C": hero}}
        def check(expression, arg=unit):
            return evaluate_condition({"事件": name, "参数": {"arg1": arg}}, expression, state)
        self.assertTrue(check('arg1 is "电磁弹簧" and arg1.name in ["等离子屏障","电磁弹簧"]'))
        self.assertTrue(check('arg1 in 玩家.战场 and 玩家.战场 has "电磁弹簧"'))
        self.assertFalse(check('arg1 is 玩家.主C', derivative))
        self.assertFalse(check('not (arg1.等级 >= 10)'))
        self.assertTrue(check('arg1 is 玩家.主C and arg1.等级 >= 10', hero))
        self.assertTrue(check("玩家.战场.求和(等级) == 12"))
        state["玩家"]["战场"] = [derivative]
        self.assertFalse(check("arg1 in 玩家.战场", hero))
        state["玩家"]["战场"] = [None, derivative]
        self.assertFalse(check("not (arg1 in 玩家.战场)", hero))

    def test_hero_counts_and_equipment_talent_lists(self):
        event = {"事件": "解释为何对目标使用效果牌",
                 "参数": {"arg1": {"名称": "夏侯惇", "已穿装备": []}}}
        state = {"玩家": {"战场": [{"名称": "小乔", "阵营": "三分之地"},
                                  {"类型": "单位", "名称": "机关"},
                                  {"名称": "吕布", "阵营": "三分之地"}],
                         "已选天赋": ["搏战"]}}
        rule = ('arg1.已穿装备.计数() == 0 and 玩家.已选天赋 has "搏战"'
                ' and 玩家.战场.计数(阵营, "三分之地") == 2'
                ' and 玩家.战场.计数(标签, "登场") >= 0')
        self.assertTrue(evaluate_condition(event, rule, state))
        del state["玩家"]["战场"][0]["阵营"]
        self.assertFalse(evaluate_condition(event, "not (" + rule + ")", state))
        del event["参数"]["arg1"]["已穿装备"]
        self.assertFalse(evaluate_condition(event, "arg1.已穿装备.计数() == 0", state))
        with self.assertRaises(ConditionError):
            validate_expression(event["事件"], '玩家.战场.计数(等级, "10") == 1')

    def test_tag_count_requires_enough_information_to_decide_each_hero(self):
        catalog = json.loads((CATALOG_DIR / "catalog.json").read_text(encoding="utf-8"))
        catalog["card_tags"] = {
            "card:1": {"name":"弈星", "type":"英雄", "awakened":False, "tags":["具有登场效果"]},
            "card:2": {"name":"弈星", "type":"英雄", "awakened":True, "tags":["具有整备效果"]},
        }
        rule = '玩家.战场.计数(标签, "登场")'
        hero = {"名称":"弈星"}
        state = {"玩家":{"战场":[hero]}}
        self.assertFalse(evaluate_condition(EVENT, rule + " == 0", state, catalog))
        self.assertFalse(evaluate_condition(EVENT, rule + " == 1", state, catalog))
        hero["已觉醒"] = False
        self.assertTrue(evaluate_condition(EVENT, rule + " == 1", state, catalog))

    def test_exported_catalog_can_change_without_restart(self):
        catalog = json.loads((CATALOG_DIR / "catalog.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "export.json"
            target.write_text(json.dumps({"condition_catalog": catalog}), encoding="utf-8")
            with patch.dict(os.environ, WXQ_CONDITION_CATALOG=str(target)):
                validate_expression("上阵英雄", 'arg1.name is "弈星"')
                catalog["types"]["英雄"]["额外属性"] = "number"
                target.write_text(json.dumps({"condition_catalog": catalog}), encoding="utf-8")
                validate_expression("上阵英雄", "arg1.额外属性 >= 1.5")

    def test_scope_priority_then_uniform_group_and_line(self):
        def group(scope, lines, priority=5, expression=""):
            return dict(event_name="上阵英雄", scope=scope, expression=expression,
                        priority=priority, utterances=lines)
        groups = [
            group({}, ["低优先级"], priority=1),
            group({"player":"甲"}, ["一", "二"]),
            group({"lineup":"乙"}, ["三"]),
            group({"lineup":"丙"}, ["其他阵容"], priority=10),
            group({}, ["缺值"], priority=10, expression="arg1.等级 >= 3"),
        ]
        class LastChoice:
            def __init__(self):
                self.options = []

            def choice(self, items):
                self.options.append(items)
                return items[-1]
        rng = LastChoice()
        state = {"玩家":{"使用棋手":"甲", "使用阵容":"乙"}}
        self.assertEqual(choose_utterance({"groups":groups}, EVENT, state, rng=rng), "三")
        self.assertEqual(rng.options, [[["一", "二"], ["三"]], ["三"]])
        self.assertIsNone(choose_utterance({"groups":[]}, EVENT, {}))

    def test_strict_inclusion_filters_only_dominated_matches(self):
        class Capture:
            def choice(self, items):
                if isinstance(items[0],list):
                    self.labels = [lines[0] for lines in items]
                return items[0]

        event = {"事件":"上阵英雄","参数":{"arg1":{"名称":"弈星","等级":10,"已觉醒":True}}}
        state = {"玩家":{"剩余能量":2,"主C":{"名称":"弈星"},"战场":[{"名称":"弈星","等级":10}]}}
        def check(expressions, expected, priorities=None):
            groups = [dict(event_name="上阵英雄",expression=expr,utterances=[str(i)],
                           priority=(priorities or [0]*len(expressions))[i])
                      for i,expr in enumerate(expressions)]
            rng = Capture()
            choose_utterance({"groups":groups},event,state,rng=rng)
            self.assertEqual(rng.labels,[str(i) for i in expected])

        check(["玩家.战场.求和(等级) >= 5", "玩家.战场.求和(等级) >= 10"], [1])
        check(["", '玩家.战场.计数(阵营, "三分之地") >= 0'], [0])
        state["玩家"]["战场"][0]["阵营"] = "三分之地"
        count = '玩家.战场.计数(阵营, "三分之地")'
        check(["", count + " >= 0", count + " >= 1"], [2])
        cap = "玩家.剩余能量 <= 2"
        hero = 'arg1.名称 is "弈星"'
        check(["",cap,"玩家.剩余能量 <= 3",cap+" and "+hero],[3])
        check([cap+" and "+hero,cap,hero],[0])
        check([cap,"玩家.剩余能量 < 3","not (玩家.剩余能量 > 2)"],[0,1,2])
        check([cap,hero,cap+" or "+hero],[0,1])
        check([hero,'arg1.名称 in ["弈星","小乔"]'],[0])
        check(["arg1.已觉醒 or not arg1.已觉醒",""],[0])
        check(["玩家.战场 has arg1","arg1 in 玩家.战场",""],[0,1])
        check([hero,'arg1 is "弈星"'],[0,1])
        check([hero,cap+" and "+hero],[0],[9,0])
        check(["arg1.等级 >= 玩家.剩余能量","arg1.等级 >= 10 and 玩家.剩余能量 <= 2"],[1])
