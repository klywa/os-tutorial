"""Translate old authoring rules and adapt v3 snapshots to the v0.4 contract."""

import json
import re

from . import ConditionError, _Evaluator, _UNKNOWN, _catalog, _event_name
from .v04 import catalog, compile_expression, compile_template, event_fields, lineup_name


ARGS = {
    "解释为何购买英雄": ("选中", "候选列表"),
    "解释为何购买效果牌": ("选中", "候选列表"),
    "解释为何上阵英雄": ("英雄",),
    "解释为何合成英雄": ("英雄",),
    "解释为何从手牌出售英雄": ("英雄",),
    "解释为何从战场出售英雄": ("英雄",),
    "解释为何选择英雄": ("候选列表", "选中"),
    "解释为何选择效果牌": ("候选列表", "选中"),
    "解释为何选择天赋": ("候选列表", "选中"),
    "解释为何选择棋手技能": ("候选列表", "选中"),
    "解释为何使用无目标效果牌": ("卡牌",),
    "解释为何使用关键效果牌": ("卡牌",),
    "解释为何对目标使用效果牌": ("目标", "卡牌"),
    "解释为何使用棋手技能": ("卡牌",),
    "解释为何对目标使用棋手技能": ("目标", "卡牌"),
    "解释为何穿戴装备": ("目标英雄", "装备"),
    "解释为何铸造装备": ("目标英雄", "原装备", "目标装备"),
    "解释为何转移装备": ("原英雄", "装备", "目标英雄"),
    "解释为何棋手升级": ("目标等级",),
    "解释为何建议向某阵容发展": ("阵容",),
}
TITLES = {"解释为何选择英雄牌": "解释为何选择英雄", "解释为何从场上出售英雄": "解释为何从战场出售英雄"}
RENAMES = {"使用棋手": "棋手名称", "使用阵容": "阵容名称", "当前阵容": "阵容名称",
           "手牌": "手牌列表", "已选天赋": "天赋列表", "战场": "场上英雄列表",
           "已穿装备": "装备列表", "定位": "英雄定位", "阶数": "品阶", "name": "名称"}
CARD_TYPES = {"英雄", "效果牌", "装备", "棋手技能", "天赋", "衍生物", "单位"}
ARRAY_TYPES = {"战场", "手牌", "商店列表", "已穿装备", "已选天赋"}
ARRAY_KIND = {"已穿装备": "装备", "已选天赋": "天赋"}
LEGACY_SLOT = re.compile(r"\{([^{}]+)\}")


def literal(value):
    return json.dumps(value, ensure_ascii=False)


class _Syntax(_Evaluator):
    def path(self, root):
        path = [root]
        while self.accept("."):
            field = self.take("id")
            if field in ("计数", "求和") and self.accept("("):
                args = []
                if not self.accept(")"):
                    args.append(self.take("id"))
                    if self.accept(","):
                        args.append(self.take("literal"))
                    self.take(")")
                return field, tuple(path), args
            path.append(field)
        return ("path", tuple(path))

    def literal(self, raw, depth=0):
        return ("literal", raw)

    def logic(self, op, left, right=None):
        return (op, left, right)

    def compare(self, op, left, right):
        return (op, left, right)

    def primary(self):
        if self.token[0] == "number":
            return ("literal", self.take("number"))
        if self.token[0] in ("true", "false"):
            return ("literal", self.take(self.token[0]) == "true")
        return super().primary()

    def node(self):
        result = self.disjunction()
        if self.token[0] != "end":
            raise ConditionError("多余的旧版条件标记")
        return result


def _card_kind(kind):
    return "棋手牌" if kind == "棋手技能" else kind


def _guarded(text, paths):
    guards = sorted(set(paths), key=lambda path: (path.count("."), path))
    if not guards:
        return text
    return "(" + " and ".join([*(p if " == " in p else p + " != nil" for p in guards), text]) + ")"


class Translation:
    def __init__(self, event, legacy_catalog=None):
        self.original_event = event
        self.event = TITLES.get(event, event)
        event_fields(self.event)
        self.catalog = _catalog(legacy_catalog)
        self.params = self.catalog["events"][event]["parameters"]
        self.arg_names = dict(zip((f"arg{i}" for i in range(1, 4)), ARGS.get(self.event, ())))

    def parse(self, expression):
        return _Syntax(expression, self.original_event, {}, {}, self.catalog).node()

    def path(self, original):
        root, *attrs = original
        guards = []
        if root in self.arg_names:
            arg = self.arg_names[root]
            base = "动作." + arg
            if arg == "阵容":
                return base, guards
            if arg == "目标" and attrs and attrs[0] != "名称":
                base = "动作.目标英雄"
                guards.append(base)
            if arg == "选中" and attrs and RENAMES.get(attrs[0], attrs[0]) in catalog()["hero_fields"]:
                guards.append('动作.选中.卡牌类型 == "英雄"')
        elif root == "玩家":
            base = "我方"
        elif root == "对局" and attrs[:1] == ["当前对手"]:
            base = "对手"
            attrs.pop(0)
            guards.append(base)
        elif root == "商店" and attrs[:1] == ["商店列表"]:
            base = "我方"
        elif root == "对局":
            base = root
        else:
            raise ConditionError("未映射旧路径：" + ".".join(original))
        for field in attrs:
            if field in ("场上英雄数", "手牌数"):
                base = "len(" + base + (" .场上英雄列表)" if field == "场上英雄数" else ".手牌列表)")
                base = base.replace(" .", ".")
            else:
                base += "." + RENAMES.get(field, field)
            if field in ("主C", "最高等级英雄"):
                guards.append(base)
        return base, guards

    def value(self, node, *, name=False):
        kind, *parts = node
        if kind == "literal":
            raw = parts[0]
            if isinstance(raw, dict):
                return literal(raw.get("名称", raw.get("name"))), []
            return literal(raw), []
        path, *args = parts
        text, guards = self.path(path)
        if kind == "计数":
            options = args[0]
            if not options:
                return f"len({text})", guards
            field, value = options
            if field == "标签":
                tag = {"登场": "具有登场效果", "整备": "具有整备效果"}.get(value, value)
                predicate = f"{literal(tag)} in .标签"
            elif field == "阵营":
                predicate = f".阵营 == {literal(value)}"
            else:
                plain = [item for item in value if isinstance(item, str)]
                forms = [f'(.名称 == {literal(item["名称"])}'
                         + (f' and {"not " if not item["已觉醒"] else ""}.已觉醒' if "已觉醒" in item else "") + ")"
                         for item in value if isinstance(item, dict)]
                if plain:
                    forms.append(f".名称 in {literal(plain)}")
                predicate = " or ".join(forms)
            return f"count({text}, {predicate})", guards
        if kind == "求和":
            return f"sum({text}, .{args[0][0]})", guards
        if name and not text.endswith(".名称"):
            text += ".名称"
        return text, guards

    def entity(self, node):
        if node[0] == "literal":
            return node[1].get("类型") if isinstance(node[1], dict) else None
        if node[0] != "path":
            return None
        path = node[1]
        if path[-1] in ("主C", "最高等级英雄"):
            return "英雄"
        if len(path) == 1 and self.params.get(path[0]) in CARD_TYPES:
            return self.params[path[0]]
        return None

    def is_list(self, node):
        if node[0] != "path":
            return False
        path = node[1]
        return path[-1] in ARRAY_TYPES or len(path) == 1 and self.params.get(path[0], "").startswith("Array<")

    def membership(self, array, member):
        path = array[1]
        card_kind = self.entity(member)
        seq, guards = self.value(array)
        raw_member = member[1]
        if path[-1] == "战场" and card_kind == "衍生物":
            seq = seq.replace(".场上英雄列表", ".场上衍生物列表")
        if path[-1] == "战场" and card_kind == "单位":
            # A dynamic target may be a hero, a derivative or a different unit.
            name, external = self.value(member, name=True)
            kind, _ = self.value(member)
            return (f'(({kind}.卡牌类型 == "英雄" and any({seq}, .名称 == {name})) or '
                    f'({kind}.卡牌类型 == "衍生物" and any({seq.replace(".场上英雄列表", ".场上衍生物列表")}, .名称 == {name})))',
                    [*guards, *external])
        name, external = self.value(member, name=bool(card_kind and member[0] == "path"))
        predicate = f".名称 == {name}"
        kind = ARRAY_KIND.get(path[-1]) or ("英雄" if path[-1] == "战场" and card_kind != "衍生物" else None)
        if card_kind and not kind and path[-1] in ("商店列表", "手牌"):
            predicate = f".卡牌类型 == {literal(_card_kind(card_kind))} and {predicate}"
        if self.event.startswith("解释为何购买") and self.arg_names.get(path[0]) == "候选列表":
            raise ConditionError("旧购买候选条件需核对选中项补入后的语义")
        if not card_kind and not isinstance(raw_member, str):
            raise ConditionError("旧列表成员缺少卡牌类型")
        return f"any({seq}, {predicate})", [*guards, *external]

    def boolean(self, node, invert=False):
        kind, *parts = node
        if kind == "not":
            return self.boolean(parts[0], not invert)
        if kind in ("and", "or"):
            connective = {"and": "or", "or": "and"}[kind] if invert else kind
            children = [self.boolean(child, invert) for child in parts]
            return children[0] if children[0] == children[1] else f"({f' {connective} '.join(children)})"
        if kind == "literal" and type(parts[0]) is bool:
            return "0 == 0" if parts[0] != invert else "0 != 0"
        if kind == "path":
            text, guards = self.value(node)
            return _guarded(("not " if invert else "") + text, guards)
        left, right = parts
        if kind in ("is", "has") and left[0] == "path" and left[1][-1] in ("阵容名", "当前阵容", "使用阵容"):
            value, guards = self.value(left)
            raw = right[1]
            if not isinstance(raw, str):
                raise ConditionError("旧阵容比较需要名称")
            return _guarded(f'{value} {"!=" if invert else "=="} {literal(lineup_name(raw))}', guards)
        if kind == "has" or kind == "in" and self.is_list(right):
            text, guards = self.membership(left if kind == "has" else right, right if kind == "has" else left)
            return _guarded(("not " if invert else "") + text, guards)
        if left[0] == "path" and left[1][-1] == "伤害类型":
            raise ConditionError("待核实等价的官方伤害类型标签")
        a, a_guards = self.value(left, name=bool(self.entity(left) and left[0] == "path"))
        b, b_guards = self.value(right, name=bool(self.entity(right) and right[0] == "path"))
        guards = [*a_guards, *b_guards]
        comparison = "==" if kind == "is" else kind
        prefix = "not " if invert else ""
        if kind == "is" and left[0] == "path" and self.entity(left) == "单位" and self.entity(right):
            owner, _ = self.value(left)
            other_kind = self.entity(right)
            typecheck = f'{owner}.卡牌类型 == {literal(_card_kind(other_kind))}'
            return _guarded(f"{prefix}({typecheck} and {a} == {b})", guards)
        return _guarded(f"{prefix}({a} {comparison} {b})" if invert else f"{a} {comparison} {b}", guards)

    def expression(self, source):
        return self.boolean(self.parse(source)) if source.strip() else ""

    def template(self, source):
        def slot(match):
            node = self.parse(match[1])
            value, _ = self.value(node, name=bool(self.entity(node)))
            return "{{" + value + "}}"

        return LEGACY_SLOT.sub(slot, source)


def _cards(value, typ):
    if not isinstance(value, list):
        return _UNKNOWN
    return [_card(row, typ) for row in value]


def _card(value, typ=None):
    if isinstance(value, str):
        value = {"名称": value}
    if not isinstance(value, dict):
        return _UNKNOWN
    typ = value.get("卡牌类型", value.get("类型", typ))
    card = {RENAMES.get(key, key): val for key, val in value.items() if val is not None}
    if typ:
        card["卡牌类型"] = _card_kind(typ)
    if "装备列表" in card:
        card["装备列表"] = _cards(card["装备列表"], "装备")
    return card


def _old_lineup(value):
    if isinstance(value, dict):
        value = value.get("阵容名")
    if isinstance(value, list):
        names = list(dict.fromkeys(lineup_name(n) for n in value if isinstance(n, str)))
        return names[0] if len(names) == 1 else _UNKNOWN
    return lineup_name(value) if isinstance(value, str) else _UNKNOWN


def _player(value):
    if not isinstance(value, dict):
        return _UNKNOWN
    result = {RENAMES.get(key, key): val for key, val in value.items()
              if val is not None and key not in ("使用阵容", "当前阵容", "战场")}
    if "使用阵容" in value or "当前阵容" in value:
        result["阵容名称"] = _old_lineup(value.get("使用阵容", value.get("当前阵容")))
    if isinstance(value.get("战场"), list):
        board = _cards(value["战场"], "英雄")
        result["场上英雄列表"] = [row for row in board
                                  if row is _UNKNOWN or row.get("卡牌类型") == "英雄"]
        result["场上衍生物列表"] = [row for row in board
                                  if row is _UNKNOWN or row.get("卡牌类型") == "衍生物"]
    for key, typ in (("天赋列表", "天赋"), ("手牌列表", None)):
        if key in result:
            result[key] = _cards(result[key], typ)
    for key in ("主C", "最高等级英雄"):
        if key in result:
            result[key] = _card(result[key], "英雄")
    return result


def adapt(event, state, legacy_catalog=None):
    """Use v3's explicit counters and object identities without inventing cards."""
    source = _catalog(legacy_catalog)
    name = _event_name(event["事件"], source)
    target = TITLES.get(name, name)
    if target not in catalog()["events"]:
        return target, state
    definition = source["events"][name]["parameters"]
    args = event.get("参数", {})
    action = {}
    for index, field in enumerate(ARGS.get(target, ()), 1):
        key = f"arg{index}"
        if key not in args:
            continue
        val = args[key]
        kind = definition[key]
        if kind == "阵容":
            val = _old_lineup(val)
        elif kind.startswith("Array<"):
            member = kind[6:-1]
            val = _cards(val, None if "|" in member else member)
        elif kind in CARD_TYPES:
            val = _card(val, "英雄" if kind == "单位" else kind)
        action[field] = val
    if "目标" in action:
        target_card = action["目标"]
        if isinstance(target_card, dict):
            action["目标英雄"] = target_card if target_card.get("卡牌类型") == "英雄" else None
    if target.startswith("解释为何购买") and isinstance(action.get("候选列表"), list) and "选中" in action:
        action["候选列表"] = [action["选中"], *action["候选列表"]]
    game = state.get("对局", {})
    old_player = state.get("玩家", {})
    old_opponent = game.get("当前对手")
    player = _player(old_player)
    if isinstance(state.get("商店", {}).get("商店列表"), list):
        player["商店列表"] = _cards(state["商店"]["商店列表"], None)
    if target == "解释为何建议向某阵容发展":
        player.setdefault("阵容名称", "待识别")
    counts = {}
    for root, raw in (("我方", old_player), ("对手", old_opponent)):
        for old, new in (("场上英雄数", "场上英雄列表"), ("手牌数", "手牌列表")):
            value = raw.get(old) if isinstance(raw, dict) else None
            if type(value) is int:
                counts[(root, new)] = value
    return target, {"我方": player, "对手": _player(old_opponent), "对局": game, "动作": action,
                    "_legacy_counts": counts}
