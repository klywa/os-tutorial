"""Order matched rules by strict inclusion of their three-valued truth sets."""
from dataclasses import dataclass
from functools import lru_cache
import json

import z3

from . import _Evaluator, Value, _COMPARISONS


@dataclass
class Term:
    kind: str
    present: object
    value: object
    # Entity identity uses both the runtime type and the possibly missing name.
    tag: object = None
    named: object = None


class Model:
    def __init__(self, catalog):
        self.catalog = catalog
        self.ctx = z3.Context()
        self.solver = z3.Solver(ctx=self.ctx)
        self.true = z3.BoolVal(True, self.ctx)
        self.false = z3.BoolVal(False, self.ctx)
        self.paths = {}
        self.collections = {}

    def string(self, value):
        return z3.StringVal(value, self.ctx)

    def any(self, terms):
        return z3.Or(*terms) if terms else self.false

    def canonical(self, typ):
        return self.catalog["aliases"].get(typ, typ)

    def path(self, parts, typ, parent, field=None):
        if parts in self.paths:
            return self.paths[parts]
        symbol = ".".join(parts)
        known = z3.And(parent, z3.Bool(symbol + ":present", self.ctx))
        if typ.startswith("Array<"):
            term = Term(typ, known, symbol)
        elif typ in ("int", "number", "bool", "string"):
            constructor = {"int":z3.Int, "number":z3.Real, "bool":z3.Bool, "string":z3.String}[typ]
            term = Term(typ, known, constructor(symbol, self.ctx))
            enum = self.catalog.get("enums", {}).get(field)
            if enum:
                self.solver.add(z3.Implies(known, self.any([term.value == self.string(v) for v in enum])))
        else:
            alternatives = [self.canonical(t) for t in typ.split("|")]
            tag = self.string(alternatives[0])
            if len(alternatives) > 1:
                tag = z3.String(symbol + ":type", self.ctx)
                self.solver.add(self.any([tag == self.string(t) for t in alternatives]))
            name = self.path(parts + ("名称",), "string", known)
            term = Term("entity", known, name.value, tag, name.present)
        self.paths[parts] = term
        return term

    def boolean(self, yes, no):
        return Term("bool", z3.Or(yes,no), yes)

    def literal(self, value):
        if isinstance(value, list):
            return Term("list",self.true,[self.literal(v) for v in value])
        if isinstance(value, dict):
            return Term("entity",self.true,self.string(value.get("名称",value.get("name"))),
                        self.string(self.canonical(value["类型"])), self.true)
        if isinstance(value, str):
            return Term("string",self.true,self.string(value))
        if isinstance(value, bool):
            return Term("bool",self.true,z3.BoolVal(value,self.ctx))
        return Term("number",self.true,z3.RealVal(str(value),self.ctx))

    def equal(self, a, b):
        both = z3.And(a.present,b.present)
        different = a.tag != b.tag if a.tag is not None and b.tag is not None else self.false
        names = z3.And(a.named if a.tag is not None else self.true,
                       b.named if b.tag is not None else self.true)
        return Term("bool",z3.And(both,z3.Or(different,names)),
                    z3.And(z3.Not(different),a.value == b.value))

    def membership(self, seq, item):
        if seq.kind == "list":
            yes, unknown = [], []
            for element in seq.value:
                comparison = self.equal(element,item)
                yes.append(z3.And(comparison.present,comparison.value))
                unknown.append(z3.Not(comparison.present))
            hit = self.any(yes)
            return self.boolean(hit,z3.And(z3.Not(hit),z3.Not(self.any(unknown))))

        # A list is observed only through membership. For each possible element
        # type model its keys, whether any element exists, and any missing name.
        yes, uncertain = [], []
        types = [self.canonical(t) for t in seq.kind[6:-1].split("|")]
        for typ in types:
            key = (seq.value,typ)
            if key not in self.collections:
                sort = {"int":z3.RealSort,"number":z3.RealSort,"bool":z3.BoolSort}.get(typ,z3.StringSort)
                prefix = seq.value + ":" + typ
                present = z3.Bool(prefix+":nonempty",self.ctx)
                partial = z3.Bool(prefix+":missing",self.ctx)
                contains = z3.Function(prefix+":contains",sort(self.ctx),z3.BoolSort(self.ctx))
                self.collections[key] = present,partial,contains
                self.solver.add(z3.Implies(partial,present))
                if typ=="bool":
                    self.solver.add(present == z3.Or(partial,contains(self.true),contains(self.false)))
            present,partial,contains = self.collections[key]
            compatible = item.tag == self.string(typ) if item.tag is not None else self.true
            known = item.named if item.tag is not None else item.present
            hit = contains(item.value)
            if typ == "int" and z3.is_real(item.value):
                hit = z3.And(z3.IsInt(item.value), hit)
            self.solver.add(z3.Implies(hit,present))
            yes.append(z3.And(compatible,known,hit))
            uncertain.append(z3.And(compatible,z3.Or(partial,z3.And(present,z3.Not(known)))))
        # An unknown union element can match any of the possible types.
        null_element = z3.Bool(seq.value+":unknown-element", self.ctx)
        uncertain.append(null_element)
        if len(types)>1 and item.tag is not None:
            uncertain.append(z3.And(z3.Not(item.present),self.any(
                [self.collections[(seq.value,t)][0] for t in types])))
        hit = self.any(yes)
        return self.boolean(z3.And(seq.present,hit),
                            z3.And(seq.present,z3.Not(hit),z3.Not(self.any(uncertain))))

    def possible(self, condition):
        self.solver.push()
        try:
            self.solver.add(condition)
            return self.solver.check()
        finally:
            self.solver.pop()


class SymbolicExpression(_Evaluator):
    """Share tokenization, precedence, parentheses and literal syntax with evaluation."""
    def __init__(self, source, event, model):
        super().__init__(source,event,{}, {},model.catalog)
        self.model = model

    def path(self, root):
        typ = self.params.get(root) or self.catalog["roots"][root]
        parts = (root,)
        term = self.model.path(parts,typ,self.model.true)
        while self.accept("."):
            attr = self.take("id")
            if attr == "求和" and self.token[0] == "(":
                field, typ = self.sum_field(typ)
                parts += (f"求和({field})",)
                term = self.model.path(parts, typ, term.present)
                continue
            attr = "名称" if attr == "name" else attr
            owners = typ[6:-1] if attr == "标签" and typ.startswith("Array<") else typ
            owner = self.model.canonical(owners.split("|")[0])
            typ = self.catalog["types"][owner][attr]
            parts += (attr,)
            term = self.model.path(parts,typ,term.present,owner+"."+attr)
        return term

    def primary(self):
        term = super().primary()
        return self.model.literal(term.value) if isinstance(term,Value) else term

    def literal(self, raw):
        return self.model.literal(raw)

    def logic(self, op, left, right=None):
        yes = z3.And(left.present,left.value)
        no = z3.And(left.present,z3.Not(left.value))
        if op == "not":
            return self.model.boolean(no,yes)
        other_yes = z3.And(right.present,right.value)
        other_no = z3.And(right.present,z3.Not(right.value))
        if op == "and":
            return self.model.boolean(z3.And(yes,other_yes),z3.Or(no,other_no))
        return self.model.boolean(z3.Or(yes,other_yes),z3.And(no,other_no))

    def compare(self, op, left, right):
        if op == "in":
            return self.model.membership(right,left)
        if op == "has":
            return self.model.membership(left,right)
        if op == "is":
            return self.model.equal(left,right)
        return Term("bool",z3.And(left.present,right.present),_COMPARISONS[op](left.value,right.value))

    def matches(self):
        if self.token[0] == "end":
            return self.model.true
        rule = self.disjunction()
        return z3.And(rule.present,rule.value)


@lru_cache(maxsize=128)
def _dominated(expressions, event, catalog_json):
    model = Model(json.loads(catalog_json))
    formulas = {expr:SymbolicExpression(expr,event,model).matches() for expr in expressions}
    dominated = set()
    items = list(formulas.items())
    for i,(a,left) in enumerate(items):
        for b,right in items[i+1:]:
            left_only = model.possible(z3.And(left,z3.Not(right)))
            right_only = model.possible(z3.And(right,z3.Not(left)))
            if left_only == z3.unsat and right_only == z3.sat:
                dominated.add(b)
            elif right_only == z3.unsat and left_only == z3.sat:
                dominated.add(a)
    return frozenset(dominated)


def most_specific(groups, event, catalog):
    expressions = tuple(sorted({g.get("expression","").strip() for g in groups}))
    relevant = {**catalog,"events":{event:catalog["events"][event]}}
    relevant.pop("card_tags", None)
    dominated = _dominated(expressions,event,json.dumps(relevant,sort_keys=True,ensure_ascii=False))
    return [g for g in groups if g.get("expression","").strip() not in dominated]
