"""Authoring projections for the keyed runtime format."""

import ast
from collections import defaultdict
from copy import deepcopy

from src.python.condition import ConditionError
from src.python.condition.v04 import catalog, compile_expression, compile_template, lineup_name, load_library, validate_key
from src.python.condition.v04_legacy import Translation, literal


VERSION = "0.4"
CURRENT_VERSION = "0.5"
KEYED_SYNTAX_VERSIONS = (VERSION, CURRENT_VERSION)


def key_for(event, expression):
    """Use a literal segment only when every successful branch requires it."""
    paths = catalog()["events"][event]["key"]
    required = compile_expression(event, expression).node

    def allowed(node, path):
        if isinstance(node, ast.BoolOp):
            values = [allowed(child, path) for child in node.values]
            if isinstance(node.op, ast.And):
                known = [value for value in values if value is not None]
                return set.intersection(*known) if known else None
            return set.union(*values) if all(value is not None for value in values) else None
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or ast.unparse(node.left) != path:
            return None
        op, expected = node.ops[0], node.comparators[0]
        if isinstance(op, ast.Eq) and isinstance(expected, ast.Constant):
            return {expected.value}
        if isinstance(op, ast.In) and isinstance(expected, ast.List):
            return {item.value for item in expected.elts}
        return None

    fields = catalog()["actions"][catalog()["events"][event]["action"]]
    segments = []
    for field in paths:
        path = "动作." + field + (".名称" if fields[field] == "卡牌" else "")
        values = allowed(required, path)
        if values and len(values) == 1:
            value = str(next(iter(values)))
            if value and value == value.strip() and not any(c in value for c in "-*"):
                segments.append(value)
                continue
        segments.append("*")
    return "-".join(segments)


def effective_expression(scope, expression):
    clauses = []
    if scope.get("player"):
        clauses.append("我方.棋手名称 == " + literal(scope["player"]))
    if scope.get("lineup"):
        clauses.append("我方.阵容名称 == " + literal(lineup_name(scope["lineup"])))
    if expression.strip():
        clauses.append("(" + expression + ")" if clauses else expression)
    return " and ".join(clauses)


def validate_rule(group, event):
    version = group.get("syntax_version")
    if version not in KEYED_SYNTAX_VERSIONS:
        raise ConditionError("不支持此模板语法版本")
    key, expression = group.get("extra_key"), group.get("expression")
    if version == CURRENT_VERSION:
        from src.python.condition.v04 import validate_key_expression
        validate_key_expression(event, key, expression)
    else:
        validate_key(event, key)
        compile_expression(event, expression)
    if group.get("editor_mode", "text") != "text" or group.get("condition_tree") or group.get("conditions"):
        raise ConditionError("使用额外信息键的模板须填写文本条件")
    for row in group["utterances"]:
        compile_template(event, row["text"])


def translate(group, event, legacy_catalog=None):
    converter = Translation(event, legacy_catalog)
    result = deepcopy(group)
    if "expression" not in group and group.get("conditions"):
        raise ConditionError("旧版选择器必须先转换为文本条件：" + group["name"])
    try:
        expression = converter.expression(group.get("expression", ""))
    except ConditionError as exc:
        if str(exc) != "待核实等价的官方伤害类型标签":
            raise
        result["publication_hold"] = str(exc)
        return result
    result.update(expression=expression, extra_key=key_for(converter.event, expression),
                  syntax_version=VERSION, editor_mode="text", conditions=[])
    result.pop("condition_tree", None)
    result.pop("publication_hold", None)
    for row in result["utterances"]:
        row["text"] = converter.template(row["text"])
    return result


def upgrade_rule(group, event):
    """Upgrade a keyed rule without changing its authoring identity or metadata."""
    if group.get("syntax_version") != VERSION:
        return group.copy()
    from src.python.condition.v04 import strip_key_redundancy
    expression = strip_key_redundancy(event, group["extra_key"], group["expression"])
    return {**group, "syntax_version": CURRENT_VERSION, "expression": expression}


def runtime_tree(public, entities, notes, meta):
    import template_rules
    events = {event["id"]: event for event in public["events"]}
    result = defaultdict(lambda: defaultdict(list))
    for group in public["groups"]:
        if group.get("publication_hold"):
            continue
        definition = events[group["event_id"]]
        event = definition["name"]
        if group.get("syntax_version") not in KEYED_SYNTAX_VERSIONS:
            if event not in catalog()["events"]:
                continue
            group = translate({**group, **template_rules.editor_rule(group, definition, entities)}, event,
                              template_rules.library_catalog(events.values()))
            if group.get("publication_hold"):
                continue
        group = upgrade_rule(group, event)
        gid = group["id"]
        scope = group["scope"]
        player = scope["player_id"]
        records = (entities, meta.get("entity_archive", {}).get(gid, {}), meta.get("baselines", {}).get(gid, {}))
        display = {"player": next((rows[player]["name"] for rows in records if player in rows), None),
                   "lineup": notes.get(scope["lineup_note_id"], {}).get("title")}
        if (player and not display["player"]) or (scope["lineup_note_id"] and not display["lineup"]):
            raise ConditionError("模板的适用范围缺少正式名称：" + group["name"])
        explanation = group.get("explanation") or group.get("explanation_before")
        runtime = {
            "id": gid, "name": group["name"], "event_id": group["event_id"], "priority": group.get("priority", 0),
            "expression": effective_expression(display, group["expression"]),
            "utterances": [{"id": u["id"], "text": u["text"]} for u in group["utterances"]],
        }
        if explanation:
            runtime["explanation"] = explanation
        result[event][group["extra_key"]].append(runtime)
    document = {"解释事件": {event: dict(keys) for event, keys in result.items()}}
    load_library(document, strict=True)
    return document
