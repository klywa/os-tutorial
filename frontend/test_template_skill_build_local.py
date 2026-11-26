"""Local skill package gates. The event documents and audit trail are synthetic."""
import hashlib
import json
from pathlib import Path
from copy import deepcopy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/wanxiangqi-template/scripts"
with patch.object(sys, "path", [str(SCRIPTS), str(ROOT), *sys.path]):
    import build_local
    import wording


EVENT = "解释为何上阵英雄"
SKELETON = "E02-S01"
LINE = "留下{玩家.剩余能量}能量供下一步使用。"


class LocalBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.events = self.root / "references/events"
        self.events.mkdir(parents=True)
        self.write_event(confirmed=True)
        self.group = {
            "name": "合成测试", "event_name": EVENT, "scope": {}, "priority": 0,
            "expression": 'arg1 is "测试英雄" and 玩家.剩余能量 >= 2',
            "utterances": [LINE], "explanation_before": SKELETON + " 依实际能量判断。",
            "explanation_source": "合成测试来源", "explanation_after": "检查能量边界。",
        }
        self.review = {
            "attempt": 1,
            "name": self.group["name"], "event_name": EVENT, "skeletons": [SKELETON],
            "candidates": [
                {"text": LINE if i == 15 else f"未入选的合成测试句{i}",
                 "accepted": i == 15, "verdict": "合成审稿记录",
                 "improved": True, "improvement": "合成相邻复核记录"} for i in range(16)
            ],
        }
        self.cases = []
        for kind, player in [("positive", {"剩余能量": 2}),
                             ("negative", {"剩余能量": 1}), ("missing", {})]:
            case = {"kind": kind, "matches": kind == "positive",
                    "group": [EVENT, self.group["name"]],
                    "event": {"事件": EVENT, "参数": {"arg1": "测试英雄"}},
                    "state": {"玩家": player}, "reason": "仅改变剩余能量"}
            if kind == "positive":
                case["expected_utterances"] = ["留下2能量供下一步使用。"]
            self.cases.append(case)
        self.package = {
            "kind": "speech-template-library", "schema_version": 3,
            "condition_catalog": json.loads((ROOT / "src/condition/catalog.json").read_text("utf-8")),
            "groups": [self.group], "events": [],
        }

    def write_event(self, *, confirmed):
        heading = "骨架库" if confirmed else "待确认草案"
        (self.events / "E02.md").write_text(
            f"# {EVENT}\n\n## {heading}\n\n- **{SKELETON}** 合成测试骨架\n", "utf-8")

    def validate(self):
        build_local.validate(self.package, [self.review], self.cases, self.events)

    def test_v04_equipment_affinity_can_use_recipient_and_equipment_without_scope(self):
        group = {
            "event_name": "解释为何穿戴装备", "name": "法源之杯给施法者",
            "extra_key": "*-法源之杯", "scope": {},
            "expression": '动作.目标英雄.名称 in ["貂蝉","甄姬"]',
            "utterances": [{"id": "line", "text": "法源之杯能让法系英雄更早施法。"}],
        }
        from check_batch import _check_v04
        _check_v04(group, [])
        group["expression"] += ' or 动作.装备.名称 == "法源之杯"'
        with self.assertRaisesRegex(ValueError, "缺少局面依据"):
            _check_v04(group, [])
        group["expression"] = '动作.目标英雄.名称 == 动作.目标英雄.名称'
        with self.assertRaisesRegex(ValueError, "缺少局面依据"):
            _check_v04(group, [])

    def test_v04_merge_result_can_ground_an_intrinsic_level_threshold(self):
        from check_batch import _check_v04
        group = {
            "event_name": "解释为何合成英雄", "name": "吕布跨升级门槛",
            "extra_key": "吕布", "scope": {},
            "expression": ('动作.英雄.等级 < 40 and 动作.合成后等级 != nil '
                           'and 动作.合成后等级 >= 40'),
            "utterances": [{"id": "line", "text": "吕布到40级后，放完技能能靠攻速接普攻。"}],
        }
        _check_v04(group, [])
        group["expression"] += ' or 动作.英雄.名称 == "吕布"'
        with self.assertRaisesRegex(ValueError, "缺少局面依据"):
            _check_v04(group, [])

    def test_default_model_requires_authorization_and_exact_local_draft(self):
        key = build_local.audit_key(EVENT, "默认模型例", "local-group")
        brief = ("生效条件\n尚未购买\n当前事件\n解释当前操作\n"
                 "局面解释\n提供等级收益\n写法与措辞\n点明受益对象\n建议话术\n- 提高受益英雄等级。")
        draft_path = self.root / "local-draft.json"
        draft = {"kind": "local-default-model-draft", "group_id": "local-group",
                 "wording_brief": brief, "candidates": ["提高受益英雄等级。"]}
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        audit = {"event_name": EVENT, "name": "默认模型例", "group_id": "local-group",
                 "generation_source": "default_model", "default_model_draft": draft_path.name,
                 "candidates": [{"text": draft["candidates"][0]}]}
        with self.assertRaisesRegex(ValueError, "须获得本批授权"):
            build_local.verify_generation([audit], self.root, {key: brief})
        build_local.verify_generation([audit], self.root, {key: brief}, allow_default_model=True)
        audit["candidates"][0]["text"] = "擅自改了原句。"
        with self.assertRaisesRegex(ValueError, "原稿与复核记录不一致"):
            build_local.verify_generation([audit], self.root, {key: brief}, allow_default_model=True)

    def test_named_effect_can_check_observed_target_equipment_count(self):
        from check_batch import _check_v04
        group = {
            "event_name": "解释为何对目标使用效果牌", "name": "空装备目标使用武装重构",
            "extra_key": "武装重构", "scope": {},
            "expression": "动作.目标英雄 != nil and len(动作.目标英雄.装备列表) == 0",
            "utterances": [{"id": "line", "text": "空装备英雄能靠武装重构获得一件装备。"}],
        }
        _check_v04(group, [])
        group["expression"] = "动作.目标英雄 != nil"
        with self.assertRaisesRegex(ValueError, "缺少局面依据"):
            _check_v04(group, [])

    def test_v04_awakening_requires_both_facts_across_branches(self):
        from check_batch import _check_v04
        guard = "动作.英雄.已觉醒 and 动作.英雄.觉醒进度 == 2"
        group = {
            "event_name": "解释为何合成英雄", "name": "甄姬觉醒",
            "extra_key": "甄姬", "scope": {}, "expression": guard,
            "utterances": [{"id": "line", "text": "甄姬觉醒后能从三张登场牌中选一张。"}],
        }
        _check_v04(group, [])
        self.assertTrue(build_local.has_awakening_guard(guard + " and (我方.等级 == 3 or 我方.等级 == 4)"))
        group["expression"] += " or 动作.英雄.已觉醒"
        with self.assertRaisesRegex(ValueError, "缺少局面依据"):
            _check_v04(group, [])

    def test_v04_group_identity_merges_only_equivalent_triggers(self):
        event = "解释为何竞拍目标英雄（第1次拍卖）"
        first = {
            "id": "first", "event_name": event, "name": "旧组名", "syntax_version": "0.4",
            "extra_key": "蔡文姬", "scope": {"lineup": "三分登场-白歌"},
            "expression": "我方.等级 == 2", "review_status": "final_reviewed",
            "utterances": [{"id": "first-line", "text": "第一句"}],
        }
        duplicate = {
            **first, "id": "duplicate", "scope": {},
            "expression": '2 == 我方.等级 and 动作.选中.名称 == "蔡文姬" and (我方.阵容名称 == "三分登场")',
            "last_modified_by": {"kind": "user", "username": "local"},
            "utterances": [
                {"id": "duplicate-line", "text": "第一句", "fixed": True},
                {"id": "manual-line", "text": "人工改句", "fixed": True},
            ],
            "file_comments": [{"id": "comment", "utterance_id": "duplicate-line", "body": "人工批注"}],
        }
        distinct = {**first, "id": "distinct", "expression": "我方.等级 == 3"}
        merged = build_local.merge_duplicate_groups([first, duplicate, distinct])
        self.assertEqual([group["id"] for group in merged], ["first", "distinct"])
        self.assertEqual([build_local.name_template_group(group) for group in merged],
                         ["解释为何竞拍蔡文姬（第1次拍卖）"] * 2)
        self.assertEqual(merged[0]["utterances"], [
            {"id": "first-line", "text": "第一句", "fixed": True},
            {"id": "manual-line", "text": "人工改句", "fixed": True},
        ])
        self.assertEqual(merged[0]["file_comments"][0]["utterance_id"], "first-line")
        self.assertIsNone(merged[0]["review_status"])
        self.assertEqual(first["review_status"], "final_reviewed")
        identical = {**first, "id": "identical"}
        self.assertEqual(build_local.merge_duplicate_groups([first, identical])[0]["review_status"],
                         "final_reviewed")
        conflicting = {**identical, "utterances": [{"id": "first-line", "text": "不同的话术"}],
                       "file_comments": [{"id": "comment", "utterance_id": "first-line"}]}
        combined = build_local.merge_duplicate_groups([first, conflicting])[0]
        self.assertNotEqual(combined["utterances"][1]["id"], "first-line")
        self.assertEqual(combined["file_comments"][0]["utterance_id"], combined["utterances"][1]["id"])

    def test_v04_effect_card_auction_requires_tier_six(self):
        purchase, select, auction = build_local.RELATED_EVENTS[1]
        groups = [{"event_name": event, "name": event, "syntax_version": "0.4",
                   "extra_key": "换帅", "expression": "我方.等级 == 4"} for event in (purchase, select, auction)]
        reviews = [dict(sync={"reason": "交接等级", "tier": "通用"})] * 3
        build_local.verify_related(groups[:2], reviews[:2])
        with self.assertRaisesRegex(ValueError, "拍卖轮次不可取得"):
            build_local.verify_related(groups, reviews)
        reviews = [dict(sync={"reason": "生存", "tier": "通用", "effect_card_tier": 6})] * 3
        with self.assertRaisesRegex(ValueError, "阶级与卡面不符"):
            build_local.verify_related(groups, reviews)
        for group in groups:
            group["extra_key"] = "一线生机"
        with self.assertRaisesRegex(ValueError, "缺少关联组"):
            build_local.verify_related(groups[:2], reviews[:2])
        build_local.verify_related(groups, reviews)

        auction_only = [{"sync": {"reason": "生存", "tier": "通用", "effect_card_tier": 6,
                                 "unavailable": {purchase: "本赛季获取仅为拍卖", select: "本赛季获取仅为拍卖"}}}]
        build_local.verify_related(groups[-1:], auction_only)


    def test_group_dedup_respects_season_and_mode_ranges(self):
        base = {
            "id": "shared", "event_name": EVENT, "name": "小乔", "syntax_version": "0.4",
            "extra_key": "小乔", "expression": "我方.等级 == 2",
            "version": ["S1", "S2"], "mode": ["万象大赛"],
            "utterances": [{"id": "line", "text": "先上小乔"}],
        }
        same_range = {**base, "id": "duplicate", "version": ["S2", "S1"], "mode": "万象大赛"}
        s1 = {**base, "id": "s1", "version": ["S1"]}
        s2 = {**base, "id": "s2", "version": "S2"}
        other_mode = {**base, "id": "other", "mode": ["其他模式"]}
        groups = build_local.merge_duplicate_groups([base, same_range, s1, s2, other_mode])
        self.assertEqual([group["id"] for group in groups], ["shared", "s1", "s2", "other"])

    def test_v04_same_name_scenarios_require_group_identity(self):
        def group(key, level):
            return {
                "id": key, "name": "解释为何上阵甄姬", "event_id": EVENT, "priority": 0,
                "expression": f"我方.等级 == {level}", "explanation": "用途",
                "utterances": [{"id": key + "-line", "text": "测试话术"}],
            }

        def case(key, kind, level, matches):
            return {
                "group": [EVENT, key], "kind": kind, "matches": matches,
                "event": {"事件": EVENT},
                "state": {"我方": {} if level is None else {"等级": level},
                          "动作": {"英雄": {"名称": "甄姬"}}},
            }

        runtime = {"解释事件": {EVENT: {"甄姬": [group("first", 2), group("second", 3)]}}}
        cases = [case("first", "positive", 2, True), case("first", "negative", 3, False),
                 case("first", "missing", None, False), case("second", "positive", 3, True),
                 case("second", "negative", 2, False), case("second", "missing", None, False)]
        self.assertEqual(build_local.check_scenarios(runtime, cases), [])
        scoped = {
            "first": {"version": ["S1", "S2"], "mode": ["万象大赛"]},
            "second": {"version": ["S2"], "mode": ["万象大赛"]},
        }
        cases.extend([
            {**case("first", "positive", 2, True), "season": "S2", "mode": "万象大赛"},
            {**case("second", "negative", 3, False), "season": "S1", "mode": "万象大赛"},
            {**case("first", "negative", 2, False), "season": "S1", "mode": "其他模式"},
        ])
        self.assertEqual(build_local.check_scenarios(runtime, cases, scopes=scoped), [])
        cases[0]["group"][1] = "解释为何上阵甄姬"
        with self.assertRaisesRegex(ValueError, "稳定组 ID"):
            build_local.check_scenarios(runtime, cases)

    def test_confirmed_missing_draft_and_after_confirmation(self):
        self.validate()
        self.review["skeletons"] = ["E02-S99"]
        with self.assertRaisesRegex(ValueError, "已确认骨架"):
            self.validate()
        self.review["skeletons"] = [SKELETON]
        self.write_event(confirmed=False)
        with self.assertRaisesRegex(ValueError, "已确认骨架"):
            self.validate()
        self.write_event(confirmed=True)
        self.validate()

    def test_coverage_requires_audited_sources_and_general_groups(self):
        general = [EVENT, "通用组"]
        specific = [EVENT, "细分组"]
        events = {EVENT: ("E02", {"E02-S01", "E02-S02"})}
        reviews = {
            tuple(general): {"skeletons": ["E02-S01"]},
            tuple(specific): {"skeletons": ["E02-S02"]},
        }
        audit = {"inventory": ["笔记#1"], "units": [{
            "source": "笔记#1",
            "materials": [{
                "decision": "决定何时上阵",
                "events": [{
                    "event": EVENT,
                    "checks": [
                        {"skeleton": "E02-S01", "status": "group", "group": general,
                         "reason": "补前排"},
                        {"skeleton": "E02-S02", "status": "group", "group": specific,
                         "reason": "额外收益", "bases": [general]},
                    ],
                }],
            }],
        }]}
        build_local.verify_coverage(audit, reviews, events)
        missing = deepcopy(audit)
        missing["units"] = []
        with self.assertRaisesRegex(ValueError, "来源"):
            build_local.verify_coverage(missing, reviews, events)
        with self.assertRaisesRegex(ValueError, "通用组"):
            build_local.verify_coverage(audit, {tuple(specific): reviews[tuple(specific)]}, events)
        audit["units"][0]["materials"][0]["events"][0]["checks"][1]["reason"] = ""
        with self.assertRaisesRegex(ValueError, "理由"):
            build_local.verify_coverage(audit, reviews, events)

    def test_used_skeleton_must_be_documented(self):
        self.group["explanation_before"] = "未注明骨架"
        with self.assertRaisesRegex(ValueError, "前置思考"):
            self.validate()

    def test_paused_hand_sale_is_rejected_even_if_skeleton_text_remains(self):
        paused = "解释为何从手牌出售英雄"
        (self.events / "E04.md").write_text(
            f"# {paused}\n\n暂停生成。\n\n## 骨架库\n\n- **E04-S01** 合成历史条目\n", "utf-8")
        self.group.update(event_name=paused, explanation_before="E04-S01")
        self.review.update(event_name=paused, skeletons=["E04-S01"])
        for case in self.cases:
            case["group"][0] = paused
            case["event"]["事件"] = paused
        with self.assertRaisesRegex(ValueError, "未登记事件|暂停"):
            self.validate()

    def test_both_related_families_require_own_skeleton_and_three_outcomes(self):
        for family in (("E01", "E06", "E07"), ("E10", "E11", "E12")):
            for event_id in family:
                with self.subTest(event=event_id):
                    code = event_id + "-S01"
                    events = {EVENT: (event_id, {code})}
                    group = {**self.group, "explanation_before": code}
                    review = {**self.review, "skeletons": [code],
                              "related_events": {s: "已核对该事件的可选对象与收益" for s in family}}
                    build_local.check_review(group, review, events)
                    review["skeletons"] = [next(s for s in family if s != event_id) + "-S01"]
                    with self.assertRaisesRegex(ValueError, "本事件"):
                        build_local.check_review(group, review, events)
                    review["skeletons"] = [code]
                    del review["related_events"][family[-1]]
                    with self.assertRaisesRegex(ValueError, "关联事件"):
                        build_local.check_review(group, review, events)

    def test_shared_equipment_tier_requires_real_groups_and_equal_conditions(self):
        events = [f"解释为何{action}装备" for action in ("穿戴", "铸造", "转移")]
        groups = [dict(event_name=event, name="法杖给法师", scope={},
                       expression='动作.装备.名称 == "法杖" and 动作.目标英雄.等级 >= 10',
                       extra_key="*-法杖") for event in events]
        groups[1]["expression"] = groups[1]["expression"].replace("动作.装备", "动作.目标装备")
        groups[1]["extra_key"] = groups[2]["extra_key"] = "*-*-法杖"
        reviews = [dict(sync={"reason": "法杖适配", "tier": "等级10"}) for _ in groups]
        build_local.verify_related(groups, reviews)
        with self.assertRaisesRegex(ValueError, "转移装备"):
            build_local.verify_related(groups[:2], reviews[:2])
        groups[1]["expression"] = groups[1]["expression"].replace("10", "20")
        with self.assertRaisesRegex(ValueError, "条件"):
            build_local.verify_related(groups, reviews)

    def test_related_hero_tier_requires_both_auctions_and_exclusive_needs_evidence(self):
        events = ["解释为何购买英雄", "解释为何选择英雄",
                  "解释为何竞拍目标英雄（第1次拍卖）", "解释为何竞拍目标英雄（第2次拍卖）"]
        groups = [dict(event_name=event, name="补战力", scope={}, extra_key="测试英雄",
                       expression='动作.选中.名称 == "测试英雄" and 我方.等级 == 2') for event in events]
        reviews = [dict(sync={"reason": "补战力", "tier": "通用"}) for _ in groups]
        build_local.verify_related(groups, reviews)
        for index in (2, 3):
            with self.assertRaisesRegex(ValueError, events[index].split("（")[1]):
                build_local.verify_related(groups[:index] + groups[index+1:], reviews[:index] + reviews[index+1:])
        with self.assertRaisesRegex(ValueError, "证据"):
            build_local.verify_related(groups[:1], [{"sync": {"exclusive": "购买时独有"}}])
        build_local.verify_related(groups[:1], [{"sync": {
            "exclusive": "依赖购买时的独有机制", "evidence": "已核实的规则出处"}}])

    def test_equal_quality_and_missing_comparisons_can_publish(self):
        for candidate in self.review["candidates"]:
            candidate.pop("improvement")
            candidate.pop("improved")
        self.review["candidates"][-1]["improved"] = False
        build_local.validate(self.package, [self.review], self.cases, self.events)

    def test_invented_language_excludes_an_otherwise_accepted_line(self):
        for line in ("他才可能接到雷再出手。", "司空震吃不到落雷。", "给队友加级。", "这样利于叠伤。", "随机落雷才可能让司空震快攻。"):
            with self.subTest(line=line):
                self.group["utterances"] = [line]
                self.review["candidates"][-1]["text"] = line
                with self.assertRaisesRegex(ValueError, "生造词|缩写成快攻"):
                    self.validate()

    def test_approved_wording_is_used_in_the_request_and_export_gate(self):
        request = {"context": {"题面": "保留已核实的事实"}, "fields": {"utterances": "lines"}}
        wording.add_rules(request)
        self.assertEqual(request["context"]["完整写作策略"], wording.writing_strategy())
        terms = wording.approved_rules()
        for term in ("复制卡牌", "降低属性", "临时等级", "物理法术攻击", "材料"):
            self.assertIn(term, terms)
        self.assertEqual(request["context"]["题面"], "保留已核实的事实")
        pattern = wording.banned_pattern()
        for line in ("获得4级临时等级", "承接等级", "增加等级", "把驱雷转移给队友",
                     "命中英雄后触发技能"):
            with self.subTest(allowed=line):
                self.assertIsNone(pattern.search(line))
        for line in ("这件装备留作材料。", "让英雄退场。", "先借装备。", "替队友分走效果。"):
            with self.subTest(banned=line):
                self.group["utterances"] = [line]
                self.review["candidates"][-1]["text"] = line
                with self.assertRaisesRegex(ValueError, "使用禁用表达"):
                    self.validate()

    def test_rejected_candidates_do_not_block_approved_originals(self):
        rejected = self.review["candidates"][0]
        rejected.update(text="可以借装备。", verdict="命中禁用表达：借装备")
        self.validate()
        self.review["candidates"][-1]["accepted"] = False
        with self.assertRaisesRegex(ValueError, "全部达标句"):
            self.validate()

    def test_only_first_batch(self):
        self.review["attempt"] = 2
        with self.assertRaisesRegex(ValueError, "只允许首批"):
            build_local.validate(self.package, [self.review], self.cases, self.events)

    def test_audit_length_normalized_duplicates_verdict_and_all_accepted(self):
        candidates = self.review["candidates"]
        with self.subTest(kind="count"):
            final = candidates.pop()
            with self.assertRaisesRegex(ValueError, "16"):
                self.validate()
            candidates.append(final)
        candidates[0]["accepted"] = True
        candidates[1]["accepted"] = True
        candidates[1]["text"] = candidates[0]["text"] + "。"
        with self.assertRaisesRegex(ValueError, "重复"):
            self.validate()
        candidates[0]["accepted"] = candidates[1]["accepted"] = False
        for field, value, message in [

                ("verdict", "", "verdict"), ("accepted", True, "全部达标句")]:
            with self.subTest(field=field):
                original = candidates[1][field]
                candidates[1][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.validate()
                candidates[1][field] = original

    def test_selection_can_omit_qualified_lines_and_caps_each_pool(self):
        candidates = self.review["candidates"]
        for row in candidates:
            row["qualified"] = True
        self.validate()
        for row in candidates[:7]:
            row["accepted"] = True
        with self.assertRaisesRegex(ValueError, "最多"):
            self.validate()
        for row in candidates[:7]:
            row["accepted"] = False
        for row in candidates[:3] + candidates[-1:]:
            row.update(accepted=True,pool="best")
        with self.assertRaisesRegex(ValueError, "最多"):
            self.validate()
        for row in candidates[:3]:
            row.update(accepted=False,pool=None)
        candidates[-1]["qualified"] = False
        with self.assertRaisesRegex(ValueError, "合格"):
            self.validate()

    def test_actual_rendering_and_single_fact_counterexample(self):
        self.cases[0]["expected_utterances"] = ["留下1能量供下一步使用。"]
        with self.assertRaisesRegex(ValueError, "实际可播话术"):
            self.validate()
        self.cases[0]["expected_utterances"] = ["留下2能量供下一步使用。"]
        self.cases[1]["state"]["玩家"]["剩余能量"] = 2
        with self.assertRaisesRegex(ValueError, "实际命中"):
            self.validate()

    def test_more_specific_group_wins_against_base_group(self):
        narrow = deepcopy(self.group)
        narrow.update(name="高能量局面", expression='arg1 is "测试英雄" and 玩家.剩余能量 >= 4')
        self.package["groups"].append(narrow)
        reviews = [self.review, {**self.review, "name": narrow["name"]}]
        competing = deepcopy(self.cases[0])
        competing["state"]["玩家"]["剩余能量"] = 4
        competing.pop("expected_utterances")
        competing["can_win"] = False
        self.cases.append(competing)
        for kind, player in [("positive", {"剩余能量": 4}),
                             ("negative", {"剩余能量": 3}), ("missing", {})]:
            case = deepcopy(self.cases[0])
            case.update(kind=kind, matches=kind == "positive", group=[EVENT, narrow["name"]],
                        state={"玩家": player})
            case.pop("expected_utterances")
            if kind == "positive":
                case["expected_utterances"] = ["留下4能量供下一步使用。"]
            self.cases.append(case)
        build_local.validate(self.package, reviews, self.cases, self.events)
        competing["can_win"] = True
        with self.assertRaisesRegex(ValueError, "实际可播 False"):
            build_local.validate(self.package, reviews, self.cases, self.events)

    def test_cli_atomic_output_survives_failed_replace(self):
        self.group["wording_brief"] = "\n".join((
            "生效条件", "剩余能量至少两点。", "当前事件", "上阵测试英雄。",
            "局面解释", "当前保留能量供下一步。", "写法与措辞", "直接交代能量用途。",
            "建议话术", "- 留下两点能量供下一步使用。",
        ))
        request = {"context": {"用途": "合成测试", "话术构思": self.group["wording_brief"]},
                   "fields": {"utterances": "lines"}}
        encoded = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
        state = {"phase": "draft", "request": hashlib.sha256(encoded).hexdigest(),
                 "content": {"utterances": [c["text"] for c in self.review["candidates"]]}}
        for filename, data in (("request.json", request), ("state.json", state)):
            (self.root / filename).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        self.review.update(gemini_request="request.json", gemini_state="state.json")
        brief_request = {"context": {"用途": "合成测试"}, "fields": {"wording_brief": "text"}}
        brief_digest = hashlib.sha256(json.dumps(brief_request,ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()
        (self.root / "brief-request.json").write_text(json.dumps(brief_request), "utf-8")
        (self.root / "brief-state.json").write_text(json.dumps({"phase": "draft", "request": brief_digest,
            "content": {"wording_brief": self.group["wording_brief"]}}), "utf-8")
        self.review.update(gemini_brief_request="brief-request.json", gemini_brief_state="brief-state.json")
        build_local.verify_gemini([self.review], self.root)
        (self.root / "state.json").write_text(json.dumps({**state, "feedback_count": 1}), "utf-8")
        with self.assertRaisesRegex(ValueError, "首批原稿"):
            build_local.verify_gemini([self.review], self.root)
        (self.root / "state.json").write_text(json.dumps(state), "utf-8")
        altered = deepcopy(self.review)
        altered["candidates"][0]["text"] = "人工替换过的句子"
        with self.assertRaisesRegex(ValueError, "Gemini 成功响应"):
            build_local.verify_gemini([altered], self.root)
        args = []
        for name, value in [("draft", self.package), ("review", [self.review]), ("cases", self.cases)]:
            path = self.root / (name + ".json")
            path.write_text(json.dumps(value, ensure_ascii=False), "utf-8")
            args.append(str(path))
        coverage = self.root / "coverage.json"
        coverage.write_text(json.dumps({"inventory": ["测试素材"], "units": [{
            "source": "测试素材", "materials": [{"decision": "上阵", "events": [{
                "event": EVENT, "checks": [{"skeleton": SKELETON, "status": "group",
                                         "group": [EVENT, self.group["name"]], "reason": "明确用途"}],
            }]}],
        }]}), "utf-8")
        target = self.root / "我指定的库.json"
        target.write_bytes(b"previous")
        before = set(self.root.iterdir())
        modules = [str(ROOT / "frontend"), str(ROOT / ".codex/skills/wanxiangqi-knowledge/scripts")]
        with patch.object(sys, "path", [*modules, *sys.path]), patch.object(
                build_local, "ROOT", self.root), patch.object(build_local, "SKILL", self.root), patch.object(
                sys, "argv", ["build_local", *args, str(target), "--coverage", str(coverage)]):
            with patch.object(build_local, "preview_import", return_value={"errors": ["未知阵容"]}):
                with self.assertRaises(SystemExit):
                    build_local.main()
            self.assertEqual(target.read_bytes(), b"previous")
            with patch.object(build_local.os, "replace", side_effect=OSError("busy")):
                with self.assertRaises(SystemExit):
                    build_local.main()
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(set(self.root.iterdir()), before)
            build_local.main()
        output = json.loads(target.read_text("utf-8"))
        self.assertEqual(output, {**self.package, "events": [{
            "name": EVENT, "category": "解释类", "signature": f"{EVENT}(arg1: 英雄)",
        }]})
        self.assertEqual(set(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
