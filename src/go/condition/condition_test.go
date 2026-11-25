package condition

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestHeroArrayCount(t *testing.T) {
	const event = `{"事件":"上阵英雄","参数":{"arg1":"弈星"}}`
	const count = `玩家.战场.计数(英雄, ["小乔", {"类型":"英雄","名称":"弈星","已觉醒":true}])`
	for _, tc := range []struct {
		expression string
		state      string
		want       bool
	}{
		{count + " == 3", `{"玩家":{"战场":["小乔",{"名称":"小乔","已觉醒":false},{"类型":"衍生物","名称":"小乔"},{"名称":"弈星","已觉醒":false},{"名称":"弈星","已觉醒":true}]}}`, true},
		{count + " == 0", `{"玩家":{"战场":[]}}`, true},
		{count + " >= 2", `{"玩家":{"战场":["小乔"]}}`, false},
		{"not (" + count + " >= 2)", `{"玩家":{"战场":[{"名称":"弈星"}]}}`, false},
		{"not (" + count + " >= 2)", `{"玩家":{"战场":[null]}}`, false},
		{"not (" + count + " >= 2)", `{"玩家":{}}`, false},
	} {
		got, err := EvaluateCondition([]byte(event), tc.expression, []byte(tc.state))
		if err != nil || got != tc.want {
			t.Errorf("%s with %s = %v, %v; want %v", tc.expression, tc.state, got, err, tc.want)
		}
	}
}

func TestSharedCases(t *testing.T) {
	data, err := os.ReadFile("../../condition/cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name, Expression string
		Event, State     json.RawMessage
		Result, Error    bool
		Column           int
		Parameters       map[string]string
	}
	if err := json.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	for _, tc := range cases {
		t.Run(tc.Name, func(t *testing.T) {
			evaluate := EvaluateCondition
			if tc.Parameters != nil || strings.Contains(tc.Expression, ".标签") {
				data, err := os.ReadFile("../../condition/catalog.json")
				if err != nil {
					t.Fatal(err)
				}
				var c Catalog
				if err := json.Unmarshal(data, &c); err != nil {
					t.Fatal(err)
				}
				tags, err := os.ReadFile("../../condition/test-card-tags.json")
				if err != nil {
					t.Fatal(err)
				}
				if err := json.Unmarshal(tags, &c.CardTags); err != nil {
					t.Fatal(err)
				}
				if tc.Parameters != nil {
					c.Events["自定义事件"] = EventDefinition{Parameters: tc.Parameters}
				}
				evaluate = c.EvaluateCondition
			}
			got, err := evaluate(tc.Event, tc.Expression, tc.State)
			if (err != nil) != tc.Error || err == nil && got != tc.Result {
				t.Fatalf("got %v, %v; want %v (error %v)", got, err, tc.Result, tc.Error)
			}
			if tc.Column > 0 {
				problem, ok := err.(*ConditionError)
				if !ok || problem.Column != tc.Column {
					t.Fatalf("got %v; want column %d", err, tc.Column)
				}
			}
		})
	}
}
