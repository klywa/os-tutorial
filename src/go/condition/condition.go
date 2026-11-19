// Package condition evaluates snapshot conditions against the shared event catalog.
package condition

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"unicode/utf8"
)

type EventDefinition struct {
	Category   string
	Parameters map[string]string
}

type Catalog struct {
	Events       map[string]EventDefinition
	Types        map[string]map[string]string
	Roots        map[string]string
	Aliases      map[string]string
	Operations   map[string][]string
	Enums        map[string][]string
	CardTags     map[string]CardTagRecord `json:"card_tags"`
	CardTagsFile string                   `json:"card_tags_file"`
}

type CardTagRecord struct {
	Type     string
	Name     string
	Awakened bool
	Tags     []string
}

func (c *Catalog) cardTags(v value) any {
	if v.raw == nil {
		return nil
	}
	if list, ok := v.raw.([]value); ok {
		result := []any{}
		for _, item := range list {
			if tags, ok := c.cardTags(item).([]any); ok {
				result = append(result, tags...)
			} else {
				result = append(result, nil)
			}
		}
		return result
	}
	name, _ := nameOf(v).(string)
	obj, _ := v.raw.(map[string]any)
	rawID, hasID := obj["id"]
	id, _ := rawID.(string)
	if number, ok := rawID.(json.Number); ok {
		id = "card:" + number.String()
	}
	if hasID {
		row, ok := c.CardTags[id]
		if !ok || row.Type != v.typ || (name != "" && name != row.Name) {
			return nil
		}
		name = row.Name
	}
	awake, hasForm := obj["已觉醒"].(bool)
	var shared []string
	found := false
	for key, row := range c.CardTags {
		if row.Type != v.typ || name != row.Name || (hasID && row.Type != "英雄" && id != key) ||
			(row.Type == "英雄" && hasForm && row.Awakened != awake) {
			continue
		}
		if !found {
			shared = slices.Clone(row.Tags)
			found = true
		} else {
			shared = slices.DeleteFunc(shared, func(s string) bool { return !slices.Contains(row.Tags, s) })
		}
	}
	if !found {
		return nil
	}
	tags := make([]any, len(shared))
	for i, tag := range shared {
		tags[i] = tag
	}
	return tags
}

// EvaluateCondition uses WXQ_CONDITION_CATALOG, catalog.json beside the executable,
// or the repository catalog, in that order. Both raw and exported catalogs are supported.
func EvaluateCondition(eventJSON []byte, expression string, stateJSON []byte) (bool, error) {
	path := os.Getenv("WXQ_CONDITION_CATALOG")
	if path == "" {
		if exe, err := os.Executable(); err == nil {
			candidate := filepath.Join(filepath.Dir(exe), "catalog.json")
			if _, err := os.Stat(candidate); !os.IsNotExist(err) {
				path = candidate
			}
		}
	}
	if path == "" {
		_, source, _, ok := runtime.Caller(0)
		if !ok {
			return false, fmt.Errorf("set WXQ_CONDITION_CATALOG")
		}
		path = filepath.Join(filepath.Dir(source), "..", "..", "condition", "catalog.json")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return false, err
	}
	var envelope struct {
		Catalog json.RawMessage `json:"condition_catalog"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		return false, err
	}
	if envelope.Catalog != nil {
		data = envelope.Catalog
	}
	var c Catalog
	if err := json.Unmarshal(data, &c); err != nil {
		return false, err
	}
	if c.CardTagsFile == "card-tags.json" {
		data, err = os.ReadFile(filepath.Join(filepath.Dir(path), "card-tags.json"))
		if err != nil {
			return false, err
		}
		if err := json.Unmarshal(data, &c.CardTags); err != nil {
			return false, err
		}
	}
	return c.EvaluateCondition(eventJSON, expression, stateJSON)
}

// Internally, syntax and type errors abort recursive descent through a private sentinel.
// Unexpected programmer panics propagate to the caller.
type ConditionError struct {
	Message string
	Column  int // one-based Unicode column, zero for input errors outside the expression
}

func (e *ConditionError) Error() string {
	if e.Column > 0 {
		return fmt.Sprintf("column %d: %s", e.Column, e.Message)
	}
	return e.Message
}

func reject(format string, args ...any) {
	panic(&ConditionError{Message: fmt.Sprintf(format, args...)})
}

func decodeObject(raw []byte) map[string]any {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var obj map[string]any
	if err := d.Decode(&obj); err != nil || obj == nil {
		reject("expected a JSON object")
	}
	if err := d.Decode(new(any)); err != io.EOF {
		reject("trailing JSON data")
	}
	return obj
}

// EvaluateCondition reuses a caller-provided catalog. An unknown final value is false.
func (c *Catalog) EvaluateCondition(eventJSON []byte, expression string, stateJSON []byte) (result bool, err error) {
	var p *parser
	defer func() {
		if r := recover(); r != nil {
			if problem, ok := r.(*ConditionError); ok {
				if p != nil {
					problem.Column = 1 + utf8.RuneCountInString(expression[:p.offset])
				}
				err = problem
			} else {
				panic(r)
			}
		}
	}()
	event, state := decodeObject(eventJSON), decodeObject(stateJSON)
	name, ok := event["事件"].(string)
	def, known := c.Events[name]
	if ok && !known {
		const prefix = "解释为何"
		alias := prefix + name
		if strings.HasPrefix(name, prefix) {
			alias = strings.TrimPrefix(name, prefix)
		}
		def, known = c.Events[alias]
	}
	if !ok || !known {
		reject("unknown event %q", name)
	}
	args, _ := event["参数"].(map[string]any)
	if raw, exists := event["参数"]; exists && (raw == nil || args == nil) {
		reject("参数 must be an object")
	}
	for key, raw := range args {
		spec, ok := def.Parameters[key]
		if !ok {
			reject("unknown event parameter %q", key)
		}
		c.validateSnapshot(c.read(spec, raw), 0)
	}
	for key, raw := range state {
		if spec, ok := c.Roots[key]; ok {
			c.validateSnapshot(c.read(spec, raw), 0)
		}
	}
	if strings.TrimSpace(expression) == "" {
		return true, nil
	}
	p = &parser{rest: expression, total: len(expression), c: c, def: def, args: args, state: state}
	v := p.expr(1)
	if tok := p.peek(); tok != "" {
		p.offset = p.total - len(p.rest)
		reject("unexpected token %q", tok)
	}
	requireBool(v)
	return v.raw == true, nil
}

type value struct {
	typ           string
	union         string // declared alternatives before the runtime tag selected typ
	raw           any    // nil is unknown, arrays are []value
	field         string // catalog key for a field-specific operator restriction
	literalString bool
}

func (v value) domain() string {
	if v.union != "" {
		return v.union
	}
	return v.typ
}

func scalar(t string, raw any) value { return value{typ: t, raw: raw} }
func (c *Catalog) canonical(t string) string {
	if a, ok := c.Aliases[t]; ok {
		return a
	}
	return t
}
func elements(t string) (string, bool) {
	if strings.HasPrefix(t, "Array<") && strings.HasSuffix(t, ">") {
		return t[6 : len(t)-1], true
	}
	return "", false
}
func numeric(t string) bool { return t == "int" || t == "number" }

// Snapshots can carry additional game metadata. Check every supplied, declared
// argument field even if the condition never reads it.
func (c *Catalog) validateSnapshot(v value, depth int) {
	if depth > maxNesting {
		reject("snapshot nesting exceeds %d", maxNesting)
	}
	switch raw := v.raw.(type) {
	case []value:
		for _, item := range raw {
			c.validateSnapshot(item, depth+1)
		}
	case map[string]any:
		for key, item := range raw {
			if key == "类型" && v.union != "" {
				continue
			} // union discriminator
			if key == "name" {
				key = "名称"
			}
			if spec, known := c.Types[v.typ][key]; known {
				c.checkEnum(v.typ+"."+key, item)
				c.validateSnapshot(c.read(spec, item), depth+1)
			}
		}
	}
}

func (c *Catalog) checkEnum(field string, raw any) {
	allowed, closed := c.Enums[field]
	if !closed || raw == nil {
		return
	}
	s, ok := raw.(string)
	if !ok || !slices.Contains(allowed, s) {
		reject("%s requires one of %v", field, allowed)
	}
}
func (c *Catalog) read(t string, raw any) value {
	t = c.canonical(t)
	if raw == nil {
		return scalar(t, nil)
	}
	if item, array := elements(t); array {
		list, ok := raw.([]any)
		if !ok {
			reject("expected %s", t)
		}
		out := make([]value, len(list))
		for i, x := range list {
			out[i] = c.read(item, x)
		}
		return scalar(t, out)
	}
	if strings.Contains(t, "|") {
		obj, ok := raw.(map[string]any)
		if !ok {
			reject("expected %s", t)
		}
		tag, _ := obj["类型"].(string)
		tag = c.canonical(tag)
		valid := false
		for _, member := range strings.Split(t, "|") {
			if c.canonical(member) == tag {
				valid = true
				break
			}
		}
		if !valid {
			reject("expected 类型 in %s", t)
		}
		v := c.read(tag, raw)
		v.union = t
		return v
	}
	switch t {
	case "int", "number":
		n, ok := raw.(json.Number)
		if !ok {
			reject("expected %s", t)
		}
		r, ok := new(big.Rat).SetString(n.String())
		if !ok || t == "int" && !r.IsInt() {
			reject("expected %s", t)
		}
		raw = r
	case "string":
		if _, ok := raw.(string); !ok {
			reject("expected string")
		}
	case "bool":
		if _, ok := raw.(bool); !ok {
			reject("expected bool")
		}
	default:
		if _, ok := c.Types[t]; !ok {
			reject("unknown type %q", t)
		}
		switch x := raw.(type) {
		case map[string]any:
			// Equipment has its own 类型 attribute. Other entities may carry an
			// explicit type tag even in an argument whose type is already known.
			if _, attr := c.Types[t]["类型"]; !attr {
				if tag, present := x["类型"]; present {
					name, ok := tag.(string)
					if !ok || c.canonical(name) != t {
						reject("entity tag %v incompatible with %s", tag, t)
					}
				}
			}
		case string:
		default:
			reject("expected %s", t)
		}
	}
	return scalar(t, raw)
}
func (c *Catalog) literal(raw any, depth int) value {
	if depth > maxNesting {
		reject("literal nesting exceeds %d", maxNesting)
	}
	switch x := raw.(type) {
	case bool:
		return scalar("bool", x)
	case string:
		return value{typ: "string", raw: x, literalString: true}
	case json.Number:
		return c.read("number", x)
	case []any:
		items := make([]value, len(x))
		for i, item := range x {
			items[i] = c.literal(item, depth+1)
		}
		return scalar("Array<?>", items)
	case map[string]any:
		tag, _ := x["类型"].(string)
		tag = c.canonical(tag)
		fields, ok := c.Types[tag]
		if !ok {
			reject("unknown entity type %q", tag)
		}
		name, ok := x["名称"].(string)
		if !ok {
			name, ok = x["name"].(string)
		}
		if !ok || name == "" {
			reject("entity literal needs 名称")
		}
		for key, data := range x {
			if key == "类型" || key == "name" {
				continue
			}
			ft, ok := fields[key]
			if !ok {
				reject("unknown field %s.%s", tag, key)
			}
			c.read(ft, data)
			c.checkEnum(tag+"."+key, data)
		}
		return scalar(tag, x)
	}
	reject("invalid literal")
	return value{}
}
