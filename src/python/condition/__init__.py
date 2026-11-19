"""Evaluate catalog-declared game event conditions with three-valued logic."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import json
import os
import operator
import random
from pathlib import Path
import re


class ConditionError(ValueError):
    """Invalid condition, catalog reference, or input value."""

    def __init__(self, message, column=None):
        self.column = column
        super().__init__(f"第 {column} 列：{message}" if column else message)


_UNKNOWN = object()
_MAX_NESTING = 64
_DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "condition" / "catalog.json"
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_IDENT = re.compile(r"[^\W\d]\w*", re.UNICODE)


def _reject_constant(value):
    raise ConditionError(f"无效 JSON 数字 {value}")


_DECODER = json.JSONDecoder(parse_float=Decimal, parse_constant=_reject_constant)
_COMPARISONS = {"==": operator.eq, "<": operator.lt, "<=": operator.le,
                ">": operator.gt, ">=": operator.ge}


def _tokens(source):
    if not isinstance(source, str):
        raise ConditionError("表达式应为字符串")
    p = 0
    while p < len(source):
        c = source[p]
        if c.isspace():
            p += 1
            continue
        if c in '"[{':
            try:
                s, end = _DECODER.raw_decode(source, p)
            except ValueError as exc:
                raise ConditionError("无效 JSON 字面量", p + 1) from exc
            yield ("literal", s, p + 1)
            p = end
            continue
        m = _NUMBER.match(source, p)
        if m:
            number = _DECODER.decode(m[0])
            yield ("number", number, p + 1)
            p = m.end()
            continue
        m = _IDENT.match(source, p)
        if m:
            word = m[0]
            yield (word if word in ("and", "or", "not", "is", "in", "has", "true", "false") else "id", word, p + 1)
            p = m.end()
            continue
        symbol = source[p:p+2]
        if symbol in ("==", "<=", ">="):
            yield (symbol, symbol, p + 1)
            p += 2
        elif c in "().[]{},:<>":
            yield (c, c, p + 1)
            p += 1
        else:
            raise ConditionError(f"无法识别字符 {c!r}", p + 1)
    yield ("end", None, p + 1)


@dataclass
class Value:
    types: tuple
    value: object
    ops: object = None
    domain: tuple = ()  # all declared alternatives before runtime tag selection
    field: str = ""
    literal_string: bool = False


def _bool(value):
    return Value(("bool",), value)


def _truth(v):
    if v.types != ("bool",):
        raise ConditionError("逻辑运算需要布尔值")
    return v.value


def _allowed(v, op):
    if v.ops is not None and op not in v.ops:
        raise ConditionError(f"该属性不支持 {op}")


def _numeric(t):
    return t in ("int", "number")


def _integer(raw):
    if isinstance(raw, Decimal):
        return raw == raw.to_integral_value()
    return type(raw) is int or (isinstance(raw, float) and raw.is_integer())


class _Evaluator:
    def __init__(self, source, event_name, args, state, catalog):
        self.catalog = catalog
        try:
            self.params = catalog["events"][event_name]["parameters"]
        except (KeyError, TypeError) as exc:
            raise ConditionError(f"未声明事件 {event_name!r}") from exc
        self.args = args
        self.state = state
        for key, raw in args.items():
            if key not in self.params:
                raise ConditionError(f"未声明事件参数 {key}")
            self.validate_snapshot(self.declared(self.params[key], raw), 0)
        for key, raw in state.items():
            if key in catalog["roots"]:
                self.validate_snapshot(self.declared(catalog["roots"][key], raw), 0)
        self.tokens = iter(_tokens(source))
        self.token = next(self.tokens)
        self.column = self.token[2]
        self.depth = 0

    def validate_snapshot(self, value, depth):
        if depth > _MAX_NESTING:
            raise ConditionError("快照嵌套过深")
        if isinstance(value.value, list):
            for item in value.value:
                self.validate_snapshot(item, depth + 1)
        elif isinstance(value.value, dict):
            fields = self.catalog["types"][value.types[0]]
            for key, raw in value.value.items():
                if key == "类型" and len(value.domain) > 1:
                    continue  # union discriminator
                field = "名称" if key == "name" else key
                if field in fields:
                    self.check_enum(f"{value.types[0]}.{field}", raw)
                    self.validate_snapshot(self.declared(fields[field], raw), depth + 1)

    def check_enum(self, field, raw):
        allowed = self.catalog.get("enums", {}).get(field)
        if allowed is not None and raw is not None and raw not in allowed:
            raise ConditionError(f"{field} 允许的值为 {'、'.join(allowed)}")

    def enter(self):
        self.depth += 1
        if self.depth > _MAX_NESTING:
            raise ConditionError("表达式嵌套过深")

    def accept(self, kind):
        if self.token[0] != kind:
            return False
        self.column = self.token[2]
        self.token = next(self.tokens)
        return True

    def take(self, kind):
        value = self.token[1]
        if not self.accept(kind):
            raise ConditionError(f"预期 {kind}，得到 {self.token[0]}", self.token[2])
        return value

    def run(self):
        if self.token[0] == "end":
            return True
        try:
            result = _truth(self.disjunction())
        except ConditionError as exc:
            if exc.column is not None:
                raise
            raise ConditionError(str(exc), self.column) from exc
        if self.token[0] != "end":
            raise ConditionError(f"多余的标记 {self.token[1]!r}", self.token[2])
        return result is True

    def disjunction(self):
        left = self.conjunction()
        while self.accept("or"):
            left = self.logic("or", left, self.conjunction())
        return left

    def conjunction(self):
        left = self.negation()
        while self.accept("and"):
            left = self.logic("and", left, self.negation())
        return left

    def negation(self):
        if self.accept("not"):
            self.enter()
            value = self.negation()
            self.depth -= 1
            return self.logic("not", value)
        return self.comparison()

    def logic(self, op, left, right=None):
        a = _truth(left)
        if op == "not":
            return _bool(_UNKNOWN if a is _UNKNOWN else not a)
        b = _truth(right)
        decisive = op == "or"
        return _bool(decisive if decisive in (a,b) else _UNKNOWN if _UNKNOWN in (a,b) else not decisive)

    def comparison(self):
        left = self.primary()
        op = self.token[0]
        if op not in ("is", "in", "has", "<", "<=", "==", ">=", ">"):
            return left
        self.take(op)
        right = self.primary()
        return self.compare(op,left,right)

    def compare(self, op, left, right):
        _allowed(left, op)
        _allowed(right, op)
        if op in ("has", "in"):
            seq, member = (left, right) if op == "has" else (right, left)
            return _bool(self.contains(seq, member))
        if op == "is":
            if left.literal_string:
                self.check_enum(right.field, left.value)
            if right.literal_string:
                self.check_enum(left.field, right.value)
            return _bool(self.equal(left, right, identity=True))
        if not all(_numeric(t) for t in left.types + right.types):
            if not (op == "==" and left.types == right.types == ("bool",)):
                raise ConditionError(f"{op} 的操作数不兼容")
        a, b = left.value, right.value
        if _UNKNOWN in (a, b):
            return _bool(_UNKNOWN)
        return _bool(_COMPARISONS[op](a, b))

    def primary(self):
        kind, value, _ = self.token
        if self.accept("("):
            self.enter()
            result = self.disjunction()
            self.depth -= 1
            self.take(")")
            return result
        if self.accept("literal"):
            return self.literal(value)
        if self.accept("number"):
            return Value(("int" if isinstance(value, int) else "number",), value)
        if self.accept("true"):
            return _bool(True)
        if self.accept("false"):
            return _bool(False)
        return self.path(self.take("id"))

    def literal(self, raw, depth=0):
        if depth > _MAX_NESTING:
            raise ConditionError("字面量嵌套过深")
        if isinstance(raw, list):
            return Value(("Array<?>",), [self.literal(item, depth + 1) for item in raw])
        if isinstance(raw, dict):
            typ = self.canonical(raw.get("类型"))
            fields = self.catalog["types"].get(typ)
            name = raw.get("名称", raw.get("name"))
            if fields is None or not isinstance(name, str) or not name:
                raise ConditionError("实体字面量需要已声明的类型和名称")
            for key, item in raw.items():
                if key in ("类型", "name"):
                    continue
                if key not in fields:
                    raise ConditionError(f"未声明属性 {typ}.{key}")
                self.declared(fields[key], item)
                self.check_enum(f"{typ}.{key}", item)
            return Value((typ,), raw)
        if isinstance(raw, str):
            return Value(("string",), raw, literal_string=True)
        if isinstance(raw, bool):
            return _bool(raw)
        if isinstance(raw, (int, Decimal)):
            return Value(("number",), raw)
        raise ConditionError("无效的字面量")

    def canonical(self, name):
        if not isinstance(name, str):
            raise ConditionError("类型应为名称")
        return self.catalog.get("aliases", {}).get(name, name)

    def declared(self, spec, raw):
        if raw is None:
            raw = _UNKNOWN
        if spec.startswith("Array<") and spec.endswith(">"):
            if raw is not _UNKNOWN:
                if not isinstance(raw, list):
                    raise ConditionError(f"输入值应为 {spec}")
                raw = [self.declared(spec[6:-1], item) for item in raw]
            return Value((spec,), raw)
        types = tuple(self.canonical(t) for t in spec.split("|"))
        domain = types
        if raw is _UNKNOWN:
            return Value(types, raw)
        if len(types) > 1:
            if not isinstance(raw, dict) or "类型" not in raw:
                raise ConditionError(f"输入值应声明类型 {spec}")
            tag = self.canonical(raw["类型"])
            if tag not in types:
                raise ConditionError(f"不兼容的实体类型 {tag}")
            types = (tag,)
        if len(types) == 1:
            t = types[0]
            valid = {
                "string": isinstance(raw, str),
                "bool": type(raw) is bool,
                "int": _integer(raw),
                "number": type(raw) in (float, int, Decimal),
            }.get(t, t in self.catalog["types"] and isinstance(raw, (dict, str)))
            if not valid:
                raise ConditionError(f"输入值应为 {t}")
            if (isinstance(raw, dict) and "类型" in raw
                    and "类型" not in self.catalog["types"][t]
                    and self.canonical(raw["类型"]) != t):
                raise ConditionError(f"实体标签与声明类型 {t} 不匹配")
        return Value(types, raw, domain=domain)

    def card_tags(self, value):
        raw = value.value
        if isinstance(raw, list):
            tags = []
            for item in raw:
                resolved = self.card_tags(item)
                tags.extend([None] if resolved is _UNKNOWN else resolved)
            return tags
        if raw is _UNKNOWN:
            return _UNKNOWN
        obj = raw if isinstance(raw, dict) else {}
        name = obj.get("名称", obj.get("name")) if isinstance(raw, dict) else raw
        identity = obj.get("id")
        if type(identity) is int:
            identity = f"card:{identity}"
        awake = obj.get("已觉醒")
        catalog = self.catalog.get("card_tags", {})
        candidates = catalog.values()
        if identity is not None:
            row = catalog.get(identity) if isinstance(identity, str) else None
            if not row or (name is not None and name != row["name"]) or row["type"] not in value.types:
                return _UNKNOWN
            name = row["name"]
            if row["type"] != "英雄":
                candidates = [row]
        matching = [set(row["tags"]) for row in candidates
                    if row["type"] in value.types and (name is None or row["name"] == name)
                    and (name is not None or identity is not None)
                    and (awake is None or row["type"] != "英雄" or row["awakened"] == awake)]
        return sorted(set.intersection(*matching)) if matching else _UNKNOWN

    def sum_field(self, array_type):
        self.take("(")
        field = self.take("id")
        self.take(")")
        if not array_type.startswith("Array<"):
            raise ConditionError("求和需要实体数组")
        owners = [self.canonical(t) for t in array_type[6:-1].split("|")]
        types = {self.catalog["types"].get(t, {}).get(field) for t in owners}
        if not all(_numeric(t) for t in types):
            raise ConditionError(f"求和需要每个数组元素都声明数值属性 {field}")
        return field, "int" if types == {"int"} else "number"

    def path(self, root):
        if root in self.params:
            result = self.declared(self.params[root], self.args.get(root, _UNKNOWN))
        elif root in self.catalog["roots"]:
            result = self.declared(self.catalog["roots"][root], self.state.get(root, _UNKNOWN))
        else:
            raise ConditionError(f"未声明路径 {root}")
        while self.accept("."):
            attr = self.take("id")
            if attr == "求和" and self.token[0] == "(":
                field, typ = self.sum_field(result.types[0])
                total = 0
                if result.value is _UNKNOWN:
                    total = _UNKNOWN
                else:
                    for item in result.value:
                        raw = item.value.get(field) if isinstance(item.value, dict) else None
                        if raw is None:
                            total = _UNKNOWN
                            break
                        total += Fraction(str(raw))
                result = Value((typ,), total)
                continue
            if attr == "name":
                attr = "名称"
            owners = result.domain or result.types
            if attr == "标签" and len(owners) == 1 and owners[0].startswith("Array<"):
                owners = tuple(self.canonical(t) for t in owners[0][6:-1].split("|"))
            options = [self.catalog["types"].get(t, {}).get(attr) for t in owners]
            if not options or None in options or len(set(options)) != 1:
                raise ConditionError(f"未声明属性 {root}.{attr}")
            raw = result.value
            if attr == "标签":
                raw = self.card_tags(result)
            elif isinstance(raw, dict):
                raw = raw.get(attr, raw.get("name", _UNKNOWN) if attr == "名称" else _UNKNOWN)
            elif not (isinstance(raw, str) and attr == "名称"):
                raw = _UNKNOWN
            owner = owners[0] if attr == "标签" else result.types[0]
            field = f"{owner}.{attr}"
            ops = self.catalog.get("operations", {}).get(field)
            result = self.declared(options[0], raw)
            result.ops = ops
            result.field = field
        return result

    def equal(self, left, right, identity=False):
        types = self.catalog["types"]
        compatible = False
        left_domain = left.domain or left.types
        right_domain = right.domain or right.types
        for a in left_domain:
            for b in right_domain:
                if a == b:
                    compatible |= not identity or a == "string" or a in types
                elif not identity and _numeric(a) and _numeric(b):
                    compatible = True
                elif (a in types and b == "string") or (b in types and a == "string"):
                    compatible = True
                    if len(left_domain) > 1 or len(right_domain) > 1:
                        raise ConditionError("混合列表中的名称需要明确实体类型")
        if not compatible:
            raise ConditionError("比较双方类型不兼容")
        if _UNKNOWN in (left.value, right.value):
            return _UNKNOWN
        if (set(left.types).isdisjoint(right.types)
                and all(t in types for t in left.types + right.types)):
            return False

        def name(v):
            if isinstance(v.value, dict):
                n = v.value.get("名称", v.value.get("name"))
                if n is not None and not isinstance(n, str):
                    raise ConditionError("实体名称应为字符串")
                return n if n is not None else _UNKNOWN
            return v.value

        a, b = name(left), name(right)
        if _UNKNOWN in (a, b):
            return _UNKNOWN
        return a == b

    def contains(self, seq, member):
        if len(seq.types) != 1 or not seq.types[0].startswith("Array<"):
            raise ConditionError("成员运算需要列表")
        if any(t.startswith("Array<") for t in member.types):
            raise ConditionError("成员运算需要单个元素")
        inner = seq.types[0][6:-1]
        if inner != "?":
            self.equal(self.declared(inner, _UNKNOWN), member)
        if seq.value is _UNKNOWN:
            return _UNKNOWN
        matches = []
        for item in seq.value:
            if item.literal_string:
                self.check_enum(member.field, item.value)
            if (set(item.types).isdisjoint(member.types)
                    and all(t in self.catalog["types"] for t in item.types + member.types)):
                continue
            matches.append(self.equal(item, member))
        return True if True in matches else _UNKNOWN if _UNKNOWN in matches else False


def _object(data, label):
    if isinstance(data, (str, bytes, bytearray)):
        try:
            data = json.loads(data, parse_float=Decimal, parse_constant=_reject_constant)
        except (UnicodeError, ValueError) as exc:
            raise ConditionError(f"{label}的 JSON 无效") from exc
    if not isinstance(data, dict):
        raise ConditionError(f"{label}应为对象")
    return data


def _catalog(catalog):
    if catalog is None:
        filename = os.environ.get("WXQ_CONDITION_CATALOG") or _DEFAULT_CATALOG
        try:
            with open(filename, encoding="utf-8") as file:
                catalog = json.load(file)
            if catalog.get("card_tags_file") == "card-tags.json":
                with open(Path(filename).with_name("card-tags.json"), encoding="utf-8") as file:
                    catalog["card_tags"] = json.load(file)
        except (OSError, ValueError) as exc:
            raise ConditionError(f"无法读取条件目录 {filename}") from exc
    catalog = _object(catalog, "目录")
    return _object(catalog.get("condition_catalog", catalog), "目录")


def _event_name(name, catalog):
    if not isinstance(name, str) or name in catalog["events"]:
        return name
    prefix = "解释为何"
    alias = name.removeprefix(prefix) if name.startswith(prefix) else prefix + name
    return alias if alias in catalog["events"] else name


def evaluate_condition(event_json, expression, state_json, catalog=None):
    """Return True only when the expression evaluates to a known true value."""
    event = _object(event_json, "事件")
    args = event.get("参数", {})
    if not isinstance(args, dict):
        raise ConditionError("事件参数应为对象")
    state = _object(state_json, "局势")
    try:
        definitions = _catalog(catalog)
        return _Evaluator(expression, _event_name(event.get("事件"), definitions), args, state, definitions).run()
    except RecursionError as exc:
        raise ConditionError("表达式嵌套过深") from exc


def validate_expression(event_name, expression, catalog=None):
    """Raise ConditionError if the expression is invalid for this event."""
    evaluate_condition({"事件": event_name}, expression, {}, catalog)


def choose_utterance(config, event_json, state_json, *, rng=None):
    """Pick among the most specific matches at the highest numeric priority.

    Install this package's requirements.txt for semantic comparisons between
    different expressions. Single-expression evaluation uses the standard library.
    """
    config = _object(config, "运行时配置")
    event = _object(event_json, "事件")
    state = _object(state_json, "局势")
    player = _object(state.get("玩家", {}), "玩家")
    groups = config.get("groups")
    if not isinstance(groups, list):
        raise ConditionError("运行时配置需要 groups 列表")
    catalog = _catalog(config.get("condition_catalog"))
    name = _event_name(event.get("事件"), catalog)
    event = {**event, "事件": name}
    evaluate_condition(event, "", state, catalog)
    eligible = []
    best = None
    for group in groups:
        if not isinstance(group, dict):
            raise ConditionError("事件组应为对象")
        if _event_name(group.get("event_name"), catalog) != name:
            continue
        scope = _object(group.get("scope", {}), "适用范围")
        if set(scope) - {"player", "lineup"} or any(
            value is not None and not isinstance(value, str) for value in scope.values()
        ):
            raise ConditionError("适用范围应指定棋手或阵容名称")
        if any(scope.get(key) is not None and scope[key] != player.get(attr)
               for key, attr in (("player", "使用棋手"), ("lineup", "使用阵容"))):
            continue
        if not evaluate_condition(event, group.get("expression", ""), state, catalog):
            continue
        lines = group.get("utterances")
        priority = group.get("priority", 0)
        if not isinstance(lines, list) or not lines or not all(isinstance(s, str) and s.strip() for s in lines):
            raise ConditionError("命中组需要非空文案列表")
        if type(priority) is not int:
            raise ConditionError("事件组优先级应为整数")
        if best is None or priority > best:
            best = priority
            eligible = []
        if priority == best:
            eligible.append(group)
    picker = random if rng is None else rng
    if not eligible:
        return None
    if len({group.get("expression", "").strip() for group in eligible}) > 1:
        from .specificity import most_specific
        eligible = most_specific(eligible, event["事件"], catalog)
    return picker.choice(picker.choice([group["utterances"] for group in eligible]))

