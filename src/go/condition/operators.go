package condition

import (
	"math/big"
	"slices"
	"strings"
)

func requireBool(v value) {
	if v.typ != "bool" {
		reject("expected bool, got %s", v.typ)
	}
}
func logical(a value, op string, b value) value {
	requireBool(a)
	requireBool(b)
	decisive := op == "or"
	if a.raw == decisive || b.raw == decisive {
		return scalar("bool", decisive)
	}
	if a.raw == nil || b.raw == nil {
		return scalar("bool", nil)
	}
	return scalar("bool", !decisive)
}

func (c *Catalog) apply(a value, op string, b value) value {
	for _, operand := range []value{a, b} {
		if allowed, ok := c.Operations[operand.field]; ok && !slices.Contains(allowed, op) {
			reject("operator %s unavailable for %s", op, operand.field)
		}
	}
	switch op {
	case "or", "and":
		return logical(a, op, b)
	case "has":
		return c.membership(a, b)
	case "in":
		return c.membership(b, a)
	case "is":
		if a.literalString {
			c.checkEnum(b.field, a.raw)
		}
		if b.literalString {
			c.checkEnum(a.field, b.raw)
		}
		if (a.typ == "string" || c.entity(a.typ) || strings.Contains(a.typ, "|")) && c.compatible(a.domain(), b.domain()) {
			return c.equal(a, b)
		}
	case "==":
		if a.typ == "bool" && b.typ == "bool" {
			return c.equal(a, b)
		}
	}
	if op != "is" && numeric(a.typ) && numeric(b.typ) {
		if a.raw == nil || b.raw == nil {
			return scalar("bool", nil)
		}
		cmp := a.raw.(*big.Rat).Cmp(b.raw.(*big.Rat))
		switch op {
		case "<":
			return scalar("bool", cmp < 0)
		case "<=":
			return scalar("bool", cmp <= 0)
		case "==":
			return scalar("bool", cmp == 0)
		case ">=":
			return scalar("bool", cmp >= 0)
		case ">":
			return scalar("bool", cmp > 0)
		}
	}
	reject("cannot apply %s to %s and %s", op, a.typ, b.typ)
	return value{}
}
func (c *Catalog) entity(t string) bool { _, ok := c.Types[c.canonical(t)]; return ok }
func nameOf(v value) any {
	switch raw := v.raw.(type) {
	case string:
		return raw
	case map[string]any:
		name, ok := raw["名称"]
		if !ok {
			name = raw["name"]
		}
		if name != nil {
			if _, ok := name.(string); !ok {
				reject("名称 must be a string")
			}
		}
		return name
	}
	return nil
}
func (c *Catalog) equal(a, b value) value {
	if a.raw == nil || b.raw == nil {
		return scalar("bool", nil)
	}
	if numeric(a.typ) && numeric(b.typ) {
		return scalar("bool", a.raw.(*big.Rat).Cmp(b.raw.(*big.Rat)) == 0)
	}
	if a.typ == "bool" && b.typ == "bool" {
		return scalar("bool", a.raw == b.raw)
	}
	if c.entity(a.typ) && c.entity(b.typ) && a.typ != b.typ {
		return scalar("bool", false)
	}
	x, y := nameOf(a), nameOf(b)
	if x == nil || y == nil {
		return scalar("bool", nil)
	}
	return scalar("bool", x == y)
}
func (c *Catalog) compatible(t, needle string) bool {
	if (strings.Contains(t, "|") && needle == "string") || (strings.Contains(needle, "|") && t == "string") {
		return false
	}
	for _, part := range strings.Split(t, "|") {
		part = c.canonical(part)
		for _, candidate := range strings.Split(needle, "|") {
			candidate = c.canonical(candidate)
			if part == candidate || part == "单位" && slices.Contains(c.UnitTypes, candidate) ||
				candidate == "单位" && slices.Contains(c.UnitTypes, part) ||
				numeric(part) && numeric(candidate) || c.entity(part) && candidate == "string" || part == "string" && c.entity(candidate) {
				return true
			}
		}
	}
	return false
}
func (c *Catalog) membership(list, needle value) value {
	typ, ok := elements(list.typ)
	if !ok {
		reject("membership needs an array, got %s", list.typ)
	}
	if _, array := elements(needle.typ); array {
		reject("membership needs a scalar")
	}
	if strings.Contains(typ, "|") && needle.typ == "string" {
		reject("mixed entity membership requires an explicit type")
	}
	if typ != "?" && !c.compatible(typ, needle.domain()) {
		reject("%s not applicable to %s", needle.typ, list.typ)
	}
	if list.raw == nil {
		return scalar("bool", nil)
	}
	var matched, unknown bool
	for _, item := range list.raw.([]value) {
		if item.literalString {
			c.checkEnum(needle.field, item.raw)
		}
		if typ == "?" && !c.compatible(item.domain(), needle.domain()) {
			if c.entity(item.typ) && c.entity(needle.typ) {
				continue
			}
			reject("incompatible list item %s for %s", item.typ, needle.typ)
		}
		v := c.equal(item, needle)
		matched = matched || v.raw == true
		unknown = unknown || v.raw == nil
	}
	if !matched && unknown {
		return scalar("bool", nil)
	}
	return scalar("bool", matched)
}
