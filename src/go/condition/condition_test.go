package condition

import (
	"encoding/json"
	"os"
	"testing"
)

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
			if tc.Parameters != nil {
				data, err := os.ReadFile("../../condition/catalog.json")
				if err != nil {
					t.Fatal(err)
				}
				var c Catalog
				if err := json.Unmarshal(data, &c); err != nil {
					t.Fatal(err)
				}
				c.Events["自定义事件"] = EventDefinition{Parameters: tc.Parameters}
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
