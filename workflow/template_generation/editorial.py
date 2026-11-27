"""Workflow copy of the project editorial checks for v0.4 groups."""
import ast
from src.python.condition.v04 import compile_expression, compile_template, render_compiled, validate_key


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


def check_group(group, positive_states):
    event = group["event_name"]
    key = validate_key(event, group["extra_key"])
    expression = compile_expression(event, group["expression"]).node
    scope = group.get("scope", {})
    factions = {"三分之地", "大河流域", "逐鹿", "河洛", "日落海", "建木", "无阵营"}
    for node in ast.walk(expression) if expression else ():
        if not isinstance(node, ast.Compare):
            continue
        values = [node.left, *node.comparators]
        if any(isinstance(value, ast.Attribute) and value.attr == "阵营" for value in values):
            names = (literal.value for value in values for literal in ast.walk(value)
                     if isinstance(literal, ast.Constant) and isinstance(literal.value, str))
            if any(name not in factions for name in names):
                raise ValueError(f"{group['name']}：条件中的阵营须使用正式全称")
    fixed_equipment = event in {"解释为何穿戴装备", "解释为何铸造装备", "解释为何转移装备"} and key[-1] != "*"
    fixed_recipient = fixed_equipment and key[0] != "*"
    fixed_effect = event in {"解释为何对目标使用效果牌", "解释为何对目标使用棋手技能"} and key[0] != "*"

    def action_field(node, field):
        return (isinstance(node, ast.Attribute) and node.attr == field
                and isinstance(node.value, ast.Name) and node.value.id == "动作")

    def recipient_path(node):
        return isinstance(node, ast.Attribute) and action_field(node.value, "目标英雄")

    def recipient_fact(node):
        if not (fixed_equipment or fixed_effect):
            return False
        props = {"装备列表", "等级", "品阶", "已觉醒", "觉醒进度", "阵营",
                 "关键词", "标签", "英雄阵容定位"}
        def observed(part):
            return recipient_path(part) and part.attr in props
        if observed(node) and node.attr == "已觉醒":
            return True
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return any(isinstance(child, ast.Constant) and child.value is not None for child in ast.walk(node)) and any(
                observed(child) for child in ast.walk(node))
        return (isinstance(node, ast.Call) and len(node.args) == 2 and observed(node.args[0])
                and any(isinstance(child, ast.Constant) for child in ast.walk(node.args[1])))

    def game_context(node, negated=False):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return game_context(node.operand, not negated)
        if isinstance(node, ast.BoolOp):
            combine = any if isinstance(node.op, ast.And) != negated else all
            return combine(game_context(child, negated) for child in node.values)
        if node is None:
            return False
        if any(isinstance(child, ast.Name) and child.id in {"我方", "对手", "对局"}
               for child in ast.walk(node)):
            return True
        if recipient_fact(node):
            return True
        if negated or not isinstance(node, ast.Compare) or len(node.ops) != 1:
            return False
        op, other = node.ops[0], node.comparators[0]
        if (event == "解释为何合成英雄" and action_field(node.left, "合成后等级")
                and isinstance(op, (ast.Eq, ast.Gt, ast.GtE))
                and isinstance(other, ast.Constant) and type(other.value) is int):
            return True
        # A named equipment and a recipient restriction are independent facts.
        if not fixed_equipment:
            return False
        if isinstance(op, ast.Eq):
            return ((recipient_path(node.left) and isinstance(other, ast.Constant)) or
                    (isinstance(node.left, ast.Constant) and recipient_path(other)))
        return (isinstance(op, ast.In) and recipient_path(node.left)
                and isinstance(other, ast.List) and bool(other.elts))

    merge_awakening = event == "解释为何合成英雄" and has_awakening_guard(group["expression"])
    if not (scope.get("player") or scope.get("lineup") or fixed_recipient or merge_awakening
            or game_context(expression)):
        raise ValueError(f"{group['name']}：有生效分支缺少局面依据")
    texts = [row["text"] for row in group["utterances"]]
    if not texts or len(texts) != len(set(texts)) or any(not text.strip() for text in texts):
        raise ValueError(f"{group['name']}：话术为空或有重复")
    vague_references = ("这件装备", "那件装备", "这个装备", "该装备", "此装备", "这些装备",
                        "这张牌", "那张牌", "该卡牌", "这个英雄", "那个英雄", "唯一最近")
    for text in texts:
        if any(term in text for term in vague_references):
            raise ValueError(f"{group['name']}：含糊指代或禁用措辞须改为明确名称或正式槽位：{text}")
        parts = compile_template(event, text)
        length = sum(len("".join(part.split())) if isinstance(part, str) else 4 for part in parts)
        if length > 30:
            raise ValueError(f"{group['name']}：每句须不超过 30 字，槽位各计 4 字")
        if len(parts) > 1 and not any(render_compiled(parts, state) is not None for state in positive_states):
            raise ValueError(f"{group['name']}：槽位需要可播正例")
