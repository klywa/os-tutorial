"""Check group-level expectations against an entire published speech library."""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class PreferGroup:
    """Observe whether the runtime offers this group's lines at its final draw."""
    def __init__(self, lines, line_index=0):
        self.lines = lines
        self.line_index = line_index
        self.offered = False

    def choice(self, choices):
        if choices is self.lines:
            return choices[self.line_index]
        for item in choices:
            if item is self.lines:
                self.offered = True
                return item
        return choices[0]


def check(config, cases, *, require_all=True):
    from src.python.condition import choose_utterance, evaluate_condition

    catalog = config["condition_catalog"]
    groups = {(g["event_name"], g["name"]): g for g in config["groups"]}
    if not groups or not isinstance(cases, list) or not cases:
        raise ValueError("请提供非空正式库及核验用例")
    if len(groups) != len(config["groups"]):
        raise ValueError("同一事件存在重名模板组，无法唯一定位")
    coverage = defaultdict(set)
    errors = []
    for case in cases:
        key = tuple(case["group"])
        group = groups[key]
        event, state = case["event"], case["state"]
        kind = case["kind"]
        expected = case["matches"]
        if kind not in ("positive", "negative", "missing") or type(expected) is not bool:
            raise ValueError(f"{key}：用例类别或预期命中值无效")
        if (kind == "positive" and not expected) or (kind == "negative" and expected):
            raise ValueError(f"{key}：用例类别与预期命中值不一致")
        player = state.get("玩家", {})
        scope = group.get("scope", {})
        matches = (event["事件"] == key[0] and
                   all(scope.get(dim) is None or scope[dim] == player.get(field)
                       for dim, field in (("player", "使用棋手"), ("lineup", "使用阵容"))) and
                   evaluate_condition(event, group["expression"], state, catalog))
        probe = PreferGroup(group["utterances"])
        first_utterance = choose_utterance(config, event, state, rng=probe)
        won = case.get("can_win", expected)
        if type(won) is not bool or (won and not expected):
            raise ValueError(f"{key}：最终可播预期无效")
        expected_utterances = case.get("expected_utterances")
        if "expected_utterances" in case and (
            not won or not isinstance(expected_utterances, list)
            or len(expected_utterances) != len(group["utterances"])
            or not all(isinstance(line, str) for line in expected_utterances)
        ):
            raise ValueError(f"{key}：请按配置顺序填写所有预期可播话术")
        if matches != expected or probe.offered != won:
            errors.append(f"{key} / {case.get('reason', kind)}：实际命中 {matches}，实际可播 {probe.offered}")
            continue
        if expected_utterances is not None:
            actual_utterances = [first_utterance]
            actual_utterances.extend(
                choose_utterance(config, event, state, rng=PreferGroup(group["utterances"], index))
                for index in range(1, len(expected_utterances))
            )
            if actual_utterances != expected_utterances:
                errors.append(f"{key} / {case.get('reason', kind)}：实际可播话术 {actual_utterances}")
                continue
        coverage[key].add(kind)
        if probe.offered:
            coverage[key].add("winner")
    required = groups if require_all else dict.fromkeys(tuple(case["group"]) for case in cases)
    for key in required:
        missing = {"positive", "winner", "negative", "missing"} - coverage[key]
        if missing:
            errors.append(f"{key}：缺少通过的用例 {', '.join(sorted(missing))}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("published", type=Path, help="GET /api/templates/published 的完整结果")
    parser.add_argument("cases", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--groups-in-cases", action="store_true", help="仅要求用例中列出的组有完整覆盖")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    config = read(args.published)
    cases = read(args.cases)
    errors = check(config, cases, require_all=not args.groups_in_cases)
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print(f"已核对 {len(config['groups'])} 个可播组、{len(cases)} 项用例")


