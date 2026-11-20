"""Check editorial limits for newly generated v3 groups before import."""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _longest_slot_values(group, catalog, references, cases):
    from src.python.condition import (
        evaluate_condition,
        literal_in_bindings,
        numeric_utterance_bindings,
        utterance_values,
    )

    expression = group.get("expression", "")
    event_name = group.get("event_name")
    literal_bindings = literal_in_bindings(expression, event_name, catalog)
    numeric_paths = set(numeric_utterance_bindings(expression, event_name, catalog))
    longest = {path: max(values, key=len) for path, values in literal_bindings.items()}
    scope = group.get("scope", {})
    used_numeric = numeric_paths.intersection(references)
    if used_numeric:
        for case in cases:
            event, state = case["event"], case["state"]
            player = state.get("玩家", {})
            if event.get("事件") != event_name or any(
                scope.get(key) is not None and scope[key] != player.get(field)
                for key, field in (("player", "使用棋手"), ("lineup", "使用阵容"))
            ):
                continue
            if not evaluate_condition(event, expression, state, catalog):
                continue
            values = utterance_values(expression, event, state, catalog)
            for path in used_numeric.intersection(values):
                longest[path] = max(longest.get(path, ""), values[path], key=len)
    for path in references:
        if path not in longest:
            if path in numeric_paths:
                raise ValueError(f"数字槽位 {{{path}}} 缺少实际命中本组的正例")
            raise ValueError(f"槽位 {{{path}}} 缺少可用的绑定条件")
    return longest


def check(document, *, scenarios=()):
    from src.python.condition import render_bound_utterance, utterance_references

    if document.get("kind") != "speech-template-library" or document.get("schema_version") != 3:
        raise ValueError("请提供 v3 模板库 JSON")
    if not isinstance(document.get("groups"), list):
        raise ValueError("缺少模板组列表")
    cases_by_group = defaultdict(list)
    for case in scenarios:
        if case.get("kind") == "positive" and case.get("matches") is True:
            cases_by_group[tuple(case["group"])].append(case)
    for index, group in enumerate(document["groups"], 1):
        name = group.get("name") or str(index)
        explanation = group.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 300:
            raise ValueError(f"{name}：请填写 300 字以内的说明与依据")
        lines = group.get("utterances")
        if not isinstance(lines, list) or len(lines) < 2:
            raise ValueError(f"{name}：需要多条可独立使用的话术")
        if any(not isinstance(line, str) or not line.strip() for line in lines):
            raise ValueError(f"{name}：每句须完整且不超过 30 字")
        try:
            references = dict.fromkeys(path for line in lines for path in utterance_references(line))
            values = _longest_slot_values(
                group, document.get("condition_catalog"), references,
                cases_by_group[(group.get("event_name"), group.get("name"))],
            ) if references else {}
            if any(len(render_bound_utterance(line, values)) > 30 for line in lines):
                raise ValueError("每句展开后须不超过 30 字")
        except ValueError as error:
            raise ValueError(f"{name}：{error}") from error
        if len({line.strip() for line in lines}) != len(lines):
            raise ValueError(f"{name}：组内有重复话术")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--scenarios", type=Path, help="含数字槽位时提供实际命中各组的正例")
    args = parser.parse_args()
    try:
        document = json.loads(args.package.read_text(encoding="utf-8-sig"))
        scenarios = json.loads(args.scenarios.read_text(encoding="utf-8-sig")) if args.scenarios else []
        if not isinstance(scenarios, list):
            raise ValueError("核验用例须为数组")
        check(document, scenarios=scenarios)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(f"已检查 {len(document['groups'])} 个模板组")
