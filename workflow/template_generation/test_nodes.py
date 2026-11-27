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
蔡文姬在场，等曹操上场再打手里的甄姬，曹操才有机会升级。
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
        expr = f'any(我方.场上英雄列表, .名称 == "{partner}")'
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
                 prerequisite="，".join(prerequisites) + "。", related_ids=[], source_refs=refs,
                 related_refs=[{"location": "第一段", "quote": COMMON}] if index else [])
    enrich = dict(point_id=pid, knowledge=quote, cause=quote, benefit=NAMES[index], scope=scope,
                  prerequisites=prerequisites, source_refs=refs,
                  card_refs=[ref for name, ref in CARD_REFS.items() if name in quote], gaps=[])
    events = {"point_id": pid, "events": [{"id": "e1", "event": LOCK if index == 0 else BUY,
              "subject": ("甄姬", "甄姬", "曹操")[index], "entry": "商店", "reason": NAMES[index],
              "expected": NAMES[index] + "的机会。", "base": None}],
              "excluded": ["文字稿只描述这一处商店决策，其余入口留待核对。"]}
    expression, cases = condition_cases(index)
    direction = dict(limited=scope, not_limited="以后商店是否再次刷到搭档",
                     expected=NAMES[index], wording="只描述当前可证的机会。")
    conditions = {"point_id": pid, "conditions": [{"id": "c1", "event_id": "e1", "name": NAMES[index],
                  "scope": {"player": None, "lineup": None}, "expression": expression,
                  "extra_key": ("", "甄姬", "曹操")[index],
                  "reason": quote, "cases": cases, **direction}]}
    candidates = [{"id": f"u{i + 1}", "text": line,
                   "review": ("采用，交代当前资源、时机与收益。" if i < 2 else "未选，主要理由已收录。")}
                  for i, line in enumerate(LINES[index].splitlines())]
    phrases = {"point_id": pid, "groups": [{"condition_id": "c1", "selected": [f"u{i}" for i in range(1, 7)],
               "writing": direction, "candidates": candidates, "review": "逐句核对原文后选取六句。"}]}
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
    def test_conditions_require_explicit_key_and_reject_its_repeated_fact(self):
        branch = transcript(1)
        response = branch["conditions"]
        missing = deepcopy(response)
        del missing["conditions"][0]["extra_key"]
        with self.assertRaisesRegex(ValueError, "extra_key"):
            nodes.validate("conditions", missing, branch)
        repeated = deepcopy(response)
        row = repeated["conditions"][0]
        row["expression"] = '动作.选中.名称 == "甄姬" and ' + row["expression"]
        with self.assertRaisesRegex(ValueError, "重复"):
            nodes.validate("conditions", repeated, branch)

    def test_explicit_key_counts_toward_base_fields(self):
        branch = transcript(1)
        row = branch["conditions"]["conditions"][0]
        nodes._validate_condition(row, BUY, ["动作.选中.名称", "我方.场上英雄列表", ".名称"])

    def test_refinement_priority_is_only_compared_for_competing_keys(self):
        branch = transcript(1)
        branch["events"]["events"][0]["base"] = {
            "expected": "利用场上的曹操", "fields": ["我方.场上英雄列表", ".名称"],
        }
        base = branch["conditions"]["conditions"][0]
        specific = {**deepcopy(base), "id": "c2", "layer": "refinement"}
        base.update(layer="base", extra_key="*")
        branch["conditions"]["conditions"].append(specific)
        nodes.validate("conditions", branch["conditions"], branch)

    def test_every_knowledge_type_can_follow_its_own_event_from_mixed_source(self):
        samples = {
            "英雄定位": ("韩信是主C，靠整备或开团永久成长，战斗中靠普攻挑飞控制。", BUY),
            "阵容作用": ("开备韩信靠队友多次整备和开团，让主要输出持续加级。", "解释为何建议向某阵容发展"),
            "英雄联动": ("曹操在场时可再次触发甄姬的登场，甄姬需留在场上供整备选取。", BUY),
            "功能英雄": ("梦奇从战场出售后取得兑换券，打出位可留给下一张资源英雄。", "解释为何从战场出售英雄"),
            "对策英雄": ("敌方韩信依赖免控维持输出时，张良的压制有机会打断他。", "解释为何上阵英雄"),
            "天赋": ("满人口时选扩编名额，购买额外人口后能保留一个打出位。", "解释为何选择天赋"),
            "装备": ("法源之杯给朵莉亚持续回蓝，让她更早施法支援水域内的队友。", "解释为何穿戴装备"),
            "效果牌": ("封神一瞬指定韩信后，他自身每次永久加级都可再获得一级。", "解释为何对目标使用效果牌"),
            "棋手技能": ("钦定主角指定韩信后，后续打出合格的牌可以给他永久等级。", "解释为何对目标使用棋手技能"),
            "运营节奏": ("姜导在4级集中找首张韩信，容错不足时优先部署现成战力。", "解释为何棋手升级"),
            "特殊技巧": ("先留出打出位，上梦奇后再卖出，才能在同回合腾位并拿到退场兑换券。", "解释为何从战场出售英雄"),
            "针对敌方阵容或英雄的打法": ("面对敌方高爆发先考虑名刀·司命保命，前提是触发后仍有机会反击。", "解释为何穿戴装备"),
        }
        guide = nodes._json(nodes.REF / "knowledge-types.json")
        self.assertEqual(set(samples), set(guide))
        self.assertEqual(set(range(2, 27)), {row for rule in guide.values() for row in rule["workbook_rows"]})
        adjacent_types = {
            "英雄定位": "运营节奏", "阵容作用": "英雄联动", "英雄联动": "功能英雄",
            "功能英雄": "对策英雄", "对策英雄": "针对敌方阵容或英雄的打法", "天赋": "运营节奏",
            "装备": "针对敌方阵容或英雄的打法", "效果牌": "棋手技能", "棋手技能": "效果牌",
            "运营节奏": "英雄定位", "特殊技巧": "功能英雄", "针对敌方阵容或英雄的打法": "对策英雄",
        }
        for index, (type_name, (knowledge, event)) in enumerate(samples.items()):
            with self.subTest(type=type_name):
                other_type = adjacent_types[type_name]
                other = samples[other_type][0]
                source = knowledge + other
                points = [{
                    "id": f"p{slot}", "type": kind, "content": quote, "strategy": "对应当前问题",
                    "principle": quote, "scope": "相应局面", "prerequisite": "原文所述条件成立",
                    "source_refs": [{"location": "同一段", "quote": quote}], "related_refs": [],
                    "related_ids": [f"p{1-slot}"],
                } for slot, kind, quote in ((0, type_name, knowledge), (1, other_type, other))]
                identified = nodes.validate("identify", {"points": points}, {"source": source})["points"]
                point, distractor = identified
                self.assertNotEqual(point["id"], distractor["id"])
                inputs = {"point": point, "source": source, "related_points": [distractor]}
                prompt = nodes.prepare("enrich", source, point, inputs)
                self.assertIn(other, prompt)
                self.assertIn(guide[type_name]["stop"], prompt)
                self.assertNotIn(guide[other_type]["stop"], prompt)
                response = {
                    "point_id": point["id"], "knowledge": knowledge, "cause": knowledge,
                    "benefit": knowledge, "scope": point["scope"], "prerequisites": [],
                    "source_refs": point["source_refs"], "card_refs": [], "gaps": [],
                }
                enrich = nodes.validate("enrich", response, inputs)
                self.assertEqual(type_name, enrich["type"])
                with self.assertRaisesRegex(ValueError, "知识类型"):
                    nodes.validate("enrich", {**response, "type": other_type, "knowledge": other}, inputs)
                inputs["enrich"] = enrich
                prompt = nodes.prepare("events", source, point, inputs)
                event_anchors = prompt.split("当前知识类型常见事件（按实际收益匹配）\n\n", 1)[1].split("\n\n", 1)[0]
                self.assertIn(event, json.loads(event_anchors))
                nodes.validate("events", {"point_id": point["id"], "excluded": [], "events": [{
                    "id": f"e{index}", "event": event, "subject": knowledge, "entry": "对应决策",
                    "reason": knowledge, "expected": knowledge, "base": None,
                }]}, inputs)

    def test_enrichment_preserves_and_enforces_identified_type(self):
        branch = transcript(1)
        point = branch["point"]
        inputs = {"point": point, "source": SOURCE}
        result = nodes.validate("enrich", branch["enrich"], inputs)
        self.assertEqual(point["type"], result["type"])
        with self.assertRaisesRegex(ValueError, "知识类型"):
            nodes.validate("enrich", {**branch["enrich"], "type": "运营节奏"}, inputs)
        self.assertIn("当前类型的补充边界", nodes.prepare("enrich", SOURCE, point, inputs))

    def test_declared_base_cannot_disappear_behind_refinement_or_rejection(self):
        branch = transcript(1)
        branch["events"]["events"][0]["base"] = {
            "expected": "曹操能配合甄姬登场。",
            "fields": ["动作.选中.名称", "我方.场上英雄列表", ".名称"],
        }
        output = branch["conditions"]
        condition = output["conditions"][0]
        condition["layer"] = "refinement"
        with self.assertRaisesRegex(ValueError, "缺少基础组"):
            nodes.validate("conditions", output, branch)
        rejected = dict(point_id=PIDS[1], conditions=[], rejected=[{
            "event_id": "e1", "reason": "无法运行求值器", "blocker": "missing_field", "reference": "求值器",
        }])
        with self.assertRaisesRegex(ValueError, "本地求值"):
            nodes.validate("conditions", rejected, branch)
        condition["layer"] = "base"
        nodes.validate("conditions", output, branch)
        condition["scope"]["player"] = "姜导"
        with self.assertRaisesRegex(ValueError, "超出基础条件"):
            nodes.validate("conditions", output, branch)
        condition["scope"]["player"] = None
        refinement = {**deepcopy(condition), "id": "refined", "layer": "refinement"}
        output["conditions"].append(refinement)
        with self.assertRaisesRegex(ValueError, "细分组优先级"):
            nodes.validate("conditions", output, branch)
        refinement["priority"] = 1
        nodes.validate("conditions", output, branch)

    def test_equipment_points_include_unnamed_equipment_for_comparison(self):
        point = {"id": "mana", "type": "装备", "content": "法源之杯帮助回蓝。"}
        equipment = {(row["season"], row["id"]) for row in nodes._card_rows(point, [])
                     if row["category"] == "equipment"}
        self.assertEqual(equipment, {
            (season, row["id"]) for season in nodes.SEASONS
            for row in nodes._json(nodes.HERE / "knowledge" / (season + ".json"))
            if row["category"] == "equipment"})

    def test_player_skill_quote_from_nested_prompt_card_is_accepted(self):
        source = "姜导要利用技能培养主力。"
        point = {"id": "skill", "content": source, "type": "棋手技能"}
        ref = {"season": "S1", "id": "card:664101", "quote": "己方英雄首次升到25级，获得1张秘技牌封神一瞬。"}
        result = {"point_id": "skill", "knowledge": source, "cause": source, "benefit": source, "scope": "姜导",
                  "prerequisites": [], "gaps": [], "source_refs": [{"quote": source, "location": "首行"}],
                  "card_refs": [ref]}
        available = list(nodes._card_rows(point, []))
        self.assertNotIn(ref["id"], [card["id"] for card in available])
        self.assertIn(ref["quote"], nodes.prepare("enrich", source, point, {}))
        self.assertEqual({**result, "type": point["type"]},
                         nodes.validate("enrich", result, {"point": point, "source": source}))

    def test_selected_phrases_require_six_and_specific_objects(self):
        branch = transcript(1)
        branch["conditions"] = nodes.validate("conditions", branch["conditions"], branch)
        group = branch["phrases"]["groups"][0]
        group["selected"] = group["selected"][:2]
        with self.assertRaisesRegex(ValueError, "6"):
            nodes.validate("phrases", branch["phrases"], branch)
        skipped = nodes.validate("phrases", branch["phrases"], branch, after_retry=True)["groups"][0]
        self.assertEqual([], skipped["selected"])
        self.assertIn("重试后只筛出 2 条", skipped["review"])
        group["selected"] = [f"u{i}" for i in range(1, 7)]
        group["candidates"][0]["text"] = "这件装备能让曹操多回蓝。"
        with self.assertRaisesRegex(ValueError, "指代"):
            nodes.validate("phrases", branch["phrases"], branch)

    def test_assembly_uses_formal_title_for_lineup_alias(self):
        branch = transcript(1)
        row = branch["conditions"]["conditions"][0]
        row["scope"] = {"player": "姜导", "lineup": "开备韩信"}
        for case in row["cases"]:
            case["state"]["我方"].update(棋手名称="姜导", 阵容名称="开备韩信")
        library, _ = nodes.assemble({PIDS[1]: branch})
        group = library["groups"][0]
        self.assertEqual(group["scope"], {"player": "姜导", "lineup": "开备韩信-姜导"})
        self.assertIn('我方.阵容名称 == "开备韩信"', group["effective_expression"])
        self.assertEqual(row["scope"]["lineup"], "开备韩信")

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

    def test_model_prompts_inline_decision_fields_and_have_no_file_read_instructions(self):
        branch = transcript(1)
        for stage in ('enrich', 'conditions', 'phrases'):
            prompt = nodes.prepare(stage, SOURCE, branch['point'], branch)
            for filename in ('src/condition/catalog.json', 'docs/template-library.md',
                             '../../../src/condition/catalog-v04.json', 'writing-strategy.md#按对象选词'):
                self.assertNotIn(filename, prompt)
            if stage in ('enrich', 'conditions'):
                self.assertIn('容错数', prompt)
                self.assertIn('对局.玩家列表', prompt)
        self.assertIn('实战判断所需字段', nodes.prepare('enrich', SOURCE, branch['point'], branch))

    def test_empty_selection_and_unexpressible_event(self):
        a, b = transcript(0), transcript(1)
        a["conditions"].update(conditions=[], rejected=[{"event_id": "e1", "reason": "缺少可观测事实",
                                                       "blocker": "missing_field", "reference": "商店锁定目标"}])
        a["phrases"]["groups"] = []
        lib, _ = nodes.assemble({PIDS[0]: a, PIDS[1]: b})
        self.assertEqual(len(lib["groups"]), 1)
        b["phrases"]["groups"][0]["selected"] = []
        with self.assertRaisesRegex(ValueError, "未生成合格"):
            nodes.assemble({PIDS[1]: b})
