package condition

import (
	"encoding/json"
	"math/big"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"unicode"
)

type v04Registry struct {
	Roots         map[string]string
	Types         map[string]map[string]string
	Actions       map[string]map[string]string
	Events        map[string]struct{ Action string }
	HeroFields    []string          `json:"hero_fields"`
	HeroPaths     []string          `json:"hero_paths"`
	LineupAliases map[string]string `json:"lineup_aliases"`
}

type v04Node struct {
	op, kind string
	path     []string
	args     []*v04Node
	literal  any
}

// EvaluateConditionV04 validates the complete expression, then evaluates it with short-circuit logic.
func EvaluateConditionV04(eventName, expression string, stateJSON []byte) (result bool, err error) {
	_, source, _, _ := runtime.Caller(0)
	path := os.Getenv("WXQ_CONDITION_CATALOG_V04")
	if path == "" {
		if executable, e := os.Executable(); e == nil {
			candidate := filepath.Join(filepath.Dir(executable), "catalog-v04.json")
			if _, e := os.Stat(candidate); e == nil {
				path = candidate
			}
		}
	}
	if path == "" {
		path = filepath.Join(filepath.Dir(source), "..", "..", "condition", "catalog-v04.json")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return false, err
	}
	var catalog v04Registry
	if err = json.Unmarshal(data, &catalog); err != nil {
		return false, err
	}
	defer func() {
		if problem := recover(); problem != nil {
			if conditionError, ok := problem.(*ConditionError); ok {
				err = conditionError
			} else {
				panic(problem)
			}
		}
	}()
	definition, exists := catalog.Events[eventName]
	if !exists {
		reject("unknown v0.4 event %q", eventName)
	}
	state := decodeObject(stateJSON)
	v04NormalizeLineups(state, catalog.LineupAliases)
	if strings.TrimSpace(expression) == "" {
		return true, nil
	}
	if len([]rune(expression)) > 100000 {
		reject("v0.4 expression too long")
	}
	p := parser{rest: expression, total: len(expression)}
	node := v04Parse(&p, 1)
	if p.peek() != "" {
		reject("unexpected token %q", p.peek())
	}
	check := v04TypeCheck{catalog, catalog.Actions[definition.Action]}
	if check.kind(node, nil, "") != "bool" {
		reject("condition must be boolean")
	}
	result, _ = v04Value(node, state, nil).(bool)
	return result, nil
}

func v04NormalizeLineups(value any, aliases map[string]string) {
	switch object := value.(type) {
	case map[string]any:
		for key, item := range object {
			if name, ok := item.(string); ok && (key == "阵容名称" || key == "阵容") {
				if alias, known := aliases[name]; known {
					object[key] = alias
				}
			} else {
				v04NormalizeLineups(item, aliases)
			}
		}
	case []any:
		for _, item := range object {
			v04NormalizeLineups(item, aliases)
		}
	}
}

func v04Operator(p *parser) (string, int) {
	op := p.peek()
	switch {
	case strings.HasPrefix(p.rest, "!="):
		return "!=", 2
	case op == "not":
		next := strings.TrimLeftFunc(p.rest[3:], unicode.IsSpace)
		probe := parser{rest: next}
		if probe.peek() == "in" {
			return "not in", len(p.rest) - len(next) + 2
		}
	}
	if op == "is" || op == "has" {
		return "", 0
	}
	return op, len(op)
}

func v04Parse(p *parser, minimum int) *v04Node {
	p.enter()
	defer func() { p.depth-- }()
	var left *v04Node
	if minimum <= 3 && p.take("not") {
		left = &v04Node{op: "not", args: []*v04Node{v04Parse(p, 3)}}
	} else {
		left = v04Primary(p)
	}
	for {
		op, size := v04Operator(p)
		level := priority(op)
		if op == "!=" || op == "not in" {
			level = 4
		}
		if level < minimum {
			return left
		}
		p.rest = p.rest[size:]
		left = &v04Node{op: op, args: []*v04Node{left, v04Parse(p, level+1)}}
		if next, _ := v04Operator(p); level == 4 &&
			(priority(next) == 4 || next == "!=" || next == "not in") {
			reject("comparisons cannot be chained")
		}
	}
}

func v04Identifier(p *parser) string {
	word := p.peek()
	if word == "" || !unicode.IsLetter([]rune(word)[0]) {
		reject("expected identifier")
	}
	p.take(word)
	return word
}

func v04Primary(p *parser) *v04Node {
	if p.take("(") {
		node := v04Parse(p, 1)
		if !p.take(")") {
			reject("expected )")
		}
		return node
	}
	if p.take("nil") {
		return &v04Node{kind: "nil"}
	}
	token := p.peek()
	if token != "" && strings.ContainsAny(token[:1], "\"[-0123456789") {
		decoder := json.NewDecoder(strings.NewReader(p.rest))
		decoder.UseNumber()
		var raw any
		if decoder.Decode(&raw) != nil {
			reject("invalid literal")
		}
		p.rest = p.rest[decoder.InputOffset():]
		node := &v04Node{literal: raw}
		switch value := raw.(type) {
		case json.Number:
			number, ok := new(big.Int).SetString(string(value), 10)
			if !ok {
				reject("expected decimal integer")
			}
			node.kind, node.literal = "int", number
		case string:
			node.kind = "string"
		case []any:
			for _, member := range value {
				if _, ok := member.(string); !ok {
					reject("list literals must contain strings")
				}
			}
			node.kind = "Array<string>"
		default:
			reject("invalid literal")
		}
		return node
	}
	if p.take(".") {
		node := &v04Node{path: []string{"#", v04Identifier(p)}}
		for p.take(".") {
			node.path = append(node.path, v04Identifier(p))
		}
		return node
	}
	root := v04Identifier(p)
	if p.take("(") {
		node := &v04Node{op: root, args: []*v04Node{v04Parse(p, 1)}}
		for p.take(",") {
			node.args = append(node.args, v04Parse(p, 1))
		}
		if !p.take(")") {
			reject("expected )")
		}
		return node
	}
	path := []string{root}
	for p.take(".") {
		path = append(path, v04Identifier(p))
	}
	return &v04Node{path: path}
}

func v04Facts(node *v04Node, truth bool, into map[string]bool) {
	switch node.op {
	case "and", "or":
		if (node.op == "and") == truth {
			v04Facts(node.args[0], truth, into)
			v04Facts(node.args[1], truth, into)
		}
	case "not":
		v04Facts(node.args[0], !truth, into)
	case "!=", "==":
		path, right := node.args[0].path, node.args[1]
		if (node.op == "!=") == truth && right.kind == "nil" && len(path) != 0 {
			into[strings.Join(path, ".")] = true
		}
		if (node.op == "==") == truth && right.kind == "string" && right.literal == "英雄" && len(path) > 1 && path[len(path)-1] == "卡牌类型" {
			into[strings.Join(path[:len(path)-1], ".")+".#hero"] = true
		}
	}
}

type v04TypeCheck struct {
	catalog v04Registry
	action  map[string]string
}

func (v v04TypeCheck) pathType(node *v04Node, guards map[string]bool, item string, nilCheck bool) string {
	root := node.path[0]
	kind := v.catalog.Roots[root]
	if root == "#" {
		kind = item
		if item == "英雄元素" {
			kind = "卡牌"
		}
	}
	for i, field := range node.path[1:] {
		prefix := strings.Join(node.path[:i+1], ".")
		if strings.HasSuffix(kind, "?") && !guards[prefix] {
			reject("missing nil guard for %s", prefix)
		}
		table := v.catalog.Types[strings.TrimSuffix(kind, "?")]
		if strings.TrimSuffix(kind, "?") == "卡牌" && slices.Contains(v.catalog.HeroFields, field) &&
			!slices.Contains(v.catalog.HeroPaths, node.path[i]) && !(prefix == "#" && item == "英雄元素") && !guards[prefix+".#hero"] {
			reject("missing hero type guard for %s.%s", prefix, field)
		}
		if kind == "动作" {
			table = v.action
		}
		kind = table[field]
	}
	if kind == "" {
		reject("unknown v0.4 path %s", strings.Join(node.path, "."))
	}
	if !nilCheck && guards[strings.Join(node.path, ".")] {
		kind = strings.TrimSuffix(kind, "?")
	}
	if item != "" && root != "#" && !nilCheck && !v04Scalar(kind) {
		reject("predicate can only reference outer scalars")
	}
	return kind
}

func v04Scalar(kind string) bool { return kind == "string" || kind == "int" || kind == "bool" }

func (v v04TypeCheck) kind(node *v04Node, guards map[string]bool, item string) string {
	if len(node.path) != 0 {
		return v.pathType(node, guards, item, false)
	}
	if node.kind != "" {
		if node.kind == "nil" {
			reject("nil requires an optional path comparison")
		}
		return node.kind
	}
	args := node.args
	switch node.op {
	case "not", "and", "or":
		a := v.kind(args[0], guards, item)
		if len(args) == 2 {
			next := make(map[string]bool, len(guards)+1)
			for path := range guards {
				next[path] = true
			}
			v04Facts(args[0], node.op == "and", next)
			if v.kind(args[1], next, item) != "bool" {
				reject("expected boolean operand")
			}
		}
		if a != "bool" {
			reject("expected boolean operand")
		}
		return "bool"
	case "==", "!=", "<", "<=", ">", ">=", "in", "not in":
		if args[1].kind == "nil" {
			if (node.op != "==" && node.op != "!=") || len(args[0].path) == 0 ||
				!strings.HasSuffix(v.pathType(args[0], guards, item, true), "?") {
				reject("nil requires an optional path comparison")
			}
			return "bool"
		}
		a, b := v.kind(args[0], guards, item), v.kind(args[1], guards, item)
		switch node.op {
		case "in", "not in":
			if a == "string" && b == "Array<string>" {
				return "bool"
			}
		case "==", "!=":
			if a == b && v04Scalar(a) {
				return "bool"
			}
		default:
			if a == "int" && b == "int" {
				return "bool"
			}
		}
	case "any", "all", "none", "count", "sum", "len", "filter":
		arity := 2
		if node.op == "len" {
			arity = 1
		}
		if len(args) != arity || item != "" {
			reject("wrong function arity or nested predicate")
		}
		list := v.kind(args[0], guards, "")
		member, isList := elements(list)
		if !isList {
			reject("function needs a list")
		}
		if node.op == "len" {
			return "int"
		}
		source := args[0]
		for source.op == "filter" {
			source = source.args[0]
		}
		if len(source.path) > 1 && source.path[len(source.path)-1] == "场上英雄列表" {
			member = "英雄元素"
		}
		kind := v.kind(args[1], guards, member)
		if node.op == "sum" {
			if kind == "int" && len(args[1].path) > 1 && args[1].path[0] == "#" {
				return "int"
			}
		} else if kind == "bool" {
			switch node.op {
			case "count":
				return "int"
			case "filter":
				return list
			default:
				return "bool"
			}
		}
	}
	reject("invalid v0.4 operator, function or operand: %s", node.op)
	return ""
}

type v04Missing struct{}

func v04Read(path []string, state map[string]any, item any) any {
	var value any = state
	if path[0] == "#" {
		value, path = item, path[1:]
	}
	for _, field := range path {
		if value == nil {
			reject("cannot read a nil object")
		}
		object, ok := value.(map[string]any)
		if !ok {
			return v04Missing{}
		}
		value, ok = object[field]
		if !ok {
			return v04Missing{}
		}
	}
	if raw, ok := value.(json.Number); ok {
		if integer, valid := new(big.Int).SetString(string(raw), 10); valid {
			return integer
		}
		return v04Missing{}
	}
	return value
}

func v04Value(node *v04Node, state map[string]any, item any) any {
	if len(node.path) > 0 {
		return v04Read(node.path, state, item)
	}
	if node.kind != "" {
		return node.literal
	}
	a := v04Value(node.args[0], state, item)
	switch node.op {
	case "not":
		if value, ok := a.(bool); ok {
			return !value
		}
		return v04Missing{}
	case "and", "or":
		decisive := node.op == "or"
		if a == decisive {
			return decisive
		}
		b := v04Value(node.args[1], state, item)
		if b == decisive {
			return decisive
		}
		if a == !decisive && b == !decisive {
			return !decisive
		}
		return v04Missing{}
	case "==", "!=", "<", "<=", ">", ">=", "in", "not in":
		return v04Compare(a, v04Value(node.args[1], state, item), node.op)
	default:
		return v04Aggregate(node, state, a)
	}
}

func v04Compare(a, b any, op string) any {
	if a == (v04Missing{}) || b == (v04Missing{}) {
		return v04Missing{}
	}
	if b == nil {
		return (op == "==") == (a == nil)
	}
	if op == "in" || op == "not in" {
		needle, text := a.(string)
		values, ok := b.([]any)
		if !ok || !text {
			return v04Missing{}
		}
		unknown := false
		for _, member := range values {
			value, known := member.(string)
			if known && value == needle {
				return op == "in"
			}
			unknown = unknown || !known
		}
		if unknown {
			return v04Missing{}
		}
		return op == "not in"
	}
	if x, ok := a.(*big.Int); ok {
		y, ok := b.(*big.Int)
		if !ok {
			return v04Missing{}
		}
		n := x.Cmp(y)
		return map[string]bool{"==": n == 0, "!=": n != 0, "<": n < 0, "<=": n <= 0, ">": n > 0, ">=": n >= 0}[op]
	}
	equal := false
	switch x := a.(type) {
	case string:
		y, ok := b.(string)
		if !ok {
			return v04Missing{}
		}
		equal = x == y
	case bool:
		y, ok := b.(bool)
		if !ok {
			return v04Missing{}
		}
		equal = x == y
	default:
		return v04Missing{}
	}
	return (op == "==") == equal
}

func v04Aggregate(node *v04Node, state map[string]any, raw any) any {
	list, ok := raw.([]any)
	if !ok {
		return v04Missing{}
	}
	if node.op == "len" {
		return big.NewInt(int64(len(list)))
	}
	var total int64
	sum := new(big.Int)
	filtered := []any{}
	unknown := false
	for _, member := range list {
		value := v04Value(node.args[1], state, member)
		if node.op == "sum" {
			number, ok := value.(*big.Int)
			if !ok {
				return v04Missing{}
			}
			sum.Add(sum, number)
			continue
		}
		matched, known := value.(bool)
		unknown = unknown || !known
		if !known {
			continue
		}
		if node.op == "all" && !matched || node.op == "none" && matched {
			return false
		}
		if matched {
			if node.op == "any" {
				return true
			}
			total++
			filtered = append(filtered, member)
		}
	}
	if unknown {
		return v04Missing{}
	}
	switch node.op {
	case "count":
		return big.NewInt(total)
	case "sum":
		return sum
	case "filter":
		return filtered
	default:
		return node.op != "any"
	}
}
