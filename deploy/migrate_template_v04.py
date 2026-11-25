"""Preview or apply the local v0.4 migration with a revision fence."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / ".codex/skills/wanxiangqi-knowledge/scripts")]

import json_store
import template_package
import template_v04
import templates_store as store
from src.python.condition import choose_utterance, evaluate_condition, render_bound_utterance, utterance_values
from src.python.condition.v04 import load_library, matching_keys, render, winning_pool
from src.python.condition.v04_legacy import adapt

REFINED_PRIORITY = {
    "杨玉环穿戴法源之杯": 1,
    "单挂苏烈时使用小菟助力": 1,
    "单挂狂铁时使用小菟助力": 1,
    "觉醒干将单挂靠击败接着长等级": 1,
    "全军动员触发亚连整备": 1,
    "全军动员触发狂铁整备": 1,
    "全军动员多次触发朵莉亚的整备联动": 1,
    "五级遇百级主力时先用小菟送福": 2,
    "五级血紧四人先送福": 1,
    "月之特调生效后先送福再助力": 1,
    "狂铁和朵莉亚在场时上米莱狄": 1,
    "重构干将的双剑为基础装备": 1,
}


def migrate(root, *, commit_revision=None, scenarios=None):
    public, meta = store._load(root)
    revision = store._revision(public, meta)
    events = {event["id"]: event for event in public["events"]}
    entities, notes, _ = store.validation_context(root, before=public, metadata=meta)
    converted = []
    changes = []
    holds = []
    for initial in public["groups"]:
        event = events[initial["event_id"]]["name"]
        new = initial
        if initial.get("syntax_version") != template_v04.VERSION:
            new = template_v04.translate(initial, event)
            if new["name"] in REFINED_PRIORITY:
                new["priority"] = REFINED_PRIORITY[new["name"]]
            if new["name"] == "主力两件装备时选重装上阵":
                new["extra_key"] = "*"
        converted.append(new)
        if new != initial:
            changes.append({"kind": "group", "action": "put", "id": new["id"], "value": new})
        if new.get("publication_hold"):
            holds.append({"id": new["id"], "name": new["name"], "reason": new["publication_hold"]})
    proposed = {**public, "groups": converted}
    tree = template_v04.runtime_tree(store._exportable(proposed), entities, notes, meta)
    compiled = load_library(tree)
    mig = {"revision": revision, "groups": len(converted), "utterances": sum(len(g["utterances"]) for g in converted),
           "changed": len(changes), "published": sum(len(rows) for keys in tree["解释事件"].values() for rows in keys.values()),
           "held": holds, "ignored": sum(bool(g.get("ignored")) for g in converted)}
    report = {"summary": mig, "changes": [], "historical_expectation_differences": []}
    if changes:
        store.preview_changes(root, revision, changes)
    if scenarios:
        legacy = template_package.encode(store._exportable(public), entities, notes, meta,
                                         authoring=False, stable_ids=True, root=root)
        report.update(replay(scenarios, legacy, tree, compiled, holds))
    if commit_revision is not None:
        if revision != commit_revision:
            raise ValueError("模板库版本已改变。请重新预览。")
        if not scenarios or report["changes"] or report["winner_differences"] or report["groups_without_scenarios"]:
            raise ValueError("迁移提交需要通过新旧回放")
        if changes:
            original_path = Path(root) / store.PUBLISHED
            legacy_path = Path(root) / store.PUBLISHED_V3
            rollback = Path(root) / "raw/templates/v04-rollback" / f"{revision}.json"
            if not rollback.exists():
                json_store.write_file(rollback, {"revision": revision, "public": public, "metadata": meta})
            if original_path.exists() and not legacy_path.exists():
                original = json_store.read(original_path)
                if original.get("schema_version") == 3:
                    json_store.write_file(legacy_path, original)
            store.apply(root, revision, changes, actor="v0.4 语法迁移",
                        manual={"source": "syntax-migration", "reason": "本地正式库语法切换"})
    return report


def replay(scenarios, legacy, tree, compiled, holds):
    source = legacy["condition_catalog"]
    before = {(row["event_name"], row["name"]): row for row in legacy["groups"]}
    after = {(event, group["name"]): (key, group) for event, keys in tree["解释事件"].items()
             for key, groups in keys.items() for group in groups}
    held = {row["name"] for row in holds}
    diffs, stale, winners, seen, seen_cases = [], [], [], set(), set()
    held_config = {**legacy, "groups": [row for row in legacy["groups"] if row["name"] not in held]}
    names_by_id = {row["id"]: row["name"] for row in legacy["groups"]}
    lines_by_id = {id(row["utterances"]): row["id"] for row in held_config["groups"]}

    class PreviousWinners:
        groups = ()

        def choice(self, candidates):
            if isinstance(candidates[0], list):
                self.groups = tuple(lines_by_id[id(lines)] for lines in candidates)
            return candidates[0]

    checked = 0
    for row in scenarios:
        group = tuple(row.get("group", ()))
        if group not in before or group[1] in held:
            continue
        old = before[group]
        event, state = row["event"], row["state"]
        old_match = evaluate_condition(event, old["effective_expression"], state, source)
        if row.get("matches") is not None and old_match != row["matches"]:
            stale.append({"group": group, "kind": row["kind"], "expected": row["matches"], "old": old_match})
        name, snapshot = adapt(event, state, source)
        key, new = after[group]
        pattern = tuple(key.split("-")) if key else ()
        new_match = bool(matching_keys([pattern], name, snapshot))
        if new_match:
            rule = next(rule for record, rule, _ in compiled[name][pattern] if record["id"] == new["id"])
            new_match = rule.evaluate(snapshot) is True
        if old_match != new_match:
            diffs.append({"group": group, "kind": row["kind"], "before": old_match, "after": new_match,
                          "event": event, "state": state})
        if old_match and new_match:
            from src.python.condition import utterance_references
            refs = {ref for line in old["utterances"] for ref in utterance_references(line)}
            values = utterance_values(old["expression"], event, state, source, references=refs) if refs else {}
            old_lines = [render_bound_utterance(line, values) if utterance_references(line) else line for line in old["utterances"]
                         if set(utterance_references(line)) <= values.keys()]
            new_lines = [line for entry in new["utterances"] if (line := render(name, entry["text"], snapshot)) is not None]
            if old_lines != new_lines:
                diffs.append({"group": group, "kind": row["kind"], "before": old_lines, "after": new_lines,
                              "event": event, "state": state})
        case = json.dumps([event, state], ensure_ascii=False, sort_keys=True)
        if case not in seen_cases and row["kind"] == "positive":
            seen_cases.add(case)
            previous = PreviousWinners()
            choose_utterance(held_config, event, state, rng=previous)
            _, options = winning_pool(compiled, name, snapshot)
            old_winners = set(previous.groups)
            new_winners = {option["id"] for option in options}
            if old_winners != new_winners:
                winners.append({"group": group, "before": [names_by_id[gid] for gid in sorted(old_winners)],
                                "after": [names_by_id[gid] for gid in sorted(new_winners)], "event": event, "state": state})
        checked += 1
        seen.add(group)
    return {"changes": diffs, "winner_differences": winners, "historical_expectation_differences": stale, "scenarios_checked": checked,
            "groups_checked": len(seen), "groups_without_scenarios": [item for item in before if item not in seen and item[1] not in held]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--commit-revision")
    args = parser.parse_args()
    report = migrate(ROOT, commit_revision=args.commit_revision, scenarios=json_store.read(args.scenarios))
    json_store.write_file(args.report, report)
    print(json.dumps({**report["summary"], "scenarios_checked": report["scenarios_checked"],
                      "differences": len(report["changes"]), "winner_differences": len(report["winner_differences"]),
                      "report": str(args.report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
