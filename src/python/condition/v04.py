"""Typed v0.4 expressions and the explanation-event runtime."""

import ast
from dataclasses import dataclass
from functools import lru_cache
import json
import logging
import operator
from pathlib import Path
import random
import re

from . import ConditionError, _UNKNOWN


SOURCE = Path(__file__).resolve().parents[2] / "condition" / "catalog-v04.json"
TOKEN = re.compile(r'\s+|"(?:[^"\\]|\\.)*"|[^\W\d]\w*|\d+|==|!=|<=|>=|[().\[\],<>+*%\-]')
FUNCTIONS = {"len", "any", "all", "none", "count", "sum", "filter"}
SCALARS = {"string", "int", "bool"}
OUTPUT = SCALARS | {"Array<string>", "Array<卡牌>"}
COMPARISON = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
              ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
              ast.In: lambda a, b: _contains(b, a),
              ast.NotIn: lambda a, b: _negate(_contains(b, a))}
ARITHMETIC = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Mod: operator.mod}
LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def catalog():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def lineup_name(name):
    return catalog()["lineup_aliases"].get(name, name)


def event_fields(event):
    try:
        return catalog()["actions"][catalog()["events"][event]["action"]]
    except KeyError as exc:
        raise ConditionError("未注册解释类型：" + event) from exc


def _parse(source):
    if not isinstance(source, str) or len(source) > 100000:
        raise ConditionError("表达式应为长度有效的文本")
    tokens = []
    p = 0
    previous_is_string = False
    for match in TOKEN.finditer(source):
        if match.start() != p:
            raise ConditionError("表达式含无效字符", p + 1)
        p = match.end()
        token = match[0]
        if token.isspace():
            continue
        is_string = token.startswith('"')
        if previous_is_string and is_string:
            raise ConditionError("相邻文本字面量之间需要操作符", match.start() + 1)
        previous_is_string = is_string
        if token.startswith('"'):
            try:
                token = repr(json.loads(token))
            except ValueError as exc:
                raise ConditionError("无效文本字面量", match.start() + 1) from exc
        elif token.startswith("_"):
            raise ConditionError("未声明标识符", match.start() + 1)
        if token == "." and (not tokens or tokens[-1] in {"(", ",", "and", "or", "not", "in",
                                                           "==", "!=", "<", ">", "<=", ">="}):
            tokens.append("_item")
        tokens.append(token)
    if p != len(source):
        raise ConditionError("表达式含无效字符", p + 1)
    try:
        return ast.parse(" ".join(tokens), mode="eval").body
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ConditionError("表达式语法无效") from exc


def _path(node):
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (*_path(node.value), node.attr)
    raise ConditionError("属性必须来自声明的路径")


def _is_nil(node):
    return isinstance(node, ast.Name) and node.id == "nil"


def _facts(node, truth):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _facts(node.operand, not truth)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And if truth else ast.Or):
        return set().union(*(_facts(child, truth) for child in node.values))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, (ast.Name, ast.Attribute)):
        right = node.comparators[0]
        path = _path(node.left)
        if _is_nil(right) and isinstance(node.ops[0], ast.NotEq if truth else ast.Eq):
            return {path}
        if (isinstance(right, ast.Constant) and right.value == "英雄" and path[-1] == "卡牌类型"
                and isinstance(node.ops[0], ast.Eq if truth else ast.NotEq)):
            return {(*path[:-1], "#hero")}
    return set()


class _Validator:
    def __init__(self, event, slot):
        self.actions = event_fields(event)
        self.slot = slot
        self.auto_guards = set()

    def path_type(self, path, guards, item, *, nil_check=False):
        root, *fields = path
        if root == "_item":
            kind = "卡牌" if item == "英雄元素" else item
        else:
            kind = catalog()["roots"].get(root)
        if not kind:
            raise ConditionError("未声明根对象：" + root)
        for index, field in enumerate(fields, 1):
            prefix = path[:index]
            if field == '阵容英雄名列表' and item:
                raise ConditionError('阵容英雄名列表只能在谓词外使用')
            if kind.endswith("?") and prefix not in guards:
                if not self.slot or item:
                    raise ConditionError("可空对象缺少前置守卫：" + ".".join(prefix))
                self.auto_guards.add(prefix)
            owner = kind.removesuffix("?")
            table = self.actions if owner == "动作" else catalog()["types"].get(owner, {})
            if field not in table:
                raise ConditionError("未声明属性：" + ".".join(path[:index + 1]))
            if (owner == "卡牌" and field in catalog()["hero_fields"]
                    and prefix[-1] not in catalog()["hero_paths"] and not (prefix == ("_item",) and item == "英雄元素")
                    and (*prefix, "#hero") not in guards):
                raise ConditionError("英雄专属属性需要卡牌类型守卫：" + ".".join(path[:index + 1]))
            kind = table[field]
        if item and root != "_item" and kind.removesuffix("?") not in SCALARS and not nil_check:
            raise ConditionError("谓词只能读取外部标量")
        return kind.removesuffix("?") if not nil_check and path in guards else kind

    def kind(self, node, guards=frozenset(), item=None):
        if isinstance(node, (ast.Name, ast.Attribute)):
            return self.path_type(_path(node), guards, item)
        if isinstance(node, ast.Constant) and type(node.value) in {int, str}:
            return "int" if type(node.value) is int else "string"
        if isinstance(node, ast.List) and all(isinstance(n, ast.Constant) and type(n.value) is str for n in node.elts):
            return "Array<string>"
        if isinstance(node, ast.UnaryOp):
            kind = self.kind(node.operand, guards, item)
            if isinstance(node.op, ast.Not) and kind == "bool":
                return "bool"
            if isinstance(node.op, ast.USub) and kind == "int" and (self.slot or isinstance(node.operand, ast.Constant)):
                return "int"
        if isinstance(node, ast.BoolOp):
            available = set(guards)
            for child in node.values:
                self.require(child, "bool", available, item)
                available.update(_facts(child, isinstance(node.op, ast.And)))
            return "bool"
        if isinstance(node, ast.BinOp) and self.slot and type(node.op) in ARITHMETIC:
            self.require(node.left, "int", guards, item)
            self.require(node.right, "int", guards, item)
            return "int"
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return self.comparison(node, guards, item)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            return self.call(node, guards, item)
        raise ConditionError("表达式含不支持的语法或类型")

    def require(self, node, expected, guards, item):
        if self.kind(node, guards, item) != expected:
            raise ConditionError("表达式需要 " + expected)

    def comparison(self, node, guards, item):
        right = node.comparators[0]
        op = type(node.ops[0])
        if _is_nil(right):
            if (self.slot and not item or op not in {ast.Eq, ast.NotEq}
                    or not self.path_type(_path(node.left), guards, item, nil_check=True).endswith("?")):
                raise ConditionError("nil 只能用于可空路径的守卫")
            return "bool"
        left_type = self.kind(node.left, guards, item)
        right_type = self.kind(right, guards, item)
        if op in {ast.In, ast.NotIn}:
            valid = left_type == "string" and right_type == "Array<string>"
        elif op in {ast.Eq, ast.NotEq}:
            valid = left_type == right_type and left_type in SCALARS
        else:
            valid = op in COMPARISON and left_type == right_type == "int"
        if not valid:
            raise ConditionError("比较的操作数不兼容")
        return "bool"

    def call(self, node, guards, item):
        name = node.func.id
        count = 1 if name == "len" else 2
        if name not in FUNCTIONS or len(node.args) != count or item:
            raise ConditionError("无效函数、参数个数或嵌套聚合：" + name)
        sequence = self.kind(node.args[0], guards)
        if not sequence.startswith("Array<"):
            raise ConditionError(name + " 需要列表")
        if name == "len":
            return "int"
        input_list = node.args[0]
        while isinstance(input_list, ast.Call) and input_list.func.id == "filter":
            input_list = input_list.args[0]
        member = "英雄元素" if isinstance(input_list, ast.Attribute) and input_list.attr == "场上英雄列表" else sequence[6:-1]
        if name == "sum":
            if not isinstance(node.args[1], ast.Attribute) or _path(node.args[1])[0] != "_item":
                raise ConditionError("sum 需要元素数值字段")
            self.require(node.args[1], "int", guards, member)
            return "int"
        self.require(node.args[1], "bool", guards, member)
        return sequence if name == "filter" else "int" if name == "count" else "bool"


def _negate(value):
    return _UNKNOWN if value is _UNKNOWN else not value


def _contains(values, value):
    if value in values:
        return True
    return _UNKNOWN if _UNKNOWN in values else False


def _read(path, state, item):
    root, *keys = path
    value = item if root == "_item" else state.get(root, _UNKNOWN)
    for key in keys:
        if value is None:
            raise ConditionError("读取了 nil 对象：" + ".".join(path))
        value = value.get(key, _UNKNOWN) if isinstance(value, dict) else _UNKNOWN
    if keys and keys[-1] == '阵容英雄名列表' and not (isinstance(value, list) and all(isinstance(name, str) for name in value)):
        return _UNKNOWN
    if isinstance(value, str) and (path[-1] == "阵容名称" or path == ("动作", "阵容")):
        return lineup_name(value)
    return value


def _eval(node, state, item=_UNKNOWN):
    if isinstance(node, (ast.Name, ast.Attribute)):
        return None if _is_nil(node) else _read(_path(node), state, item)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [n.value for n in node.elts]
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, state, item)
        if value is _UNKNOWN:
            return value
        return not value if isinstance(node.op, ast.Not) else -value
    if isinstance(node, ast.BoolOp):
        decisive = isinstance(node.op, ast.Or)
        unknown = False
        for child in node.values:
            value = _eval(child, state, item)
            if value is decisive:
                return value
            unknown |= value is _UNKNOWN
        return _UNKNOWN if unknown else not decisive
    if isinstance(node, (ast.Compare, ast.BinOp)):
        left = _eval(node.left, state, item)
        right = _eval(node.comparators[0] if isinstance(node, ast.Compare) else node.right, state, item)
        if left is _UNKNOWN or right is _UNKNOWN:
            return _UNKNOWN
        if isinstance(node, ast.BinOp) and (type(left) is not int or type(right) is not int):
            return _UNKNOWN
        if isinstance(node, ast.Compare) and right is not None and not isinstance(node.ops[0], (ast.In, ast.NotIn)) and type(left) is not type(right):
            return _UNKNOWN
        operation = COMPARISON[type(node.ops[0])] if isinstance(node, ast.Compare) else ARITHMETIC[type(node.op)]
        return operation(left, right)
    name = node.func.id
    if name == "len" and isinstance(node.args[0], ast.Attribute):
        path = _path(node.args[0])
        if "_legacy_counts" in state and len(path) == 2 and path[-1] in ("场上英雄列表", "手牌列表"):
            return state["_legacy_counts"].get(path, _UNKNOWN)
    values = _eval(node.args[0], state, item)
    if values is _UNKNOWN:
        return values
    if name == "len":
        return len(values)
    if name in {"any", "all", "none"}:
        decisive = name != "all"
        unknown = False
        for member in values:
            result = _eval(node.args[1], state, member)
            if result is decisive:
                return name == "any"
            unknown |= result is _UNKNOWN
        return _UNKNOWN if unknown else name != "any"
    results = [_eval(node.args[1], state, member) for member in values]
    if _UNKNOWN in results:
        return _UNKNOWN
    if name == "sum":
        return sum(results)
    if name == "count":
        return sum(result is True for result in results)
    return [member for member, result in zip(values, results) if result is True]


@dataclass(frozen=True)
class Expression:
    node: object
    kind: str
    guards: tuple = ()

    def evaluate(self, state):
        if any(_read(path, state, _UNKNOWN) in (None, _UNKNOWN) for path in self.guards):
            return _UNKNOWN
        return True if self.node is None else _eval(self.node, state)


@lru_cache(maxsize=4096)
def compile_expression(event, source, *, slot=False):
    validator = _Validator(event, slot)
    if isinstance(source, str) and not source.strip() and not slot:
        return Expression(None, "bool")
    try:
        node = _parse(source)
        kind = validator.kind(node)
        if slot:
            if kind.removesuffix("?") not in OUTPUT:
                raise ConditionError("该占位符类型不能输出，单卡请显式引用 .名称")
        elif kind != "bool":
            raise ConditionError("条件必须返回布尔值")
    except RecursionError as exc:
        raise ConditionError("表达式嵌套过深") from exc
    return Expression(node, kind, tuple(sorted(validator.auto_guards, key=lambda path: (len(path), path))))


@lru_cache(maxsize=4096)
def compile_template(event, text):
    parts = []
    pos = 0
    for match in re.finditer(r"\{\{(.*?)\}\}", text, re.S):
        raw = text[pos:match.start()]
        fragment = match[1]
        if any(marker in raw or marker in fragment for marker in ("{{", "}}")):
            raise ConditionError("占位符标记不配对或嵌套")
        parts.extend((raw, compile_expression(event, fragment, slot=True)))
        pos = match.end()
    if "{{" in text[pos:] or "}}" in text[pos:]:
        raise ConditionError("占位符标记不配对")
    return (*parts, text[pos:])


def render_compiled(parts, state):
    output = []
    for part in parts:
        if isinstance(part, str):
            output.append(part)
            continue
        try:
            value = part.evaluate(state)
            if value is _UNKNOWN or value is None:
                return None
            if part.kind.startswith("Array<"):
                if not value:
                    return None
                names = value if part.kind == "Array<string>" else [member.get("名称") for member in value]
                if not all(isinstance(name, str) and name for name in names):
                    return None
                output.append("、".join(names))
            elif part.kind == "bool" and type(value) is bool:
                output.append("是" if value else "否")
            elif part.kind == "int" and type(value) is int or part.kind == "string" and type(value) is str:
                output.append(str(value))
            else:
                return None
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            return None
    return "".join(output)


def render(event, text, state):
    return render_compiled(compile_template(event, text), state)


def validate_key(event, key):
    fields = event_fields(event)
    names = catalog()["events"][event]["key"]
    if not isinstance(key, str):
        raise ConditionError("额外信息键必须为文本")
    segments = key.split("-") if key else []
    if len(segments) != len(names) or any(
        not part or part.strip() != part or part != "*" and ("*" in part or fields[field]=="int" and not re.fullmatch("0|[1-9][0-9]*",part))
        for field,part in zip(names,segments)
    ):
        raise ConditionError(f"{event} 的额外信息键无效：{key!r}")
    return tuple(segments)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConditionError("JSON 键重复：" + key)
        result[key] = value
    return result


def load_library(data):
    if isinstance(data, (str, bytes, bytearray)):
        data = json.loads(data, object_pairs_hook=_unique)
    if not isinstance(data, dict) or set(data) != {"解释事件"} or not isinstance(data["解释事件"], dict):
        raise ConditionError("话术库顶层必须为解释事件")
    result = {}
    groups_seen = set()
    for event, keys in data["解释事件"].items():
        event_fields(event)
        if not isinstance(keys, dict):
            raise ConditionError("解释类型下必须是额外信息键对象")
        result[event] = {}
        for key, groups in keys.items():
            segments = validate_key(event, key)
            if not isinstance(groups, list):
                raise ConditionError("额外信息键下必须是话术组数组")
            compiled = []
            for group in groups:
                required = {"id", "name", "event_id", "priority", "expression", "explanation", "utterances"}
                if not isinstance(group, dict) or group.keys() != required:
                    raise ConditionError("话术组字段无效")
                if (any(not isinstance(group[k], str) or not group[k].strip() for k in ("id", "name", "event_id"))
                        or not isinstance(group["explanation"], str) or type(group["priority"]) is not int
                        or group["id"] in groups_seen or not isinstance(group["utterances"], list) or not group["utterances"]):
                    raise ConditionError("话术组身份、优先级或话术无效")
                groups_seen.add(group["id"])
                utterances = {}
                for row in group["utterances"]:
                    if (not isinstance(row, dict) or set(row) != {"id", "text"}
                            or any(not isinstance(row[k], str) or not row[k].strip() for k in row)
                            or row["id"] in utterances):
                        raise ConditionError("话术身份或文本无效")
                    utterances[row["id"]] = compile_template(event, row["text"])
                compiled.append((group, compile_expression(event, group["expression"]), utterances))
            result[event][segments] = compiled
    return result


def matching_keys(keys, event, state):
    actual = []
    for field in catalog()["events"].get(event, {}).get("key", []):
        value = state.get("动作", {}).get(field)
        if isinstance(value, dict):
            value = value.get("名称")
        if field == "阵容" and isinstance(value, str):
            value = lineup_name(value)
        actual.append(str(value) if type(value) in (str, int) and str(value) and "-" not in str(value)
                      and "*" not in str(value) else None)
    legacy = "_legacy_counts" in state
    return [pattern for pattern in keys if all(
        segment == value or segment == "*" and (value is not None or legacy)
        for segment, value in zip(pattern, actual)
    )]


def winning_pool(library, event, state):
    from collections import defaultdict

    keys = library.get(event, {})
    levels = defaultdict(list)
    for pattern in matching_keys(keys, event, state):
        groups = keys[pattern]
        levels[pattern.count("*")].extend(groups)
    if not levels:
        return "unconfigured", []
    for level in sorted(levels):
        tiers = defaultdict(list)
        for group, condition, utterances in levels[level]:
            try:
                matched = condition.evaluate(state) is True
            except (ValueError, TypeError, ArithmeticError):
                LOG.warning("话术组条件求值失败：%s", group["id"], exc_info=True)
                continue
            if matched:
                tiers[group["priority"]].extend((group, uid, parts) for uid, parts in utterances.items())
        for priority in sorted(tiers, reverse=True):
            rendered = [{"status": "matched", "id": group["id"], "utterance_id": uid,
                         "event_id": group["event_id"], "text": text}
                        for group, uid, parts in tiers[priority]
                        if (text := render_compiled(parts, state)) is not None]
            if rendered:
                return "matched", rendered
    return "unmatched", []


def choose(library, event, state, *, rng=None):
    status, candidates = winning_pool(library, event, state)
    return (rng or random).choice(candidates) if candidates else {"status": status}
