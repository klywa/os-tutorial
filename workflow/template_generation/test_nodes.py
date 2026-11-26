from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from workflow.template_generation import nodes, run


# A deterministic provider transcript for local integration and browser acceptance.
SOURCE = """商店有阵容需要的甄姬时，可以锁定商店，给下回合留一张登场补牌的英雄。这条不限棋手。
曹操已经在场时可以买甄姬。甄姬登场给一张其他登场英雄牌，留在场上后，曹操整备有机会再触发一次。
蔡文姬在场、甄姬在手时，可以买曹操。先上曹操再打甄姬，曹操有机会从蔡文姬那里获得等级，整备也可能触发甄姬的登场。"""
COMMON, BOARD, COMBO = SOURCE.splitlines()
NAMES = ("预留补牌英雄", "曹操重触发登场", "先上曹操再打甄姬")
PIDS = ("general", "partner", "combined")
BUY, LOCK = "解释为何购买英雄", "解释为何锁定商店"
CARD_REFS = {
    "甄姬": {"id": "card:1271", "quote": "获得1张其他的登场英雄牌。", "season": "S1"},
    "曹操": {"id": "card:1281", "quote": "随机触发1名【三分】英雄的登场效果。", "season": "S1"},
    "蔡文姬": {"id": "card:1841", "quote": "等级最低的其他3名【三分】英雄等级+1。", "season": "S1"},
}
LINES = (
    """锁住甄姬，下回合还能靠她登场补一张英雄牌。
甄姬正是阵容要的牌，锁店能给下回合留住她。
商店留下甄姬，下回合还有补登场牌的机会。
甄姬能补登场英雄，值得为她留这一轮商店。
先留住甄姬，下一回合买她就有了着落。
下回合想用甄姬补牌，可以先把她留在商店。
阵容需要甄姬补牌，锁住就不用下回合重新找她。
商店里这张甄姬，值得给下回合留下。
要靠甄姬登场补牌，这轮可以先把她锁住。
把甄姬留到下回合买，她能再给一张登场英雄牌。
锁住要用的甄姬，下回合还能买她来补牌。
甄姬能补一张登场英雄牌，让她在商店多留一轮。
下回合要找的甄姬已经出现了，可以留住这间商店。
甄姬的登场能给阵容补牌，锁店能留住这个选择。
阵容的补牌人选就在商店，值得为甄姬留一轮。
锁住现在的商店，下回合仍有甄姬可买。""",
    """曹操在场，甄姬登场补的牌还有机会在整备时再补一次。
甄姬留在场上，曹操整备时可能让她再给一张登场英雄牌。
曹操有机会再次触发甄姬，让她的登场多补一张牌。
让甄姬登场补牌，之后曹操整备还可能再触发她。
甄姬进场就能补牌，场上的曹操还能给她再次补牌的机会。
场上已有曹操，甄姬的补牌效果有机会在整备时再来一次。
把甄姬留在曹操身边，整备时她也可能再补牌。
除了登场那张牌，甄姬还可能靠曹操整备再补一张。
曹操整备可能点到甄姬，让她再触发一次登场补牌。
有曹操在，甄姬的登场补牌也可能在整备时触发。
甄姬登场拿牌后，还能等曹操整备再触发她。
曹操整备能随机触发登场，甄姬在场就有机会再补牌。
让曹操有机会触发甄姬，整备时也能补登场英雄牌。
甄姬给的登场英雄牌，曹操整备时可能让她再给一张。
曹操在场时，留着甄姬有机会让她多触发一次补牌。
甄姬除了登场能给牌，还可能在曹操整备时再给牌。""",
    """蔡文姬在场，先上曹操再打手里的甄姬，曹操也有机会升级。
手里的甄姬放到曹操之后打，蔡文姬就有机会给曹操升等级。
先让曹操上场，再打甄姬时他就可能分到蔡文姬的等级。
有蔡文姬在，手里的甄姬可以等曹操上场后再打，让他也有机会升级。
让曹操先站上场，手里的甄姬就可能靠蔡文姬给他升级。
场上的蔡文姬会在甄姬打出时加等级，曹操先上才有机会分到。
手里这张甄姬能触发蔡文姬，曹操先上就有机会得到等级。
先上曹操再打手中甄姬，蔡文姬加等级时才有机会选到他。
蔡文姬已经在场，留手里的甄姬等曹操上场后再触发升级。
曹操先入场，甄姬从手里打出时蔡文姬就可能给他升级。
手里的甄姬能触发场上蔡文姬，让曹操先上才有机会吃到等级。
先让曹操上场等甄姬打出，蔡文姬就可能把等级加给他。
曹操先于手里的甄姬上场，就有机会分到蔡文姬给的等级。
为了让曹操有机会升级，先让他上场再打甄姬触发蔡文姬。
打手里的甄姬会触发蔡文姬，先上曹操就能多一个升级人选。
场上有蔡文姬，把甄姬留到曹操入场后打，他也有机会升等级。""",
)


def card(name):
    return {"名称": name, "卡牌类型": "英雄"}


def condition_cases(index):
    if index == 0:
        state = {"我方": {"阵容英雄名列表": ["甄姬"], "商店列表": [card("甄姬")]}}
        expr = '"甄姬" in 我方.阵容英雄名列表 and any(我方.商店列表, .名称 == "甄姬")'
        mutations = [("商店列表", []), ("阵容英雄名列表", [])]
    else:
        target, partner = ("甄姬", "曹操") if index == 1 else ("曹操", "蔡文姬")
        state = {"动作": {"选中": card(target), "候选列表": [card(target)]},
                 "我方": {"场上英雄列表": [card(partner)], "手牌列表": [card("甄姬")]}}
        expr = f'动作.选中.名称 == "{target}" and any(我方.场上英雄列表, .名称 == "{partner}")'
        mutations = [("场上英雄列表", [])]
        if index == 2:
            expr += ' and any(我方.手牌列表, .名称 == "甄姬")'
            mutations.append(("手牌列表", []))
    cases = [{"kind": "positive", "reason": "必要资源均到位", "state": state}]
    if index == 0:
        changed = deepcopy(state)
        changed["我方"].update(棋手名称="小妲己", 装备列表=[])
        cases.append({"kind": "positive", "reason": "更换无关棋手后仍能留牌", "state": changed})
    for field, replacement in mutations:
        negative = deepcopy(state)
        negative["我方"][field] = replacement
        if index == 1:
            negative["我方"]["手牌列表"] = [card("曹操")]
        cases.append({"kind": "negative", "reason": field + "中没有所需英雄", "state": negative})
        missing = deepcopy(state)
        del missing["我方"][field]
        cases.append({"kind": "missing", "reason": field + "未观测到", "state": missing})
    return expr, cases


def transcript(index):
    pid = PIDS[index]
    quote = SOURCE.splitlines()[index]
    refs = [{"location": f"第{index + 1}段", "quote": quote}]
    prerequisites = (["商店有阵容需要的甄姬"], ["曹操已上场"], ["蔡文姬已上场", "甄姬在手"])[index]
    scope = ("通用", "曹操在场", "蔡文姬在场且甄姬在手")[index]
    point = dict(id=pid, content=quote, type=("运营节奏", "英雄联动", "英雄联动")[index],
                 strategy="借登场英雄补牌", principle=NAMES[index], scope=scope,
                 prerequisites=prerequisites, related_ids=[], source_refs=refs)
    enrich = dict(point_id=pid, knowledge=quote, cause=quote, benefit=NAMES[index], scope=scope,
                  prerequisites=prerequisites, source_refs=refs,
                  card_refs=[ref for name, ref in CARD_REFS.items() if name in quote], gaps=[])
    events = {"point_id": pid, "events": [{"id": "e1", "event": LOCK if index == 0 else BUY,
              "subject": ("甄姬", "甄姬", "曹操")[index], "entry": "商店", "reason": NAMES[index]}],
              "excluded": ["文字稿只描述这一处商店决策，其余入口留待核对。"]}
    expression, cases = condition_cases(index)
    conditions = {"point_id": pid, "conditions": [{"id": "c1", "event_id": "e1", "name": NAMES[index],
                  "scope": {"player": None, "lineup": None}, "expression": expression,
                  "reason": quote, "cases": cases}]}
    candidates = [{"id": f"u{i + 1}", "text": line,
                   "review": ("采用，交代当前资源、时机与收益。" if i < 2 else "未选，主要理由已收录。")}
                  for i, line in enumerate(LINES[index].splitlines())]
    phrases = {"point_id": pid, "groups": [{"condition_id": "c1", "selected": ["u1", "u2"],
               "candidates": candidates, "review": "逐句核对原文，保留两句可独立解释本次决策的原句。"}]}
    return dict(point=point, enrich=enrich, events=events, conditions=conditions, phrases=phrases)


def acceptance(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source, output = directory / "三分教学.txt", directory / "三分教学.json"
    work = directory / "run"
    branches = [transcript(i) for i in range(3)]
    source.write_text(SOURCE, encoding="utf-8")

    def generate(provider, model, prompt):
        stage = next(s for s in nodes.STAGES if prompt.startswith(
            (nodes.HERE / "prompts" / (s + ".md")).read_text(encoding="utf-8").splitlines()[0]))
        if stage == "identify":
            return json.dumps({"points": [b["point"] for b in branches]}, ensure_ascii=False)
        point = json.loads(prompt.split("当前知识点\n\n", 1)[1].split("\n\n", 1)[0])
        result = deepcopy(branches[PIDS.index(point["id"])][stage])
        if stage == "enrich" and point["id"] == "partner":
            result["scope"] = "限定三分阵容且曹操在场"
        return json.dumps(result, ensure_ascii=False)

    revision = directory / "补充修订.json"
    revision.write_text(json.dumps(branches[1]["enrich"], ensure_ascii=False), encoding="utf-8")
    with patch.object(run.providers, "generate", generate):
        for args in (["start", str(source), "--output", str(output), "--model", "offline-acceptance-fixture",
                      "--pause-after", "enrich"], ["revise", "--stage", "enrich", "--point", "partner",
                      "--file", str(revision)], ["resume"]):
            if run.main([*args, "--run-dir", str(work)]):
                raise AssertionError("本地验收运行未通过")
    return output


class NodesTest(unittest.TestCase):
    def test_actual_conditions_and_stage_joins(self):
        branch = transcript(2)
        cond = nodes.validate("conditions", branch["conditions"], branch)
        self.assertEqual([True, False, False, False, False],
                         [c["actual"] for c in cond["conditions"][0]["cases"]])
        wrong = deepcopy(cond)
        wrong["conditions"][0]["cases"][1]["state"] = wrong["conditions"][0]["cases"][0]["state"]
        with self.assertRaisesRegex(ValueError, "实际命中"):
            nodes.validate("conditions", wrong, branch)
        library, links = nodes.assemble({PIDS[2]: branch})
        self.assertEqual({row["id"] for row in library["groups"][0]["utterances"]},
                         set(links[library["groups"][0]["id"]]))

    def test_scoped_material_and_verified_sources(self):
        branch = transcript(1)
        point = branch["point"]
        prompt = nodes.prepare("conditions", SOURCE, point, branch)
        self.assertIn("E01-S02", prompt)
        self.assertNotIn("E22-S01", prompt)
        for stage in nodes.STAGES:
            prompt = nodes.prepare(stage, "| 列 | 引文 |\n| --- | --- |\n| 1 | 曹操 |",
                                   None if stage == "identify" else point, branch)
            self.assertNotRegex(prompt, r"(?m)^\s*\|?\s*:?-{3,}:?\s*\|")
        previous = {"source": SOURCE, "point": point}
        nodes.validate("enrich", branch["enrich"], previous)
        branch["enrich"]["card_refs"][0]["quote"] = "虚构的卡面引文"
        with self.assertRaisesRegex(ValueError, "卡面出处"):
            nodes.validate("enrich", branch["enrich"], previous)
        point["related_ids"] = ["unrelated"]
        with self.assertRaisesRegex(ValueError, "引用未知"):
            nodes.validate("identify", {"points": [point]}, previous)

    def test_empty_selection_and_unexpressible_event(self):
        a, b = transcript(0), transcript(1)
        a["conditions"].update(conditions=[], rejected=[{"event_id": "e1", "reason": "缺少可观测事实"}])
        a["phrases"]["groups"] = []
        lib, _ = nodes.assemble({PIDS[0]: a, PIDS[1]: b})
        self.assertEqual(len(lib["groups"]), 1)
        b["phrases"]["groups"][0]["selected"] = []
        with self.assertRaisesRegex(ValueError, "未生成合格"):
            nodes.assemble({PIDS[1]: b})
