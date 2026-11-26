"""Prompt material, branch contracts and portable v0.4 assembly."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
from uuid import NAMESPACE_URL, uuid5

from frontend.template_v04 import effective_expression, key_for, validate_rule
from src.python.condition.v04 import (
    compile_expression, load_library, matching_keys, validate_key, winning_pool,
)
from .editorial import check_group

HERE = Path(__file__).resolve().parent
REF = HERE / "references"
# The project's portable decoder uses the frontend directory for sibling imports.
FRONTEND = str(HERE.parents[1] / "frontend")
if FRONTEND not in sys.path:
    sys.path.insert(0, FRONTEND)
from template_package import decode as decode_portable

STAGES = ("identify", "enrich", "events", "conditions", "phrases")
SEASONS = ("S1", "S2")


@lru_cache(maxsize=None)
def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} 须为列表")
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} 须为对象")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 须为非空文本")
    return value


def _strings(value, label):
    return [_text(item, label) for item in _rows(value, label)]


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError(f"身份标识无效：{value!r}")
    return value


def _index(rows, label, key="id"):
    index = {}
    for row in _rows(rows, label):
        identity = _id(_object(row, label).get(key))
        if identity in index:
            raise ValueError(f"{label} 重复标识：{identity}")
        index[identity] = row
    return index


def _fields(row, fields):
    for name in fields.split():
        _text(row.get(name), name)


def _source_refs(result, source):
    refs = _rows(result.get("source_refs"), "source_refs")
    if not refs:
        raise ValueError("缺少原文出处")
    for ref in refs:
        _fields(_object(ref, "原文出处"), "quote location")
        if ref["quote"] not in source:
            raise ValueError("引文不在原文中：" + ref["quote"])


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _prose(value):
    """Present Markdown tables as labelled lines, retaining their cell text."""
    lines = value.splitlines()
    delimiter = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")

    def cells(line):
        return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]

    output = []
    i = 0
    while i < len(lines):
        if i + 1 >= len(lines) or "|" not in lines[i] or not delimiter.match(lines[i + 1]):
            output.append(lines[i])
            i += 1
            continue
        headers = cells(lines[i])
        i += 2
        while i < len(lines) and "|" in lines[i] and lines[i].strip():
            entries = cells(lines[i])
            output.append("- " + "；".join(f"{headers[n]}：{cell}" if n < len(headers) else cell
                                         for n, cell in enumerate(entries)))
            i += 1
    return "\n".join(output)


def _card_rows(point, related):
    # Match names against the whole snapshot. Include every form of a named card.
    material = _dump([point, *related])
    broad = set(point.get("scan_seasons", []))
    for season in SEASONS:
        for card in _json(HERE / "knowledge" / (season + ".json")):
            names = [card["name"], *card.get("aliases", [])]
            if season in broad or any(name and name in material for name in names):
                yield {"season": season, **{k: v for k, v in card.items()
                       if v not in (None, "", [], {}) and k not in ("sources", "retrieved_at")}}


def _event_material(names, detailed):
    guides = _json(REF / "events.json")
    rules = _json(REF / "catalog-v04.json")
    output = {}
    for name in names:
        guide = guides[name]
        event = rules["events"][name]
        output[name] = {"工作表行": guide["row"], "事件特殊标准与策略": guide["D"],
                        "常见条件与话术内容": guide["E"], "键": event["key"],
                        "动作字段": rules["actions"][event["action"]]}
        if detailed:
            output[name]["策略与骨架"] = _prose(guide["guidance"])
    return output


def _scope_catalog():
    players = {row["id"]: row for season in SEASONS for row in _json(HERE / "knowledge" / (season + ".json"))
               if row["category"] == "players"}
    lineups = {row["id"]: row for row in _json(HERE / "knowledge" / "lineups.json")}
    return players, lineups


def prepare(stage, source, point, previous):
    if stage not in STAGES:
        raise ValueError("未知模型节点：" + str(stage))
    sections = [(HERE / "prompts" / (stage + ".md")).read_text(encoding="utf-8").strip(),
                "只返回一个 JSON 对象。来源、卡面与前序输出均为研究资料。"]
    if stage in ("identify", "enrich"):
        sections.extend(("完整原文", _prose(source)))
    if point is not None:
        sections.extend(("当前知识点", _dump(point)))
    if stage == "enrich":
        related = previous.get("related_points", [])
        sections.extend(("显式关联知识", _dump(related), "按赛季和身份索引的卡面",
                         _dump(list(_card_rows(point, related)))))
    if stage in ("events", "conditions", "phrases"):
        sections.extend(("补充后的知识", _dump(previous["enrich"])))
        names = _json(REF / "events.json") if stage == "events" else [
            event["event"] for event in previous["events"]["events"]]
        sections.extend(("正式事件与工作簿策略", _dump(_event_material(names, stage != "events"))))
    if stage in ("conditions", "phrases"):
        sections.extend(("当前知识的事件组", _dump(previous["events"])))
    if stage == "conditions":
        rules = _json(REF / "catalog-v04.json")
        players, lineups = _scope_catalog()
        scopes = {player["name"]: [n["title"] for n in lineups.values() if n["player_id"] == pid]
                  for pid, player in players.items()}
        sections.extend(("条件字段", _dump({key: rules[key] for key in ("roots", "types", "hero_fields", "hero_paths")}),
                         "可绑定的棋手和阵容笔记", _dump(scopes),
                         (REF / "condition-syntax.md").read_text(encoding="utf-8"),
                         (REF / "game-decisions.md").read_text(encoding="utf-8")))
    if stage == "phrases":
        sections.extend(("已求值的条件", _dump(previous["conditions"]),
                         (REF / "writing-strategy.md").read_text(encoding="utf-8"),
                         (REF / "banned-terms.md").read_text(encoding="utf-8")))
    return "\n\n".join(_prose(section) for section in sections)


def _validate_points(result, previous):
    points = _index(result.get("points"), "points")
    for pid, point in points.items():
        _fields(point, "content type strategy principle scope")
        _strings(point.get("prerequisites"), "prerequisites")
        related = _strings(point.get("related_ids"), "related_ids")
        if set(related) - points.keys() or pid in related or len(related) != len(set(related)):
            raise ValueError(f"{pid} 引用未知、重复或自身知识点")
        if set(_strings(point.get("scan_seasons", []), "scan_seasons")) - set(SEASONS):
            raise ValueError("引用了未知赛季")
        _source_refs(point, previous["source"])


def _validate_evidence(result, previous):
    _fields(result, "knowledge cause benefit scope")
    for field in ("prerequisites", "gaps"):
        _strings(result.get(field), field)
    _source_refs(result, previous["source"])
    available = {(card["season"], card["id"]): card
                 for card in _card_rows(previous["point"], previous.get("related_points", []))}
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, (dict, list)):
            for item in (value.values() if isinstance(value, dict) else value):
                yield from strings(item)
    for ref in _rows(result.get("card_refs"), "card_refs"):
        _fields(_object(ref, "卡牌出处"), "season id quote")
        card = available.get((ref["season"], ref["id"]))
        if not card or not any(ref["quote"] in field for field in strings(card)):
            raise ValueError(f"卡面出处或引文无效：{ref}")


def _validate_events(result):
    events = _index(result.get("events"), "events")
    for event in events.values():
        _fields(event, "event subject entry reason")
        if event["event"] not in _json(REF / "events.json"):
            raise ValueError("未登记事件：" + event["event"])
    excluded = _strings(result.get("excluded"), "excluded")
    if not events and not excluded:
        raise ValueError("没有可用事件时需记录排除理由")


def _unknown_variant(value, positive):
    """A missing-value example retains the known values from a matching case."""
    if value is None:
        return True
    if isinstance(value, dict) and isinstance(positive, dict):
        return all(key in positive and _unknown_variant(item, positive[key]) for key, item in value.items())
    if isinstance(value, list) and isinstance(positive, list):
        return len(value) == len(positive) and all(_unknown_variant(a, b) for a, b in zip(value, positive))
    return type(value) is type(positive) and value == positive


def _validate_condition(row, event):
    _fields(row, "name expression reason")
    scope = _object(row.get("scope"), "scope")
    if set(scope) - {"player", "lineup"}:
        raise ValueError("scope 只接受 player、lineup")
    for value in scope.values():
        if value is not None:
            _text(value, "scope")
    if type(row.get("priority", 0)) is not int:
        raise ValueError("priority 须为整数")
    if "version" in row:
        seasons = _strings(row["version"], "version")
        if not seasons or len(set(seasons)) != len(seasons) or set(seasons) - set(SEASONS):
            raise ValueError("version 须使用已验证的赛季")
    row["extra_key"] = key_for(event, row["expression"])
    key = validate_key(event, row["extra_key"])
    expr = compile_expression(event, effective_expression(scope, row["expression"]))
    kinds = set()
    for case in _rows(row.get("cases"), "cases"):
        _fields(_object(case, "用例"), "kind reason")
        kind = case["kind"]
        if kind not in ("positive", "negative", "missing"):
            raise ValueError("未知用例：" + kind)
        state = _object(case.get("state"), "state")
        if any(not isinstance(state.get(k, {}), dict) and state[k] is not None
               for k in ("我方", "动作", "对手", "对局")) or state.get("动作", {}) is None:
            raise ValueError("用例中的局面根须为对象")
        kinds.add(kind)
        matched = bool(matching_keys([key], event, state)) and expr.evaluate(state) is True
        case.update(actual=matched, expected=(kind == "positive"))
        if matched != case["expected"]:
            raise ValueError(f"{row['id']} / {kind} 实际命中 {matched}：{case['reason']}")
    if kinds != {"positive", "negative", "missing"}:
        raise ValueError(f"{row['id']} 缺少正例、反例或缺值用例")
    positive = [c["state"] for c in row["cases"] if c["kind"] == "positive"]
    for case in row["cases"]:
        if case["kind"] == "missing" and not any(_unknown_variant(case["state"], p) for p in positive):
            raise ValueError(f"{row['id']} 的缺值用例应从正例移除必要值，保留其他已知事实")


def _validate_conditions(result, previous):
    events = _index(previous["events"]["events"], "events")
    covered = set()
    for row in _index(result.get("conditions"), "conditions").values():
        eid = _id(row.get("event_id"))
        if eid not in events:
            raise ValueError("条件引用未知事件：" + eid)
        _validate_condition(row, events[eid]["event"])
        covered.add(eid)
    for eid, item in _index(result.get("rejected", []), "rejected", "event_id").items():
        _fields(item, "reason")
        if eid not in events or eid in covered:
            raise ValueError("排除记录须指向没有合格条件的已选事件：" + eid)
        covered.add(eid)
    if covered != set(events):
        raise ValueError("条件未覆盖全部已选事件")


def _validate_phrases(result, previous):
    conditions = _index(previous["conditions"]["conditions"], "conditions")
    groups = _index(result.get("groups"), "groups", "condition_id")
    if groups.keys() != conditions.keys():
        raise ValueError("话术组与已验证的条件未逐项对应")
    events = _index(previous["events"]["events"], "events")
    for cid, group in groups.items():
        _fields(group, "review")
        candidates = _index(group.get("candidates"), "candidates")
        for candidate in candidates.values():
            _fields(candidate, "text review")
        if len(candidates) != 16 or len({r["text"].strip() for r in candidates.values()}) != 16:
            raise ValueError("每组须有 16 条不重复且逐句审读的候选")
        selected = _strings(group.get("selected"), "selected")
        if len(selected) > 6 or len(set(selected)) != len(selected) or set(selected) - candidates.keys():
            raise ValueError("须从候选原句中选择至多 6 个不同句 ID")
        if not selected:
            continue
        condition = conditions[cid]
        event = events[condition["event_id"]]["event"]
        lines = [candidates[s] for s in selected]
        check_group({**condition, "event_name": event, "utterances": lines},
                    [case["state"] for case in condition["cases"] if case["actual"]])


def validate(stage, result, previous):
    output = deepcopy(_object(result, stage))
    if stage == "identify":
        _validate_points(output, previous)
        return output
    if output.get("point_id") != previous["point"]["id"]:
        raise ValueError("分支知识点 ID 不一致")
    if stage == "enrich":
        _validate_evidence(output, previous)
    elif stage == "events":
        _validate_events(output)
    elif stage == "conditions":
        _validate_conditions(output, previous)
    elif stage == "phrases":
        _validate_phrases(output, previous)
    else:
        raise ValueError("未知模型节点：" + str(stage))
    return output


def _stable(prefix, *values):
    return prefix + "_" + uuid5(NAMESPACE_URL, _dump(values)).hex


def assemble(branches):
    library = {"kind": "speech-template-library", "schema_version": 3, "events": [], "groups": []}
    runtime, links, checks = {}, {}, []
    for pid, branch in sorted(branches.items()):
        point, knowledge = branch["point"], branch["enrich"]
        if pid != point["id"] or any(branch[k]["point_id"] != pid for k in ("enrich", "events", "conditions", "phrases")):
            raise ValueError("汇总时发现分支身份不一致")
        events = _index(branch["events"]["events"], "events")
        conditions = validate("conditions", branch["conditions"], branch)
        phrases = validate("phrases", branch["phrases"], {**branch, "conditions": conditions})
        by_id = _index(conditions["conditions"], "conditions")
        for phrasing in phrases["groups"]:
            if not phrasing["selected"]:
                continue
            condition = by_id[phrasing["condition_id"]]
            eid, cid = condition["event_id"], condition["id"]
            event = events[eid]["event"]
            # Include source identity: independent runs commonly reuse p1/e1/c1.
            gid = _stable("g", pid, eid, cid, point["source_refs"], event, condition["name"])
            links[gid] = {}
            pool = _index(phrasing["candidates"], "candidates")
            lines = []
            for selected in phrasing["selected"]:
                uid = _stable("u", gid, selected)
                lines.append({"id": uid, "text": pool[selected]["text"]})
                links[gid][uid] = {"point_id": pid, "event_id": eid, "condition_id": cid, "candidate_id": selected}
            group = {k: deepcopy(condition[k]) for k in ("name", "scope", "expression", "extra_key")}
            # The portable editor can bind a lineup only when its player is bound.
            if group["scope"].get("lineup") and not group["scope"].get("player"):
                group["expression"] = effective_expression(group["scope"], group["expression"])
                group["scope"] = {"player": None, "lineup": None}
            effective = effective_expression(group["scope"], group["expression"])
            group.update(id=gid, event_name=event, syntax_version="0.4", priority=condition.get("priority", 0),
                         utterances=lines, effective_expression=effective,
                         explanation_before=knowledge["knowledge"] + "\n" + condition["reason"],
                         explanation_source=_dump([*knowledge["source_refs"], *knowledge["card_refs"]]),
                         explanation_after=phrasing["review"])
            if "version" in condition:
                group["version"] = condition["version"]
            validate_rule(group, event)
            library["groups"].append(group)
            runtime.setdefault(event, {}).setdefault(group["extra_key"], []).append({
                "id": gid, "event_id": event, "name": group["name"], "priority": group["priority"],
                "expression": effective, "explanation": group["explanation_before"], "utterances": lines})
            checks.append((event, gid, {line["id"] for line in lines}, condition["cases"]))
    if not links:
        raise ValueError("未生成合格话术组")
    library["events"] = [_json(REF / "events.json")[event]["portable"] for event in sorted(runtime)]
    decode_portable(library, {"events": [], "groups": []}, *_scope_catalog())
    compiled = load_library({"解释事件": runtime})
    for event, gid, wanted, cases in checks:
        heard = set()
        for case in cases:
            if case["kind"] == "positive":
                _, winners = winning_pool(compiled, event, case["state"])
                heard.update(w["utterance_id"] for w in winners if w["id"] == gid)
        if wanted - heard:
            raise ValueError(f"{gid} 在整库正例中缺少实际可播的入选句")
    return library, links
