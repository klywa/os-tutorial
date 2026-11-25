package condition

import (
	"math/big"
	"slices"
	"strings"
)

func (p *parser) count(array value) value {
	element, ok := elements(array.domain())
	if !ok {
		reject("count requires an array")
	}
	var match func(value) any
	if !p.take(")") {
		field := p.peek()
		if (element != "单位" && element != "英雄") || !slices.Contains([]string{"英雄", "阵营", "标签"}, field) {
			reject("filtered count requires a hero or unit array and a supported filter")
		}
		p.take(field)
		if !p.take(",") || (p.peek() != "[" && p.peek() != "\"") {
			reject("count requires a literal filter")
		}
		filter := p.jsonLiteral()
		if !p.take(")") {
			reject("count requires a closing parenthesis")
		}
		match = p.c.countFilter(field, filter)
	}
	if array.raw == nil {
		return scalar("int", nil)
	}
	var total int64
	for _, item := range array.raw.([]value) {
		if item.raw == nil {
			return scalar("int", nil)
		}
		if match == nil {
			total++
		} else if item.typ == "英雄" {
			switch match(item) {
			case nil:
				return scalar("int", nil)
			case true:
				total++
			}
		}
	}
	return scalar("int", new(big.Rat).SetInt64(total))
}

func (c *Catalog) countFilter(field string, filter value) func(value) any {
	if field == "英雄" {
		heroes, ok := filter.raw.([]value)
		if !ok || len(heroes) == 0 {
			reject("hero count requires a non-empty hero list")
		}
		masks := make(map[string]uint8)
		for _, hero := range heroes {
			name, named := nameOf(hero).(string)
			if !named || strings.TrimSpace(name) == "" || (hero.typ != "英雄" && hero.typ != "string") {
				reject("hero list members require a hero name")
			}
			obj, _ := hero.raw.(map[string]any)
			mask := uint8(3)
			for key, raw := range obj {
				switch key {
				case "名称", "name", "类型":
				case "已觉醒":
					awake, ok := raw.(bool)
					if !ok {
						reject("hero list awakening state must be a boolean")
					}
					mask = 1
					if awake {
						mask = 2
					}
				default:
					reject("hero list does not accept field %s", key)
				}
			}
			masks[name] |= mask
		}
		return func(item value) any {
			name, ok := nameOf(item).(string)
			if !ok || name == "" {
				return nil
			}
			mask := masks[name]
			if mask == 0 || mask == 3 {
				return mask == 3
			}
			obj, _ := item.raw.(map[string]any)
			awake, known := obj["已觉醒"].(bool)
			if !known {
				return nil
			}
			return awake == (mask == 2)
		}
	}
	expected, ok := filter.raw.(string)
	if !ok || expected == "" {
		reject("count requires a non-empty faction or tag name")
	}
	if field == "阵营" {
		return func(item value) any {
			obj, _ := item.raw.(map[string]any)
			if obj[field] == nil {
				return nil
			}
			return obj[field] == expected
		}
	}
	switch expected {
	case "登场":
		expected = "具有登场效果"
	case "整备":
		expected = "具有整备效果"
	}
	return func(item value) any {
		options := c.cardTagOptions(item)
		if len(options) == 0 {
			return nil
		}
		found := slices.Contains(options[0], expected)
		for _, tags := range options[1:] {
			if slices.Contains(tags, expected) != found {
				return nil
			}
		}
		return found
	}
}
