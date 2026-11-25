package condition

import (
	"encoding/json"
	"math/big"
	"strings"
	"unicode"
	"unicode/utf8"
)

type parser struct {
	rest                 string
	total, offset, depth int
	c                    *Catalog
	def                  EventDefinition
	args, state          map[string]any
}

const maxNesting = 64

func (p *parser) enter() {
	p.depth++
	if p.depth > maxNesting {
		reject("expression nesting exceeds %d", maxNesting)
	}
}

// peek leaves literal contents to the JSON decoder, including escapes and nested arrays.
func (p *parser) peek() string {
	s := strings.TrimLeftFunc(p.rest, unicode.IsSpace)
	p.rest = s
	if s == "" {
		return ""
	}
	for _, tok := range []string{"<=", ">=", "=="} {
		if strings.HasPrefix(s, tok) {
			return tok
		}
	}
	r, n := utf8.DecodeRuneInString(s)
	if unicode.IsLetter(r) || r == '_' {
		for n < len(s) {
			r, k := utf8.DecodeRuneInString(s[n:])
			if !unicode.IsLetter(r) && !unicode.IsDigit(r) && r != '_' {
				break
			}
			n += k
		}
	}
	return s[:n]
}
func (p *parser) take(tok string) bool {
	if p.peek() != tok {
		return false
	}
	p.offset = p.total - len(p.rest)
	p.rest = p.rest[len(tok):]
	return true
}
func priority(op string) int {
	switch op {
	case "or":
		return 1
	case "and":
		return 2
	case "<", "<=", "==", ">=", ">", "is", "in", "has":
		return 4
	}
	return 0
}
func (p *parser) expr(min int) value {
	var left value
	if min <= 3 && p.take("not") {
		p.enter()
		v := p.expr(3)
		p.depth--
		requireBool(v)
		left = scalar("bool", nil)
		if v.raw != nil {
			left.raw = !v.raw.(bool)
		}
	} else {
		left = p.primary()
	}
	for {
		op := p.peek()
		level := priority(op)
		if level < min {
			break
		}
		p.take(op)
		right := p.expr(level + 1)
		left = p.c.apply(left, op, right)
		if level == 4 && priority(p.peek()) == 4 {
			p.offset = p.total - len(p.rest)
			reject("comparisons cannot be chained")
		}
	}
	return left
}
func (p *parser) primary() value {
	tok := p.peek()
	p.offset = p.total - len(p.rest)
	if tok == "" {
		reject("expected operand")
	}
	if p.take("(") {
		p.enter()
		v := p.expr(1)
		p.depth--
		if !p.take(")") {
			p.offset = p.total - len(p.rest)
			reject("expected )")
		}
		return v
	}
	if strings.ContainsAny(tok[:1], "\"[{-0123456789") || tok == "true" || tok == "false" {
		return p.jsonLiteral()
	}
	p.take(tok)
	t, ok := p.def.Parameters[tok]
	raw := p.args[tok]
	if !ok {
		t, ok = p.c.Roots[tok]
		raw = p.state[tok]
	}
	if !ok {
		reject("unknown variable %q", tok)
	}
	v := p.c.read(t, raw)
	for p.take(".") {
		field := p.peek()
		if field == "" {
			p.offset = p.total - len(p.rest)
			reject("expected field")
		}
		p.take(field)
		if field == "计数" && p.take("(") {
			v = p.count(v)
			continue
		}
		if field == "求和" && p.take("(") {
			v = p.sumField(v)
			continue
		}
		if field == "name" {
			field = "名称"
		}
		t = ""
		domain := v.domain()
		if element, list := elements(domain); list && field == "标签" {
			domain = element
		}
		for _, owner := range strings.Split(domain, "|") {
			option, exists := p.c.Types[p.c.canonical(owner)][field]
			if !exists || (t != "" && option != t) {
				reject("unknown or ambiguous field %s.%s", v.domain(), field)
			}
			t = option
		}
		raw = nil
		switch x := v.raw.(type) {
		case map[string]any:
			var present bool
			raw, present = x[field]
			if !present && field == "名称" {
				raw = x["name"]
			}
		case string:
			if field == "名称" {
				raw = x
			}
		}
		if field == "标签" {
			raw = p.c.cardTags(v)
		}
		key := v.typ + "." + field
		if field == "标签" {
			key = p.c.canonical(strings.Split(domain, "|")[0]) + "." + field
		}
		v = p.c.read(t, raw)
		v.field = key
	}
	return v
}

func (p *parser) jsonLiteral() value {
	d := json.NewDecoder(strings.NewReader(p.rest))
	d.UseNumber()
	var x any
	if err := d.Decode(&x); err != nil {
		reject("invalid JSON literal: %v", err)
	}
	p.rest = p.rest[d.InputOffset():]
	return p.c.literal(x, 0)
}

func (p *parser) sumField(v value) value {
	element, ok := elements(v.domain())
	if !ok {
		reject("sum requires an array")
	}
	field := p.peek()
	if field == "" || !p.take(field) || !p.take(")") {
		reject("sum requires one numeric field")
	}
	typ := "int"
	for _, owner := range strings.Split(element, "|") {
		fieldType := p.c.Types[p.c.canonical(owner)][field]
		if !numeric(fieldType) {
			reject("sum requires numeric field %s on every element type", field)
		}
		if fieldType == "number" {
			typ = "number"
		}
	}
	if v.raw == nil {
		return scalar(typ, nil)
	}
	total := new(big.Rat)
	for _, item := range v.raw.([]value) {
		obj, _ := item.raw.(map[string]any)
		if obj[field] == nil {
			return scalar(typ, nil)
		}
		n := p.c.read(typ, obj[field])
		total.Add(total, n.raw.(*big.Rat))
	}
	return scalar(typ, total)
}
