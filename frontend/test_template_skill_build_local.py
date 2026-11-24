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
        terms = request["context"]["话术词表"]
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
        request = {"context": {"用途": "合成测试"}, "fields": {"utterances": "lines"}}
        encoded = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
        state = {"phase": "draft", "request": hashlib.sha256(encoded).hexdigest(),
                 "content": {"utterances": [c["text"] for c in self.review["candidates"]]}}
        for filename, data in (("request.json", request), ("state.json", state)):
            (self.root / filename).write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        self.review.update(gemini_request="request.json", gemini_state="state.json")
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
        target = self.root / "我指定的库.json"
        target.write_bytes(b"previous")
        before = set(self.root.iterdir())
        modules = [str(ROOT / "frontend"), str(ROOT / ".codex/skills/wanxiangqi-knowledge/scripts")]
        with patch.object(sys, "path", [*modules, *sys.path]), patch.object(
                build_local, "ROOT", self.root), patch.object(build_local, "SKILL", self.root), patch.object(
                sys, "argv", ["build_local", *args, str(target)]):
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
        self.assertEqual(json.loads(target.read_text("utf-8")), self.package)
        self.assertEqual(set(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
