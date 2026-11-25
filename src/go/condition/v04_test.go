package condition

import "testing"

func TestV04HeroMergeResult(t *testing.T) {
	event := []byte(`{"事件":"解释为何合成英雄","syntax_version":"0.4"}`)
	expression := `动作.英雄.等级 < 40 and 动作.合成后等级 != nil and 动作.合成后等级 >= 40 and 动作.合成后已觉醒 != nil and not 动作.合成后已觉醒`
	for _, test := range []struct {
		state string
		want  bool
	}{
		{`{"动作":{"英雄":{"等级":39},"合成后等级":40,"合成后已觉醒":false}}`, true},
		{`{"动作":{"英雄":{"等级":39},"合成后等级":40}}`, false},
		{`{"动作":{"英雄":{"等级":40},"合成后等级":40,"合成后已觉醒":false}}`, false},
	} {
		got, err := EvaluateCondition(event, expression, []byte(test.state))
		if err != nil || got != test.want {
			t.Fatalf("%s: got (%v, %v), expected %v", test.state, got, err, test.want)
		}
	}
}

func TestV04HandSaleCandidate(t *testing.T) {
	event := []byte(`{"事件":"解释为何从手牌出售英雄","syntax_version":"0.4"}`)
	expression := `动作.英雄.名称 == "赵云" and not 动作.英雄.已觉醒 and any(我方.手牌列表, .名称 == "灵感爆发") and any(我方.手牌列表, .卡牌类型 == "英雄" and not .已觉醒 and .名称 == "甄姬")`
	for _, test := range []struct {
		state string
		want  bool
	}{
		{`{"动作":{"英雄":{"名称":"赵云","已觉醒":false}},"我方":{"手牌列表":[{"名称":"灵感爆发"},{"名称":"甄姬","卡牌类型":"英雄","已觉醒":false}]}}`, true},
		{`{"动作":{"英雄":{"名称":"赵云","已觉醒":false}},"我方":{"手牌列表":[{"名称":"灵感爆发"},{"名称":"甄姬","卡牌类型":"英雄","已觉醒":true}]}}`, false},
		{`{"动作":{"英雄":{"名称":"赵云","已觉醒":true}},"我方":{"手牌列表":[{"名称":"灵感爆发"},{"名称":"甄姬","卡牌类型":"英雄","已觉醒":false}]}}`, false},
	} {
		got, err := EvaluateCondition(event, expression, []byte(test.state))
		if err != nil || got != test.want {
			t.Fatalf("%s: got (%v, %v), expected %v", test.state, got, err, test.want)
		}
	}
}

func TestV04Condition(t *testing.T) {
	event := []byte(`{"事件":"解释为何转移装备","syntax_version":"0.4"}`)
	state := []byte(`{"对手":null,"我方":{"场上英雄列表":[{"名称":"花木兰","等级":10}]},"动作":{"目标英雄":{"名称":"花木兰"}}}`)
	for _, test := range []struct {
		expression    string
		want, invalid bool
	}{
		{`any(我方.场上英雄列表, .名称 == 动作.目标英雄.名称)`, true, false},
		{`sum(filter(我方.场上英雄列表, .等级 >= 10), .等级) == 10`, true, false},
		{`对手 == nil or (对手.主C != nil and 对手.主C.等级 > 40)`, true, false},
		{`对手 == nil or 对手.主C.等级 > 40`, false, true},
		{`对手 == nil or 动作.未声明 == 1`, false, true},
		{`动作.目标英雄 is "花木兰"`, false, true},
	} {
		t.Run(test.expression, func(t *testing.T) {
			got, err := EvaluateCondition(event, test.expression, state)
			if got != test.want || (err != nil) != test.invalid {
				t.Fatalf("got (%v, %v), expected (%v, invalid=%v)", got, err, test.want, test.invalid)
			}
		})
	}
}
