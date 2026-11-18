"""Run with python -m unittest src.python.condition.test_condition."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import ConditionError, choose_utterance, evaluate_condition, validate_expression


CATALOG_DIR = Path(__file__).resolve().parents[2] / "condition"
EVENT = {"事件": "上阵英雄", "参数": {"arg1": "弈星"}}


class ConditionTests(unittest.TestCase):
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
        state = {"玩家":{"剩余能量":2,"主C":{"名称":"弈星"},"战场":["弈星"]}}
        def check(expressions, expected, priorities=None):
            groups = [dict(event_name="上阵英雄",expression=expr,utterances=[str(i)],
                           priority=(priorities or [0]*len(expressions))[i])
                      for i,expr in enumerate(expressions)]
            rng = Capture()
            choose_utterance({"groups":groups},event,state,rng=rng)
            self.assertEqual(rng.labels,[str(i) for i in expected])

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
