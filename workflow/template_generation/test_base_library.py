from copy import deepcopy
import unittest

from workflow.template_generation import nodes, run


EVENT = "解释为何购买英雄"
EXPR = '我方.阵容名称 == "开备韩信"'


def group(gid, expression=EXPR, key="韩信", *, empty=False):
    return {"id": gid, "name": gid, "event_name": EVENT, "syntax_version": "0.4",
            "scope": {"player": None, "lineup": None}, "expression": expression,
            "effective_expression": expression, "extra_key": key, "priority": 0,
            "instruction": "解释韩信在开备韩信中的战斗作用。",
            "utterances": [] if empty else [{"id": "u_" + gid, "text": "韩信的挑飞和冲锋承担收割。"}]}


def library(*groups):
    return {"kind": "speech-template-library", "schema_version": 3,
            "events": [nodes._json(nodes.REF / "events.json")[EVENT]["portable"]],
            "groups": list(groups)}


class BaseLibraryTest(unittest.TestCase):
    def test_playability_uses_only_publishable_groups_and_sentences(self):
        from workflow.template_generation import base_library

        visible = group("visible", expression="")
        visible["utterances"].append({"id": "ignored", "text": "已忽略", "ignored": True})
        hidden = {**group("hidden", expression=""), "priority": 100, "ignored": True}
        on_hold = {**group("hold", expression=""), "priority": 100, "publication_hold": "待核实"}
        compiled = base_library.runtime(library(visible, hidden, on_hold))
        _, winners = nodes.winning_pool(compiled, EVENT, {"动作": {"选中": {"名称": "韩信"}}})
        self.assertEqual([(row["id"], row["utterance_id"]) for row in winners], [("visible", "u_visible")])

    def test_legacy_base_upgrade_preserves_identity_and_removes_redundant_fact(self):
        from workflow.template_generation import base_library

        seed = group("seed", '动作.选中.名称 == "韩信" and ' + EXPR, empty=True)
        original = library(seed)
        upgraded = base_library.migrate(original)["groups"][0]
        self.assertEqual(upgraded, {**seed, "syntax_version": "0.5", "expression": EXPR,
                                    "effective_expression": EXPR})
        self.assertEqual(original["groups"][0]["syntax_version"], "0.4")

    def test_command_accepts_seed_library(self):
        args = run.parser().parse_args(["start", "note.md", "--base-library", "base.json", "--output",
                                         "target.json", "--run-dir", "run", "--model", "offline"])
        self.assertEqual(args.base_library.name, "base.json")

    def test_merge_preserves_seed_structure_and_keeps_only_new_definitions(self):
        from workflow.template_generation import base_library

        seed, original = group("seed", empty=True), group("legacy", key="雅典娜")
        original.pop("instruction")
        original_state = deepcopy(original)
        duplicate = group("duplicate", '("开备韩信" == 我方.阵容名称)')
        refinement = group("refinement", EXPR + ' and 我方.等级 >= 4')
        filled = {"utterances": group("seed")["utterances"], "explanation_before": "从原文核实战斗收益"}
        merged, skipped = base_library.merge(library(seed, original), {"seed": filled}, library(duplicate, refinement))
        self.assertEqual([g["id"] for g in merged["groups"]], ["seed", "legacy", "refinement"])
        self.assertEqual(skipped, {"duplicate": "seed"})
        self.assertEqual(merged["groups"][0], {**seed, **filled})
        self.assertEqual(merged["groups"][1], original_state)

    def test_fill_refuses_structural_changes_and_unfinished_groups(self):
        from workflow.template_generation import base_library

        seed = group("seed", empty=True)
        for patch in ({}, {"seed": {"utterances": []}}, {"seed": {"utterances": group("seed")["utterances"],
                                                       "expression": "True"}}):
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, "seed"):
                base_library.merge(library(seed), patch, library())

    def test_seed_conditions_only_accept_explanation_and_keep_the_registered_key(self):
        from workflow.template_generation import base_library, seed_nodes

        seed = group("seed", empty=True)
        point = base_library.seed_point(seed, "韩信以挑飞和冲锋收割。")
        previous = {"point": point, "seed": seed}
        result = {"point_id": point["id"], "reason": "挑飞", "limited": "开备韩信",
                  "not_limited": "搭档", "expected": "收割", "wording": "使用正式对象名"}
        result_row = seed_nodes.validate("conditions", result, previous)["conditions"][0]
        self.assertEqual(result_row["expression"], EXPR)
        self.assertEqual(result_row["extra_key"], "韩信")
        self.assertEqual([case["actual"] for case in result_row["cases"]], [True, False, False])
        with self.assertRaisesRegex(ValueError, "只接受解释角度"):
            seed_nodes.validate("conditions", {**result, "expression": ""}, previous)

    def test_previous_trace_only_carries_unchanged_sentences(self):
        from workflow.template_generation import base_library

        original = group("legacy")
        old = {"groups": {"legacy": {"point_id": "p1", "knowledge_list_id": "a1", "event_id": "e1",
                                      "condition_id": "c1", "sentences": {"u_legacy": original["utterances"][0]["text"]},
                                      "prompt_ids": {"identify": "prompt"}, "writing": {}}},
               "knowledge_lists": {"a1": []}, "prompts": {"prompt": "原始输入"},
               "points": {"p1": {"events": [{"id": "e1"}], "conditions": [{"id": "c1", "event_id": "e1"}]}}}
        new = {key: {} for key in old}
        self.assertEqual(base_library.inherit_trace(new, old, [original]), {"legacy"})
        self.assertEqual(new["groups"]["legacy"]["point_id"], "base-history/p1")
        self.assertEqual(new["prompts"]["base-history/prompt"], "原始输入")
        original["utterances"][0]["text"] = "已编辑"
        self.assertEqual(base_library.inherit_trace({key: {} for key in old}, old, [original]), set())


if __name__ == "__main__":
    unittest.main()
