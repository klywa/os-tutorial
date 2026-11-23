"""Check editorial limits for newly generated v3 groups before import."""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from src.python.condition import _Evaluator, _catalog, _event_name


_ARG = re.compile(r"(arg[1-9][0-9]*)(?:\s*\.\s*名称)?")
_FORM = re.compile(r"(arg[1-9][0-9]*)\s*\.\s*已觉醒")
_CONTEXT = ("context",)


def _name(value):
    if isinstance(value, dict):
        return value.get("名称", value.get("name"))
    return value if isinstance(value, str) else None


def _node(value):
    return getattr(value, "editorial_node", _CONTEXT)


class _ConditionShape(_Evaluator):
    """Reuse the formal parser while retaining identities and boolean structure."""

    def __init__(self, source, event_name, catalog):
        super().__init__(source, event_name, {}, {}, catalog)
        self.source = source

    def primary(self):
        kind, _, start = self.token
        value = super().primary()
        if kind == "id":
            path = self.source[start - 1:self.token[2] - 1].strip()
            arg = _ARG.fullmatch(path)
            if arg:
                value.editorial_arg = arg[1]
            form = _FORM.fullmatch(path)
            if form:
                value.editorial_node = ("form", form[1])
        elif kind in ("true", "false"):
            value.editorial_node = ("constant", value.value)
        return value

    def compare(self, op, left, right):
        result = super().compare(op, left, right)
        if op in ("is", "==") and "form" in (_node(left)[0], _node(right)[0]):
            if isinstance(right.value, bool):
                result.editorial_node = _node(left)
            elif isinstance(left.value, bool):
                result.editorial_node = _node(right)
        if op == "is" and getattr(right, "editorial_arg", None):
            left, right = right, left
        arg = getattr(left, "editorial_arg", None)
        if arg and op == "in" and right.types == ("Array<?>",):
            names = tuple(_name(item.value) for item in right.value)
            if names and all(names):
                result.editorial_node = ("identity", arg, frozenset(names))
        elif arg and op == "is" and _name(right.value):
            result.editorial_node = ("identity", arg, frozenset((_name(right.value),)))
        elif op in ("has", "in"):
            array, member = (left, right) if op == "has" else (right, left)
            candidate = getattr(array, "editorial_arg", None)
            selected_arg = getattr(member, "editorial_arg", None)
            if candidate and (_name(member.value) or selected_arg):
                result.editorial_node = ("candidate", candidate, _name(member.value), selected_arg)
        return result

    def logic(self, op, left, right=None):
        result = super().logic(op, left, right)
        result.editorial_node = (op, _node(left)) if op == "not" else (op, _node(left), _node(right))
        return result


def _branches(node, negated=False):
    kind, *parts = node
    if kind == "not":
        return _branches(parts[0], not negated)
    if kind in ("or", "and"):
        left, right = (_branches(part, negated) for part in parts)
        if (kind == "or") != negated:
            return left | right
        return {a | b for a in left for b in right}
    if kind == "candidate" and negated:
        node = _CONTEXT
    if kind == "identity" and negated:
        node = (kind, parts[0], frozenset())
    if kind == "constant":
        return {frozenset()} if parts[0] != negated else set()
    if node == _CONTEXT:
        return set()  # Only branches without a separate condition can be trivial.
    return {frozenset((node,))}


def trivial_condition(group, condition_catalog=None):
    event_name = group.get("event_name", "")
    if not event_name.startswith("解释为何"):
        return None
    scope = group.get("scope", {})
    if scope.get("player") or scope.get("lineup"):
        return None  # The independent review verifies that the binding has decision value.
    expression = group.get("expression", "")
    if not expression.strip():
        return "解释组缺少有局面依据的生效条件"
    catalog = _catalog(condition_catalog)
    shape = _ConditionShape(expression, _event_name(event_name, catalog), catalog)
    for branch in _branches(_node(shape.parse())):
        if not branch:
            return "解释组存在无局面限制的生效分支"
        identities = [term for term in branch if term[0] == "identity"]
        core_args = {term[1] for term in branch if term[0] in ("identity", "form")}
        if len(core_args) != 1:
            continue
        core_arg = next(iter(core_args))
        candidates = [term for term in branch if term[0] == "candidate"]
        if not candidates:
            return "生效分支只识别一个事件参数或限定其形态"
        positive_names = [set(term[2]) for term in identities if term[2]]
        names = set.intersection(*positive_names) if positive_names else set()
        if all(arg != core_arg and (reference == core_arg or bool(name) and names == {name})
               for _, arg, name, reference in candidates):
            return "生效分支仅重复确认候选列表含所选对象"
    return None


def _longest_slot_values(group, catalog, references, cases):
    from src.python.condition import (
        entity_utterance_references,
        evaluate_condition,
        literal_in_bindings,
        numeric_utterance_bindings,
        utterance_values,
    )

    expression = group.get("expression", "")
    event_name = group.get("event_name")
    literal_bindings = literal_in_bindings(expression, event_name, catalog)
    numeric_paths = set(numeric_utterance_bindings(expression, event_name, catalog))
    direct_paths = entity_utterance_references(references, event_name, catalog)
    longest = {path: max(values, key=len) for path, values in literal_bindings.items()}
    scope = group.get("scope", {})
    used_dynamic = (numeric_paths.intersection(references) | direct_paths) - longest.keys()
    if used_dynamic:
        for case in cases:
            event, state = case["event"], case["state"]
            player = state.get("玩家", {})
            if event.get("事件") != event_name or any(
                scope.get(key) is not None and scope[key] != player.get(field)
                for key, field in (("player", "使用棋手"), ("lineup", "使用阵容"))
            ):
                continue
            if not evaluate_condition(event, expression, state, catalog):
                continue
            values = utterance_values(expression, event, state, catalog, references=used_dynamic)
            for path in used_dynamic.intersection(values):
                longest[path] = max(longest.get(path, ""), values[path], key=len)
    for path in references:
        if path not in longest:
            if path in numeric_paths:
                raise ValueError(f"数字槽位 {{{path}}} 缺少实际命中本组的正例")
            if path in direct_paths:
                raise ValueError(f"实体槽位 {{{path}}} 缺少实际命中且有名称的正例")
            raise ValueError(f"槽位 {{{path}}} 缺少可用的绑定条件")
    return longest


def check(document, *, scenarios=()):
    from src.python.condition import render_bound_utterance, utterance_references

    if document.get("kind") != "speech-template-library" or document.get("schema_version") != 3:
        raise ValueError("请提供 v3 模板库 JSON")
    if not isinstance(document.get("groups"), list):
        raise ValueError("缺少模板组列表")
    cases_by_group = defaultdict(list)
    for case in scenarios:
        if case.get("kind") == "positive" and case.get("matches") is True:
            cases_by_group[tuple(case["group"])].append(case)
    for index, group in enumerate(document["groups"], 1):
        name = group.get("name") or str(index)
        for field in ("explanation_before", "explanation_source", "explanation_after"):
            value = group.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}：缺少 {field}")
        lines = group.get("utterances")
        if not isinstance(lines, list) or not lines:
            raise ValueError(f"{name}：至少需要一条可独立使用的话术")
        if any(not isinstance(line, str) or not line.strip() for line in lines):
            raise ValueError(f"{name}：每句须完整且不超过 30 字")
        try:
            problem = trivial_condition(group, document.get("condition_catalog"))
            if problem:
                raise ValueError(problem)
            references = dict.fromkeys(path for line in lines for path in utterance_references(line))
            values = _longest_slot_values(
                group, document.get("condition_catalog"), references,
                cases_by_group[(group.get("event_name"), group.get("name"))],
            ) if references else {}
            if any(len(render_bound_utterance(line, values)) > 30 for line in lines):
                raise ValueError("每句展开后须不超过 30 字")
        except ValueError as error:
            raise ValueError(f"{name}：{error}") from error
        if len({line.strip() for line in lines}) != len(lines):
            raise ValueError(f"{name}：组内有重复话术")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--scenarios", type=Path, help="含动态名称或数字槽位时提供实际命中各组的正例")
    args = parser.parse_args()
    try:
        document = json.loads(args.package.read_text(encoding="utf-8-sig"))
        scenarios = json.loads(args.scenarios.read_text(encoding="utf-8-sig")) if args.scenarios else []
        if not isinstance(scenarios, list):
            raise ValueError("核验用例须为数组")
        check(document, scenarios=scenarios)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(f"已检查 {len(document['groups'])} 个模板组")
