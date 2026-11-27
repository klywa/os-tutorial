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
        self.group_drawn = False
        self.playable_count = 0

    def choice(self, choices):
        if self.group_drawn:
            self.playable_count = len(choices) if self.offered else 0
            return choices[self.line_index] if self.offered else choices[0]
        self.group_drawn = True
        for item in choices:
            if item is self.lines:
                self.offered = True
                return item
        return choices[0]


def check(config, cases, *, require_all=True, scopes=None, strict=False):
    from src.python.condition import choose_utterance, evaluate_condition

    if "解释事件" in config:
        return check_v04(config, cases, require_all=require_all, scopes=scopes, strict=strict)
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
            or not all(isinstance(line, str) for line in expected_utterances)
        ):
            raise ValueError(f"{key}：请按配置顺序填写所有预期可播话术")
        if matches != expected or probe.offered != won:
            errors.append(f"{key} / {case.get('reason', kind)}：实际命中 {matches}，实际可播 {probe.offered}")
            continue
        if expected_utterances is not None:
            if len(expected_utterances) != probe.playable_count:
                errors.append(f"{key} / {case.get('reason', kind)}：实际有 {probe.playable_count} 条可播话术")
                continue
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


def check_v04(config, cases, *, require_all=True, scopes=None, strict=False):
    from src.python.condition.v04 import load_library, matching_keys, winning_pool
    from src.python.condition.v04_legacy import adapt

    library = load_library(config, strict=True) if strict else load_library(config)
    groups = {(event, group["id"]): (pattern, group, expression)
              for event, keys in library.items() for pattern, rows in keys.items()
              for group, expression, _ in rows}
    legacy_names = defaultdict(list)
    for key, (_, group, _) in groups.items():
        legacy_names[(key[0], group["name"])].append(key)
    errors, coverage = [], defaultdict(set)
    checked = set()
    scoped_libraries = {}
    for case in cases:
        key = tuple(case["group"])
        if key not in groups:
            named = legacy_names.get(key, [])
            if len(named) > 1:
                raise ValueError(f"{key}：同事件存在重名组，请用稳定组 ID")
            if named:
                key = named[0]
        checked.add(key)
        if key not in groups:
            errors.append(f"{key}：发布库中没有该组")
            continue
        pattern, group, condition = groups[key]
        event, state = case["event"], case["state"]
        name = event["事件"]
        if "参数" in event:
            name, state = adapt(event, state)
        kind, expected = case["kind"], case["matches"]
        if kind not in ("positive", "negative", "missing") or type(expected) is not bool:
            raise ValueError(f"{key}：用例类别或预期命中值无效")
        active = library
        eligible = True
        if "season" in case or "mode" in case:
            from templates_schema import group_applies
            if scopes is None:
                raise ValueError(f"{key}：范围用例须提供发布前的模板组")
            season, mode = case.get("season", "S1"), case.get("mode")
            scope_key = season, mode
            if scope_key not in scoped_libraries:
                scoped_libraries[scope_key] = {
                    event_name: {
                        event_key: [row for row in rows if group_applies(scopes[row[0]["id"]], season, mode)]
                        for event_key, rows in keys.items()
                    }
                    for event_name, keys in library.items()
                }
            active = scoped_libraries[scope_key]
            eligible = group_applies(scopes[group["id"]], season, mode)
        matched = eligible and name == key[0] and bool(matching_keys([pattern], name, state)) and condition.evaluate(state) is True
        _, offered = winning_pool(active, name, state)
        lines = [row["text"] for row in offered if row["id"] == group["id"]]
        desired = case.get("can_win", expected)
        if matched != expected or bool(lines) != desired or "expected_utterances" in case and lines != case["expected_utterances"]:
            errors.append(f"{key} / {case.get('reason', kind)}：实际命中 {matched}，实际可播 {lines}")
            continue
        coverage[key].add(kind)
        if lines:
            coverage[key].add("winner")
    required = groups if require_all else checked
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
    parser.add_argument("--scopes", type=Path, help="用于赛季或模式用例的编审模板包")
    parser.add_argument("--groups-in-cases", action="store_true", help="仅要求用例中列出的组有完整覆盖")
    parser.add_argument("--strict", action="store_true", help="按 v0.5 校验运行树中的条件与具体键")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path[:0] = [str(root), str(root / "frontend")]
    config = read(args.published)
    cases = read(args.cases)
    scopes = {group["id"]: group for group in read(args.scopes)["groups"]} if args.scopes else None
    errors = check(config, cases, require_all=not args.groups_in_cases, scopes=scopes, strict=args.strict)
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    count = len(config["groups"]) if "groups" in config else sum(
        len(groups) for keys in config["解释事件"].values() for groups in keys.values())
    print(f"已核对 {count} 个可播组、{len(cases)} 项用例")


