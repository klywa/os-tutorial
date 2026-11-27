"""Read workflow drafts and merge generated text into their fixed group definitions."""
from copy import deepcopy
import json
import re

from frontend.template_v04 import upgrade_rule
from src.python.condition.v04 import catalog, compile_expression, load_library, matching_keys, validate_key, winning_pool

from . import nodes
from .editorial import _condition_key


FILL_FIELDS = {"utterances", "explanation_before", "explanation_source", "explanation_after"}


def migrate(library):
    """Upgrade rule syntax while preserving the editable document and group identities."""
    document = deepcopy(nodes._object(library, "模板库"))
    groups = nodes._rows(document.get("groups"), "模板组")
    for index, group in enumerate(groups):
        if group.get("syntax_version") == "0.4":
            upgraded = upgrade_rule(group, group["event_name"])
            upgraded["effective_expression"] = nodes.effective_expression(
                upgraded.get("scope", {}), upgraded["expression"])
            groups[index] = upgraded
    if "condition_catalog" in document:
        document["condition_catalog"] = catalog()
    return document


def validate_library(library, *, draft=False):
    document = deepcopy(nodes._object(library, "模板库"))
    if document.get("kind") != "speech-template-library" or document.get("schema_version") != 3:
        raise ValueError("已有库须使用 schema 3 便携模板库格式")
    groups = nodes._index(document.get("groups"), "模板组")
    players, lineups = nodes._scope_catalog()
    for group in groups.values():
        nodes.validate_rule(group, group["event_name"])
        # File annotations and group visibility stay with the local document.
        group.pop("file_comments", None)
        group.pop("ignored", None)
        scope = nodes._portable_scope(group.get("scope", {}), players, lineups)
        if scope.get("lineup") and not scope.get("player"):
            group["expression"] = nodes.effective_expression(scope, group["expression"])
            scope = {}
        group["scope"] = scope
        lines = nodes._rows(group.get("utterances"), "utterances")
        if "instruction" in group or not lines:
            nodes._text(group.get("instruction"), f"模板组 {group['id']} 的 instruction")
        if not lines and draft:
            # Only exercise the ordinary portable schema. Never store this placeholder.
            group["utterances"] = [{"id": "draft_validation", "text": "草稿格式校验"}]
    nodes.decode_portable(document, {"events": [], "groups": []}, players, lineups)


def definition(group):
    event = group["event_name"]
    expression = nodes.effective_expression(group.get("scope", {}), group["expression"])
    return event, group["extra_key"], _condition_key(compile_expression(event, expression).node)


def merge(library, fills, discovered):
    result = deepcopy(library)
    known = {}
    ids = set()
    outstanding = set(fills)
    for group in result["groups"]:
        gid = group["id"]
        ids.add(gid)
        known.setdefault(definition(group), gid)
        if not group["utterances"]:
            patch = fills.get(gid, {})
            if not patch.get("utterances") or patch.keys() - FILL_FIELDS:
                raise ValueError(f"模板组 {gid} 的补全缺少话术或修改了固定字段")
            group.update(deepcopy(patch))
            outstanding.remove(gid)
    if outstanding:
        raise ValueError("补全引用了非空或不存在的模板组：" + "、".join(sorted(outstanding)))

    definitions = {event["name"]: event for event in result["events"]}
    new_events = {event["name"]: event for event in discovered["events"]}
    skipped = {}
    for group in discovered["groups"]:
        gid, key = group["id"], definition(group)
        if key in known:
            skipped[gid] = known[key]
            continue
        if gid in ids:
            raise ValueError(f"新增模板组 ID 冲突：{gid}")
        event = group["event_name"]
        if event not in definitions:
            definitions[event] = new_events[event]
            result["events"].append(deepcopy(definitions[event]))
        ids.add(gid)
        known[key] = gid
        result["groups"].append(deepcopy(group))
    return result, skipped


def inherit_trace(detail, previous, groups):
    """Keep provenance for unchanged groups when the old detail matches the base file."""
    carried = set()
    if not previous or any(not isinstance(previous.get(key), dict)
                           for key in ("groups", "points", "knowledge_lists", "prompts")):
        return carried
    for group in groups:
        gid = group["id"]
        entry = previous["groups"].get(gid)
        if not isinstance(entry, dict) or entry.get("sentences") != {
                row["id"]: row["text"] for row in group["utterances"]}:
            continue
        try:
            pid, kid = entry["point_id"], entry["knowledge_list_id"]
            point, knowledge = previous["points"][pid], previous["knowledge_lists"][kid]
            prompts = {stage: (ref, previous["prompts"][ref]) for stage, ref in entry["prompt_ids"].items()}
            if not (isinstance(knowledge, list) and isinstance(entry["writing"], dict) and any(
                    event["id"] == entry["event_id"] for event in point["events"]) and any(
                    condition["id"] == entry["condition_id"] and condition["event_id"] == entry["event_id"]
                    for condition in point["conditions"])):
                continue
        except (AttributeError, KeyError, TypeError):
            continue
        history = lambda identity: "base-history/" + identity
        detail["points"][history(pid)] = point
        detail["knowledge_lists"][history(kid)] = knowledge
        detail["prompts"].update({history(ref): prompt for ref, prompt in prompts.values()})
        detail["groups"][gid] = {**entry, "point_id": history(pid), "knowledge_list_id": history(kid),
                                 "prompt_ids": {stage: history(ref) for stage, (ref, _) in prompts.items()}}
        carried.add(gid)
    return carried


def runtime(library):
    events = {}
    for group in library["groups"]:
        if group.get("ignored") or group.get("publication_hold"):
            continue
        utterances = [{"id": line["id"], "text": line["text"]} for line in group["utterances"]
                      if not line.get("ignored")]
        if not utterances:
            continue
        event = group["event_name"]
        expression = nodes.effective_expression(group.get("scope", {}), group["expression"])
        row = {"id": group["id"], "event_id": event, "name": group["name"], "expression": expression,
               "priority": group.get("priority", 0), "explanation": group.get("explanation_before", ""),
               "utterances": utterances}
        events.setdefault(event, {}).setdefault(group["extra_key"], []).append(row)
    return load_library({"解释事件": events}, strict=True)


def check_playability(library, checks, refinements=None):
    compiled = runtime(library)
    refinements = refinements or {}
    for group in library["groups"]:
        gid = group["id"]
        if gid not in checks:
            continue
        wanted = {line["id"] for line in group["utterances"]}
        heard = set()
        base_id = refinements.get(gid)
        for case in checks[gid]:
            if case["kind"] == "positive":
                _, winners = winning_pool(compiled, group["event_name"], case["state"])
                heard.update(row["utterance_id"] for row in winners if row["id"] == gid)
                if base_id and ({gid, base_id} & {row["id"] for row in winners}) != {gid}:
                    raise ValueError(f"细分组 {gid} 未在正例胜出：{case['reason']}")
            elif base_id and case.get("fallback") is True:
                _, winners = winning_pool(compiled, group["event_name"], case["state"])
                if ({gid, base_id} & {row["id"] for row in winners}) != {base_id}:
                    raise ValueError(f"细分组 {gid} 未回退到 {base_id}：{case['reason']}")
        if wanted - heard:
            raise ValueError(f"{gid} 在合并库正例中缺少实际可播的入选句")


def seed_point(group, source):
    event = group["event_name"]
    names = set(validate_key(event, group["extra_key"])) - {"*"}
    if "装备" in event:
        type_name = "装备"
    elif "天赋" in event:
        type_name = "天赋"
    elif "效果牌" in event:
        type_name = "效果牌"
    else:
        type_name = "英雄定位"
    paragraphs = [(number, line) for number, line in enumerate(source.splitlines(), 1) if line.strip()]
    ranked = sorted(paragraphs, key=lambda pair: -sum(name in pair[1] for name in names))
    references = [{"location": f"第 {number} 行", "quote": line.strip()} for number, line in ranked[:12]]
    return {"id": nodes._stable("base", group["id"]), "type": type_name, "content": group["instruction"],
            "strategy": group["instruction"], "principle": group["instruction"], "scope": group["expression"],
            "prerequisite": group["expression"], "source_refs": references[:1],
            "related_refs": references[1:], "related_ids": []}


def fixed_cases(group):
    """Build tests in code for the exact lineup-only expression used by the initializer."""
    effective = nodes.effective_expression(group.get("scope", {}), group["expression"])
    lineup = re.fullmatch(r'我方\.阵容名称 == ("(?:[^"\\]|\\.)+")', effective)
    if not lineup:
        return None
    event = group["event_name"]
    definition = catalog()["events"][event]
    fields = catalog()["actions"][definition["action"]]
    action = {}
    for field, value in zip(definition["key"], validate_key(event, group["extra_key"])):
        field_type = fields[field]
        if value == "*":
            value = "0" if field_type == "int" else "未限定对象"
        action[field] = {"名称": value} if field_type == "卡牌" else int(value) if field_type == "int" else value
    name = json.loads(lineup[1])
    return [{"kind": kind, "state": {"动作": action, "我方": player}, "reason": reason}
            for kind, player, reason in (
                ("positive", {"阵容名称": name}, "事件对象及阵容均匹配"),
                ("negative", {"阵容名称": name + "其他阵容"}, "阵容不匹配"),
                ("missing", {}, "阵容名称缺失"))]


def validate_cases(group, cases):
    event, extra_key = group["event_name"], group["extra_key"]
    key = validate_key(event, extra_key)
    expression = compile_expression(event, nodes.effective_expression(group.get("scope", {}), group["expression"]))
    kinds = set()
    positives = []
    missing = []
    for case in nodes._rows(cases, "用例"):
        nodes._fields(nodes._object(case, "用例"), "kind reason")
        kind = case["kind"]
        state = nodes._object(case.get("state"), "state")
        expected = kind == "positive"
        actual = bool(matching_keys([key], event, state)) and expression.evaluate(state) is True
        if kind not in {"positive", "negative", "missing"} or actual != expected:
            raise ValueError(f"{group['id']} 的固定条件未通过 {kind} 用例")
        case.update(actual=actual, expected=expected)
        kinds.add(kind)
        if expected:
            positives.append(state)
        elif kind == "missing":
            missing.append(state)
    if kinds != {"positive", "negative", "missing"} or any(
            not any(nodes._unknown_variant(state, positive) for positive in positives) for state in missing):
        raise ValueError(f"{group['id']} 需要正例、反例及从正例移除必要值的缺值用例")
