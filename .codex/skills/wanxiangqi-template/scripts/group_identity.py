"""Stable identities for generated groups with event keys."""

import ast
from copy import deepcopy
import json
from uuid import NAMESPACE_URL, uuid5

from frontend.template_v04 import effective_expression
from src.python.condition.v04 import catalog, compile_expression, validate_key


KEYED_SYNTAX_VERSIONS = {"0.4", "0.5"}


def name_template_group(group):
    """Render the registered action with its fixed event parameters."""
    event = group["event_name"]
    if group.get("syntax_version") not in KEYED_SYNTAX_VERSIONS:
        return group["name"]
    definition = catalog()["events"][event]
    arguments = dict(zip(definition["key"], validate_key(event, group["extra_key"]), strict=True))

    def argument(field, label):
        value = arguments.get(field, "*")
        return label if value == "*" else value

    action = event.removeprefix("解释为何")
    main, separator, round_name = action.partition("（")
    if main.startswith("竞拍目标"):
        action = "竞拍" + argument("选中", main.removeprefix("竞拍目标")) + separator + round_name
    elif main.startswith(("购买", "选择")):
        action = main[:2] + argument("选中", main[2:])
    elif main in {"上阵英雄", "合成英雄", "从手牌出售英雄", "从战场出售英雄"}:
        action = main.removesuffix("英雄") + argument("英雄", "英雄")
    elif main in {"使用无目标效果牌", "使用关键效果牌", "使用棋手技能"}:
        action = "使用" + argument("卡牌", main[2:])
    elif main in {"对目标使用效果牌", "对目标使用棋手技能"}:
        action = "对目标使用" + argument("卡牌", main.removeprefix("对目标使用"))
    elif main == "建议向某阵容发展":
        action = "建议向" + argument("阵容", "建议发展的阵容") + "发展"
    elif main == "棋手升级":
        action = "棋手升到" + argument("目标等级", "目标等级") + "级"
    elif main == "穿戴装备":
        action = f"给{argument('目标英雄', '英雄')}穿戴{argument('装备', '装备')}"
    elif main == "铸造装备":
        action = f"将{argument('目标英雄', '英雄')}的{argument('原装备', '旧装备')}铸造成{argument('目标装备', '新装备')}"
    elif main == "转移装备":
        action = f"将{argument('原英雄', '原持有英雄')}的{argument('装备', '装备')}转移给{argument('目标英雄', '接收英雄')}"
    elif main in {"移动主C和主T", "移动前后排"}:
        action = "移动" + argument("英雄", main.removeprefix("移动"))
    return "解释为何" + action if event.startswith("解释为何") else event


def audit_key(event, name, group_id=None):
    return (event, group_id or name)


def _condition_key(node):
    if isinstance(node, ast.BoolOp):
        children = set()
        for child in node.values:
            part = _condition_key(child)
            children.update(part[1] if part[0] == type(node.op).__name__ else [part])
        return type(node.op).__name__, frozenset(children)
    if isinstance(node, ast.Call):
        return "Call", node.func.id, tuple(_condition_key(child) for child in node.args)
    if isinstance(node, ast.UnaryOp):
        return type(node.op).__name__, _condition_key(node.operand)
    if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In) and isinstance(node.comparators[0], ast.List):
        items = frozenset(ast.dump(item) for item in node.comparators[0].elts)
        if len(items) == 1:
            return "Eq", frozenset((ast.dump(node.left), *items))
        return "In", ast.dump(node.left), items
    if isinstance(node, ast.Compare) and isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return type(node.ops[0]).__name__, frozenset((ast.dump(node.left), ast.dump(node.comparators[0])))
    return "Expr", ast.dump(node)


def template_group_trigger(group):
    event = group["event_name"]
    key = validate_key(event, group["extra_key"])
    definition = catalog()["events"][event]
    fields = catalog()["actions"][definition["action"]]
    expression = effective_expression(group.get("scope", {}), group["expression"])
    parts = _condition_key(compile_expression(event, expression).node) if expression else None
    conjunction = set(parts[1] if parts and parts[0] == "And" else [parts]) - {None}
    for field, value in zip(definition["key"], key, strict=True):
        if value == "*":
            continue
        path = "动作." + field + (".名称" if fields[field] == "卡牌" else "")
        # Extra-key matching already proves this conjunct before evaluation.
        literal = int(value) if fields[field] == "int" else value
        comparison = ast.Compare(left=ast.parse(path, mode="eval").body, ops=[ast.Eq()],
                                 comparators=[ast.Constant(literal)])
        conjunction.discard(_condition_key(comparison))
    return event, tuple(key), frozenset(conjunction)


def has_awakening_guard(expression):
    """Require both facts in every branch of a merge-awakening template."""
    event = "解释为何合成英雄"
    guard = compile_expression(event, "动作.英雄.已觉醒 and 动作.英雄.觉醒进度 == 2").node
    required = [_condition_key(node) for node in guard.values]

    def proves(node, fact):
        if isinstance(node, ast.BoolOp):
            combine = all if isinstance(node.op, ast.Or) else any
            return combine(proves(child, fact) for child in node.values)
        return _condition_key(node) == fact

    condition = compile_expression(event, expression).node
    return condition is not None and all(proves(condition, fact) for fact in required)


def _human_edited(group):
    return (group.get("last_modified_by") or {}).get("kind") == "user"


def _combine_groups(first, other):
    source = other if _human_edited(other) and not _human_edited(first) else first
    result = {**source, "id": first["id"], "priority": max(first.get("priority", 0), other.get("priority", 0))}
    active = [group for group in (first, other) if not group.get("ignored")]
    if active:
        result.pop("ignored", None)

    rows, comments, row_ids = {}, {}, set()
    for group in (first, other):
        row_id_map = {}
        for row in group["utterances"]:
            candidate = dict(row)
            if group.get("ignored") and active:
                candidate["ignored"] = True
            text = row["text"]
            if text not in rows:
                if candidate["id"] in row_ids:
                    identity = json.dumps([first["id"], group["id"], row["id"], text], ensure_ascii=False)
                    candidate["id"] = "utterance_" + uuid5(NAMESPACE_URL, identity).hex
                rows[text] = candidate
                row_ids.add(candidate["id"])
            kept = rows[text]
            if row.get("fixed"):
                kept["fixed"] = True
            if not candidate.get("ignored"):
                kept.pop("ignored", None)
            row_id_map[row["id"]] = kept["id"]
        for comment in group.get("file_comments", []):
            stored = {**comment}
            if comment.get("utterance_id") in row_id_map:
                stored["utterance_id"] = row_id_map[comment["utterance_id"]]
            comments.setdefault(comment["id"], stored)
    result["utterances"] = list(rows.values())
    if comments:
        result["file_comments"] = list(comments.values())

    sources = list(dict.fromkeys(group["explanation_source"] for group in (first, other)
                                 if group.get("explanation_source")))
    if sources:
        result["explanation_source"] = "\n".join(sources)
    before = {row["text"] for row in first["utterances"] if not row.get("ignored") and not first.get("ignored")}
    after = {row["text"] for row in result["utterances"] if not row.get("ignored") and not result.get("ignored")}
    if before != after or source is not first or result["priority"] != first.get("priority", 0):
        result["review_status"] = None
        result.pop("reviewed_by", None)
        result.pop("reviewed_at", None)
    return result


def merge_duplicate_groups(groups):
    """Keep the first ID for every duplicate effective keyed trigger."""
    from templates_schema import group_modes, group_versions

    merged = []
    indices = {}
    for group in groups:
        if group.get("syntax_version") not in KEYED_SYNTAX_VERSIONS:
            merged.append(deepcopy(group))
            continue
        key = (template_group_trigger(group), group_versions(group), group_modes(group))
        index = indices.setdefault(key, len(merged))
        if index == len(merged):
            merged.append(deepcopy(group))
        else:
            merged[index] = _combine_groups(merged[index], group)
    return merged
