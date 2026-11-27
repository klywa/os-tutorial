import unittest

from . import ConditionError, choose_utterance
from .v04 import compile_expression, load_library, choose, render
from .v04_legacy import adapt


EVENT = "解释为何转移装备"
STATE = {
    "我方": {"场上英雄列表": [{"名称": "花木兰", "等级": 36}]},
    "对手": None,
    "动作": {
        "目标英雄": {"名称": "花木兰"},
        "原英雄": {"名称": "司空震"},
        "装备": {"名称": "驱雷"},
    },
}


def group(identifier, text, priority=0, expression=""):
    return {"id": identifier, "name": identifier, "event_id": "transfer",
            "priority": priority, "expression": expression, "explanation": "",
            "utterances": [{"id": identifier + "_1", "text": text}]}


class Version04Test(unittest.TestCase):
    def test_runtime_lineup_membership_distinguishes_missing_and_empty_lists(self):
        event = '解释为何上阵英雄'
        root = '我方.阵容英雄名列表'
        included = compile_expression(event, '动作.英雄.名称 in ' + root)
        excluded = compile_expression(event, '动作.英雄.名称 not in ' + root)
        for player, expected in (({'阵容英雄名列表':['小乔']}, (True, False)),
                                 ({'阵容英雄名列表':[]}, (False, True)), ({}, (False, False)),
                                 ({'阵容英雄名列表':'小乔'}, (False, False))):
            state = {'我方':player, '动作':{'英雄':{'名称':'小乔'}}}
            self.assertEqual(tuple(rule.evaluate(state) is True for rule in (included, excluded)), expected)
        with self.assertRaises(ConditionError):
            compile_expression(event, 'any(我方.场上英雄列表, .名称 in ' + root + ')')
        with self.assertRaises(ConditionError):
            compile_expression(event, 'any(对局.玩家列表, "小乔" in .阵容英雄名列表)')
        compile_expression(event, 'any(我方.场上英雄列表, .英雄阵容定位 != "非阵容英雄")')

    def test_merge_requires_observed_result_and_crosses_a_threshold(self):
        event = "解释为何合成英雄"
        awakening = compile_expression(event, "not 动作.英雄.已觉醒 and 动作.合成后已觉醒 != nil and 动作.合成后已觉醒")
        threshold = compile_expression(event, "动作.合成后等级 != nil and 动作.英雄.等级 < 40 and 动作.合成后等级 >= 40")
        hero = {"名称": "曹操", "等级": 39, "已觉醒": False}
        for result, expected in (
            ({"合成后已觉醒": True, "合成后等级": 40}, (True, True)),
            ({"合成后已觉醒": False, "合成后等级": 39}, (False, False)),
            ({}, (False, False)),
        ):
            state = {"动作": {"英雄": hero, **result}}
            self.assertEqual(tuple(rule.evaluate(state) is True for rule in (awakening, threshold)), expected)

    def test_hand_sale_can_check_inspiration_candidates(self):
        event = "解释为何从手牌出售英雄"
        rule = compile_expression(event, (
            '我方.棋手名称 == "白歌" and 动作.英雄.名称 not in ["小乔", "甄姬"] and '
            'not 动作.英雄.已觉醒 and '
            'any(我方.手牌列表, .名称 == "灵感爆发") and '
            'any(我方.手牌列表, .卡牌类型 == "英雄" and not .已觉醒 and .名称 in ["小乔", "甄姬"])'
        ))
        hero = {"名称": "赵云", "已觉醒": False}
        skill = {"名称": "灵感爆发"}
        core = {"名称": "甄姬", "已觉醒": False, "卡牌类型": "英雄"}
        for sold, hand, expected in (
            (hero, [hero, skill, core], True),
            (hero, [hero, core], False),
            (hero, [hero, skill], False),
            ({**hero, "已觉醒": True}, [hero, skill, core], False),
        ):
            self.assertIs(rule.evaluate({"我方": {"棋手名称": "白歌", "手牌列表": hand}, "动作": {"英雄": sold}}), expected)

    def test_legacy_hero_argument_for_new_events(self):
        for event in ("解释为何合成英雄", "解释为何从手牌出售英雄"):
            with self.subTest(event=event):
                _, state = adapt({"事件": event, "参数": {"arg1": {"名称": "曹操"}}}, {})
                self.assertEqual(state["动作"]["英雄"]["名称"], "曹操")

    def test_predicate_reads_outer_scalar(self):
        condition = compile_expression(EVENT, 'any(我方.场上英雄列表, .名称 == 动作.目标英雄.名称)')
        self.assertIs(condition.evaluate(STATE), True)

    def test_optional_guard_on_each_executed_branch(self):
        condition = compile_expression(EVENT, "对手 == nil or (对手.主C != nil and 对手.主C.等级 > 40)")
        self.assertIs(condition.evaluate(STATE), True)
        with self.assertRaises(ConditionError):
            compile_expression(EVENT, "对手 == nil or 对手.主C.等级 > 40")

    def test_card_slots_render_name_and_guard_optional_card(self):
        self.assertEqual(render(EVENT, "{{动作.装备.名称}}，还差{{40 - sum(我方.场上英雄列表, .等级)}}级", STATE),
                         "驱雷，还差4级")
        self.assertIsNone(render(EVENT, "{{对手.主C.名称}}", STATE))
        self.assertEqual(render(EVENT, "{{动作.装备}}", STATE), "驱雷")
        self.assertIsNone(render(EVENT, "{{对手.主C}}", {"对手": {"主C": None}}))
        self.assertEqual(render(EVENT, "{{对手.主C}}", {"对手": {"主C": {"名称": "小乔"}}}), "小乔")

    def test_match_stage_uses_round_without_changing_action_stage(self):
        for number, stage in ((3, "前期"), (4, "中期"), (11, "中期"), (12, "后期")):
            with self.subTest(number=number):
                rule = compile_expression(EVENT, f'对局.比赛阶段 == "{stage}" and 对局.当前阶段 == "战斗阶段"')
                self.assertIs(rule.evaluate({"对局": {"当前回合数": number, "当前阶段": "战斗阶段"}}), True)

    def test_ignores_unknown_paths_before_validating_their_contents(self):
        valid = group("valid", "有效")
        del valid["explanation"]
        with self.assertLogs("src.python.condition.v04", level="WARNING") as logs:
            library = load_library({"未来事件": None, "解释事件": {
                "未来解释类型": None,
                EVENT: {"错误键": None, "花木兰-司空震-驱雷": [valid]},
            }})
        self.assertEqual(len(logs.records), 3)
        self.assertEqual(choose(library, EVENT, STATE)["text"], "有效")
        with self.assertRaises(ConditionError):
            load_library({"解释事件": {EVENT: {"花木兰-司空震-驱雷": [
                {**valid, "expression": "动作.未知字段 == 1"},
            ]}}})

    def test_strict_key_validation_rejects_reversed_and_nested_literal_comparisons(self):
        rule = 'not ("花木兰" != 动作.目标英雄.名称) and 动作.装备.名称 in ["驱雷", "影牙"]'
        document = {"解释事件": {EVENT: {"花木兰-*-驱雷": [group("known", "有效", expression=rule)]}}}
        self.assertEqual(choose(load_library(document), EVENT, STATE)["text"], "有效")
        with self.assertRaisesRegex(ConditionError, "已由额外信息键确定"):
            load_library(document, strict=True)
        with self.assertRaisesRegex(ConditionError, "已由额外信息键确定"):
            choose_utterance(document, {"事件": EVENT, "syntax_version": "0.5"}, STATE)

    def test_strips_only_determined_comparisons(self):
        from .v04 import strip_key_redundancy, validate_key_expression

        old = (
            '(动作.原英雄.名称 == "司空震" and "花木兰" == 动作.目标英雄.名称) or '
            '(动作.装备.名称 not in ["驱雷"] and 对手 == nil)'
        )
        rule = strip_key_redundancy(EVENT, "花木兰-*-驱雷", old)
        self.assertEqual(rule, '动作.原英雄.名称 == "司空震"')
        validate_key_expression(EVENT, "花木兰-*-驱雷", rule)
        independent = 'any(我方.场上英雄列表, .名称 == 动作.目标英雄.名称) and 动作.目标英雄.等级 > 12'
        self.assertEqual(strip_key_redundancy(EVENT, "花木兰-*-驱雷", independent), independent)
        numeric = strip_key_redundancy("解释为何棋手升级", "6", '6 <= 动作.目标等级')
        self.assertEqual(numeric, "")

    def test_mixed_card_guard_and_lineup_alias(self):
        with self.assertRaises(ConditionError):
            compile_expression("解释为何购买英雄", "动作.选中.等级 >= 10")
        expr = compile_expression("解释为何购买英雄", '动作.选中.卡牌类型 == "英雄" and 动作.选中.等级 >= 10')
        self.assertFalse(expr.evaluate({"动作": {"选中": {"卡牌类型": "效果牌", "等级": 10}}}))
        expr = compile_expression("解释为何建议向某阵容发展", '动作.阵容 == "河洛花木兰"')
        self.assertTrue(expr.evaluate({"动作": {"阵容": "河洛花木兰-明先生"}}))

    def test_wildcard_priority_and_render_fallback(self):
        library = load_library({"解释事件": {EVENT: {
            "花木兰-司空震-驱雷": [group("exact", "{{对手.主C.名称}}")],
            "花木兰-*-驱雷": [group("next", "给{{动作.目标英雄.名称}}")],
            "*-*-*": [group("fallback", "最后", 100)],
        }}})
        self.assertEqual(choose(library, EVENT, STATE), {
            "status": "matched", "id": "next", "utterance_id": "next_1",
            "event_id": "transfer", "text": "给花木兰",
        })
        self.assertEqual(choose(library, "解释为何刷新商店", STATE)["status"], "unconfigured")

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ConditionError):
            load_library('{"解释事件":{"解释为何准备战斗":{"":[],"":[]}}}')
