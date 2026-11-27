"""Prompt material, branch contracts and portable v0.5 assembly."""
import ast
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
from uuid import NAMESPACE_URL, uuid5

from frontend.template_v04 import effective_expression, validate_rule
from src.python.condition.v04 import (
    catalog, compile_expression, key_paths, lineup_name, load_library, matching_keys,
    validate_key, validate_key_expression, winning_pool,
)
from .editorial import check_group
from . import event_examples
from .scenario_discovery import validate_coverage

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


def _source_refs(result, source, field="source_refs", *, required=True):
    refs = _rows(result.get(field), field)
    if not refs and required:
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
    # Match names across the snapshots and give equipment points all comparison items.
    material = _dump([point, *related])
    broad = set(point.get("scan_seasons", []))
    compare_equipment = point.get("type") == "装备"
    for season in SEASONS:
        for card in _json(HERE / "knowledge" / (season + ".json")):
            names = [card["name"], *card.get("aliases", [])]
            if (season in broad or (compare_equipment and card["category"] == "equipment")
                    or any(name and name in material for name in names)):
                yield {"season": season, **{k: v for k, v in card.items()
                       if v not in (None, "", [], {}) and k not in ("sources", "retrieved_at")}}


def _event_material(names, detailed):
    guides = _json(REF / "events.json")
    rules = catalog()
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
    if stage == "identify":
        sections.extend(("正式知识类型", _dump({name: row["question"]
                         for name, row in _json(REF / "knowledge-types.json").items()})))
        if "segments" in previous:
            sections.extend((
                "逐段查找独立决策，不以原文的推荐清单为边界。沿实体之间的关系检查提供者、受益者、兑现时点，"
                "从取得、使用、保留资源等入口找会改变理由的局势。允许用卡面和规则补证。"
                "在每个知识点的 evidence_kind 标记 note（原文明示）或 inference（结合规则和局面推导）。"
                "为每个段落输出 coverage 记录，形状为 {segment_id, point_ids, reason}。point_ids 为空时写具体原因。"
                "每个知识点须由至少一个段落的逐字引文支持；同段支持多项收益时逐项保留。",
                _dump(previous["segments"])))
    if stage == "enrich":
        type_name = _knowledge_type(point)
        rule = _json(REF / "knowledge-types.json")[type_name]
        sections.extend(("当前类型的补充边界", _dump({"类型": type_name, **{
            key: rule[key] for key in ("question", "include", "stop")}})))
        related = previous.get("related_points", [])
        _, lineups = _scope_catalog()
        material = _dump([point, *related])
        matching_lineups = [row for row in lineups.values() if row["title"] in material]
        types = catalog()["types"]
        decision_fields = {
            "玩家": {name: types["玩家"][name] for name in (
                "等级", "血量", "容错数", "剩余能量", "升到下一级所需经验", "当前人口", "人口上限",
                "排名", "是否存活", "主C", "最高等级英雄")},
            "对局": types["对局"],
            "卡牌": {name: types["卡牌"][name] for name in ("名称", "品阶", "等级")},
        }
        sections.extend(("显式关联知识", _dump(related), "按赛季和身份索引的卡面",
                         _dump(list(_card_rows(point, related))), "已登记的相关阵容", _dump(matching_lineups),
                         "实战判断所需字段（我方和对手均使用玩家字段）", _dump(decision_fields),
                         "知识库中的游戏决策依据",
                         (REF / "game-decisions.md").read_text(encoding="utf-8")))
    if stage in ("events", "conditions", "phrases"):
        sections.extend(("补充后的知识", _dump(previous["enrich"])))
        names = _json(REF / "events.json") if stage == "events" else [
            event["event"] for event in previous["events"]["events"]]
        if stage == "events":
            type_name = _knowledge_type(point)
            rows = set(_json(REF / "knowledge-types.json")[type_name]["workbook_rows"])
            examples = [name for name, data in names.items() if data["row"] in rows]
            sections.extend(("当前知识类型常见事件（按实际收益匹配）", _dump(examples)))
            if previous.get("scenario_discovery"):
                sections.append("从当前收益追查会使它兑现的动作。检查组件取得、上阵、使用、保留及必要的同类入口。"
                                "共享的理由要覆盖实际能发生的对应事件，分别核查动作字段和事实。"
                                "excluded 明确写出检查过的入口及排除原因。")
        sections.extend(("正式事件与工作簿策略", _dump(_event_material(names, stage != "events"))))
    if stage in ("conditions", "phrases"):
        sections.extend(("当前知识的事件组", _dump(previous["events"])))
    if stage == "conditions":
        rules = catalog()
        players, lineups = _scope_catalog()
        scopes = {player["name"]: [n["title"] for n in lineups.values() if n["player_id"] == pid]
                  for pid, player in players.items()}
        sections.extend(("条件字段", _dump({key: rules[key] for key in ("roots", "types", "hero_fields", "hero_paths")}),
                         "可绑定的棋手和阵容笔记", _dump(scopes),
                         (REF / "condition-syntax.md").read_text(encoding="utf-8"),
                         (REF / "game-decisions.md").read_text(encoding="utf-8")))
        base_groups = [group for group in previous.get("base_groups", {}).values() if group["event_name"] in names]
        if base_groups:
            sections.extend(("可引用的已有基础组", _dump(base_groups),
                             "已有足够基础解释时，在 refinement 条件填 base_group_id。复用相同事件和键，"
                             "提高优先级，并为同一动作分别在必要事实不成立和缺失的用例写 fallback: true。"
                             "条件满足时应播细分组，fallback 用例应播该基础组。"))
    if stage == "phrases":
        sections.extend(("已求值的条件", _dump(previous["conditions"]),
                         (REF / "writing-strategy.md").read_text(encoding="utf-8"),
                         (REF / "banned-terms.md").read_text(encoding="utf-8")))
        active = {row["event_id"] for row in previous["conditions"]["conditions"]}
        examples = event_examples.load()
        matched = {row["event"]: examples[row["event"]] for row in previous["events"]["events"]
                   if row["id"] in active and examples.get(row["event"])}
        if matched:
            sections.extend(("按正式事件分组的人工话术样例。只借鉴表达方式和条件与话术的对应关系。"
                             "示例中的对象、预算和局势不能充当本次组的证据。",
                             json.dumps(matched, ensure_ascii=False, indent=2)))
    return "\n\n".join(_prose(section) for section in sections)


def _knowledge_type(point):
    type_name = _text(point.get("type"), "知识类型")
    if type_name not in _json(REF / "knowledge-types.json"):
        raise ValueError("未登记知识类型：" + type_name)
    return type_name


def _validate_points(result, previous):
    points = _index(result.get("points"), "points")
    for pid, point in points.items():
        _fields(point, "content type strategy principle scope prerequisite")
        _knowledge_type(point)
        if point.get("evidence_kind", "note") not in ("note", "inference"):
            raise ValueError(f"{pid} 的 evidence_kind 只接受 note 或 inference")
        related = _strings(point.get("related_ids"), "related_ids")
        if set(related) - points.keys() or pid in related or len(related) != len(set(related)):
            raise ValueError(f"{pid} 引用未知、重复或自身知识点")
        if set(_strings(point.get("scan_seasons", []), "scan_seasons")) - set(SEASONS):
            raise ValueError("引用了未知赛季")
        _source_refs(point, previous["source"])
        _source_refs(point, previous["source"], "related_refs", required=False)
    if "segments" in previous:
        validate_coverage(result.get("coverage"), previous["segments"], points)


def _validate_evidence(result, previous):
    type_name = _knowledge_type(previous["point"])
    if "type" in result and result["type"] != type_name:
        raise ValueError("补充知识不能修改识别阶段的知识类型：" + type_name)
    result["type"] = type_name
    _fields(result, "knowledge cause benefit scope")
    for field in ("prerequisites", "gaps"):
        _strings(result.get(field), field)
    _source_refs(result, previous["source"])
    available = {}
    for card in _card_rows(previous["point"], previous.get("related_points", [])):
        season = card["season"]
        available.setdefault((season, card["id"]), []).append(card)
        for group in card.get("player_skill_groups", []):
            for skill in group.get("cards", []):
                if skill.get("id"):
                    available.setdefault((season, skill["id"]), []).append(skill)
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, (dict, list)):
            for item in (value.values() if isinstance(value, dict) else value):
                yield from strings(item)
    for ref in _rows(result.get("card_refs"), "card_refs"):
        _fields(_object(ref, "卡牌出处"), "season id quote")
        cards = available.get((ref["season"], ref["id"]), [])
        if not any(ref["quote"] in field for card in cards for field in strings(card)):
            raise ValueError(f"卡面出处或引文无效：{ref}")


def _validate_events(result):
    events = _index(result.get("events"), "events")
    for event in events.values():
        _fields(event, "event subject entry reason expected")
        if event["event"] not in _json(REF / "events.json"):
            raise ValueError("未登记事件：" + event["event"])
        if "base" not in event:
            raise ValueError("事件须说明是否存在独立的基础收益：" + event["id"])
        if event["base"] is not None:
            base = _object(event["base"], "基础收益")
            _fields(base, "expected")
            fields = _strings(base.get("fields"), "基础条件字段")
            if not fields or len(set(fields)) != len(fields):
                raise ValueError("基础条件字段须非空且互不重复")
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


def _validate_direction(row):
    _fields(row, "limited not_limited expected wording")


def _validate_condition(row, event, base_fields=None):
    _fields(row, "name reason")
    for field in ("extra_key", "expression"):
        if not isinstance(row.get(field), str):
            raise ValueError(field + " 须为字符串，可使用空串")
    _validate_direction(row)
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
    key = validate_key(event, row["extra_key"])
    validate_key_expression(event, row["extra_key"], row["expression"])
    expr = compile_expression(event, effective_expression(scope, row["expression"]))
    if base_fields is not None:
        fields = {ast.unparse(node) for node in ast.walk(expr.node) if isinstance(node, ast.Attribute)} if expr.node else set()
        leaves = {field.removeprefix("_item") for field in fields
                  if not any(other.startswith(field + ".") for other in fields)}
        leaves.update(".".join(path) for path, value in zip(key_paths(event), key) if value != "*")
        if leaves != set(base_fields):
            raise ConditionCoverageError(f"{row['id']} 缺少或超出基础条件所需字段：{sorted(leaves ^ set(base_fields))}")
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


class ConditionCoverageError(ValueError):
    pass


def _validate_conditions(result, previous):
    events = _index(previous["events"]["events"], "events")
    covered = set()
    bases, refinements = {}, {}
    for row in _index(result.get("conditions"), "conditions").values():
        eid = _id(row.get("event_id"))
        if eid not in events:
            raise ValueError("条件引用未知事件：" + eid)
        event = events[eid]
        base = event.get("base")
        layer = row.get("layer")
        if base and layer not in ("base", "refinement"):
            raise ConditionCoverageError("条件须标明基础组或细分组：" + row["id"])
        _validate_condition(row, event["event"], base["fields"] if base and layer == "base" else None)
        if "base_group_id" in row:
            gid = _id(row["base_group_id"])
            existing = previous.get("base_groups", {}).get(gid)
            if (layer != "refinement" or not existing or existing["event_name"] != event["event"]
                    or existing["extra_key"] != row["extra_key"] or existing.get("ignored")
                    or existing.get("publication_hold") or row.get("priority", 0) <= existing.get("priority", 0)):
                raise ConditionCoverageError(f"{row['id']} 的已有基础组、额外信息键或优先级无效：{gid}")
            fallback = [case for case in row["cases"] if case.get("fallback") is True]
            if {case["kind"] for case in fallback} != {"negative", "missing"}:
                raise ConditionCoverageError(f"{row['id']} 缺少回退所需的反例和缺值用例")
            key = validate_key(event["event"], existing["extra_key"])
            expression = compile_expression(event["event"], effective_expression(existing.get("scope", {}), existing["expression"]))
            for case in [*fallback, *(case for case in row["cases"] if case["kind"] == "positive")]:
                state = case["state"]
                if not matching_keys([key], event["event"], state) or expression.evaluate(state) is not True:
                    raise ConditionCoverageError(f"{row['id']} 的已有基础组未覆盖该细分场景：{case['reason']}")
            bases.setdefault(eid, []).append((key, existing.get("priority", 0)))
        if base:
            key = validate_key(event["event"], row["extra_key"])
            (bases if layer == "base" else refinements).setdefault(eid, []).append((key, row.get("priority", 0)))
        covered.add(eid)
    for eid, item in _index(result.get("rejected", []), "rejected", "event_id").items():
        _fields(item, "reason")
        if eid not in events or eid in covered:
            raise ValueError("排除记录须指向没有合格条件的已选事件：" + eid)
        if "base" in events[eid]:
            if re.search(r"(?:无法|不能|没有|无权|不可).{0,28}(?:求值器|求值程序|运行条件|读取.{0,8}目录|访问.{0,8}目录)", item["reason"]):
                raise ConditionCoverageError("提交表达式和用例由本地求值，不能以模型工具权限排除：" + eid)
            if item.get("blocker") not in ("missing_field", "insufficient_evidence", "duplicate_coverage"):
                raise ConditionCoverageError("排除项须给出可核对的阻碍类型：" + eid)
            if not isinstance(item.get("reference"), str) or not item["reference"].strip():
                raise ConditionCoverageError("排除项须指出所缺字段、证据或覆盖组：" + eid)
        covered.add(eid)
    for eid, event in events.items():
        if not event.get("base"):
            continue
        if not bases.get(eid):
            raise ConditionCoverageError("具备可表达的基础收益但缺少基础组：" + eid)
        for specific_key, specific_priority in refinements.get(eid, ()):
            for base_key, base_priority in bases[eid]:
                same_tier = base_key.count("*") == specific_key.count("*")
                overlap = all(a == b or "*" in (a, b) for a, b in zip(base_key, specific_key))
                if same_tier and overlap and specific_priority <= base_priority:
                    raise ConditionCoverageError("同级匹配时，细分组优先级须高于基础组：" + eid)
    if covered != set(events):
        raise ConditionCoverageError("条件未覆盖全部已选事件")


class InsufficientPhrases(ValueError):
    pass


def _validate_phrases(result, previous, *, after_retry=False, candidate_count=16):
    conditions = _index(previous["conditions"]["conditions"], "conditions")
    groups = _index(result.get("groups"), "groups", "condition_id")
    if groups.keys() != conditions.keys():
        raise ValueError("话术组与已验证的条件未逐项对应")
    events = _index(previous["events"]["events"], "events")
    incomplete = []
    for cid, group in groups.items():
        _fields(group, "review")
        _validate_direction(_object(group.get("writing"), "生成话术的思考"))
        candidates = _index(group.get("candidates"), "candidates")
        for candidate in candidates.values():
            _fields(candidate, "text review")
        if len(candidates) != candidate_count or len({r["text"].strip() for r in candidates.values()}) != candidate_count:
            raise ValueError(f"每组须有 {candidate_count} 条不重复且逐句审读的候选")
        selected = _strings(group.get("selected"), "selected")
        if len(selected) > 6 or len(set(selected)) != len(selected) or set(selected) - candidates.keys():
            raise ValueError("须从候选原句中选择 6 个不同句 ID")
        if len(selected) < 6:
            incomplete.append(cid)
            if after_retry:
                if conditions[cid].get("layer") == "base":
                    raise ValueError("重试后基础组仍不足 6 条合格话术：" + cid)
                group["review"] = f"重试后只筛出 {len(selected)} 条合格话术。{group['review']}"
                group["selected"] = []
            continue
        condition = conditions[cid]
        event = events[condition["event_id"]]["event"]
        lines = [candidates[s] for s in selected]
        check_group({**condition, "event_name": event, "utterances": lines},
                    [case["state"] for case in condition["cases"] if case["actual"]])
    if incomplete and not after_retry:
        raise InsufficientPhrases("以下条件不足 6 条合格话术，请重写候选后复筛：" + "、".join(incomplete))


def validate(stage, result, previous, *, after_retry=False):
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
        _validate_phrases(output, previous, after_retry=after_retry, candidate_count=6 if previous.get("local_replies") else 16)
    else:
        raise ValueError("未知模型节点：" + str(stage))
    return output


def _stable(prefix, *values):
    return prefix + "_" + uuid5(NAMESPACE_URL, _dump(values)).hex


def _portable_scope(scope, players, lineups):
    scope = deepcopy(scope)
    title, player = scope.get("lineup"), scope.get("player")
    if title and player:
        titles = {row["title"] for row in lineups.values()
                  if players.get(row["player_id"], {}).get("name") == player}
        if title not in titles:
            matches = {name for name in titles if lineup_name(name) == lineup_name(title)}
            if len(matches) == 1:
                scope["lineup"] = matches.pop()
    return scope


def assemble(branches, *, defer_playability=False):
    library = {"kind": "speech-template-library", "schema_version": 3, "events": [], "groups": []}
    runtime, links, checks = {}, {}, []
    players, lineups = _scope_catalog()
    for pid, branch in sorted(branches.items()):
        point, knowledge = branch["point"], branch["enrich"]
        if pid != point["id"] or any(branch[k]["point_id"] != pid for k in ("enrich", "events", "conditions", "phrases")):
            raise ValueError("汇总时发现分支身份不一致")
        events = _index(branch["events"]["events"], "events")
        conditions = validate("conditions", branch["conditions"], branch)
        phrases = validate("phrases", branch["phrases"], {**branch, "conditions": conditions}, after_retry=True)
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
            group = {k: condition[k] for k in ("name", "expression", "extra_key")}
            group["scope"] = _portable_scope(condition["scope"], players, lineups)
            # The portable editor can bind a lineup only when its player is bound.
            if group["scope"].get("lineup") and not group["scope"].get("player"):
                group["expression"] = effective_expression(group["scope"], group["expression"])
                group["scope"] = {"player": None, "lineup": None}
            effective = effective_expression(group["scope"], group["expression"])
            group.update(id=gid, event_name=event, syntax_version="0.5", priority=condition.get("priority", 0),
                         utterances=lines, effective_expression=effective,
                         instruction=condition["expected"] + "。" + condition["wording"],
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
    if not links and not defer_playability:
        raise ValueError("未生成合格话术组")
    library["events"] = [_json(REF / "events.json")[event]["portable"] for event in sorted(runtime)]
    if defer_playability:
        return library, links, {gid: cases for _, gid, _, cases in checks}
    decode_portable(library, {"events": [], "groups": []}, players, lineups)
    compiled = load_library({"解释事件": runtime}, strict=True)
    for event, gid, wanted, cases in checks:
        heard = set()
        for case in cases:
            if case["kind"] == "positive":
                _, winners = winning_pool(compiled, event, case["state"])
                heard.update(w["utterance_id"] for w in winners if w["id"] == gid)
        if wanted - heard:
            raise ValueError(f"{gid} 在整库正例中缺少实际可播的入选句")
    return library, links
