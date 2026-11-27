"""Model nodes that add explanation to groups whose matching rules are fixed."""
from copy import deepcopy

from . import base_library, nodes


def prepare(stage, source, point, previous):
    group = previous["seed"]
    context = {field: group[field] for field in ("event_name", "extra_key", "expression", "instruction")}
    context["scope"] = group.get("scope", {})
    locked = "固定模板组\n" + nodes._dump(context) + (
        "\n匹配规则由程序提供。只解释 instruction 要求的收益，原文中需要其他局面事实才成立的做法，"
        "不得当作这组的播报前提。可以说明机制及未来可获得的收益，不能断言特定局势已经发生。"
        "证据以指定原文、附带卡面和规则为准。拒绝编造数值。")
    if stage == "enrich":
        return locked + "\n\n" + nodes.prepare(stage, source, point, previous)
    if stage == "phrases":
        return locked + "\n\n" + nodes.prepare(stage, source, point, previous)
    prior = {"point_id": point["id"], "knowledge": previous["enrich"],
             "event_guide": nodes._event_material([group["event_name"]], True)}
    if stage == "events":
        shape = {"point_id": point["id"], "expected": "该固定事件最值得讲清的具体收益"}
        task = "只选解释角度。写明当前事件中的动作对象、收益和原因。"
    else:
        prior["event_angle"] = previous["events"]["events"][0]["expected"]
        shape = {"point_id": point["id"], "reason": "角度依据", "limited": "条件已经保证的事实",
                 "not_limited": "条件没保证的事实", "expected": "值得讲述的具体收益", "wording": "可用措辞和边界"}
        task = "只补解释角度和措辞边界，保留固定事件、键和条件。"
        if base_library.fixed_cases(group) is None:
            shape["cases"] = [{"kind": "positive、negative 或 missing", "reason": "依据", "state": {}}]
            task += "另提交正例、反例及缺值用例，证明固定规则可求值。用例可以包含正式动作和状态字段。"
            prior["condition_catalog"] = nodes.catalog()
    return "\n\n".join((locked, task, nodes._dump(prior), "只返回该形状的 JSON：" + nodes._dump(shape)))


def validate(stage, result, previous, *, after_retry=False):
    group = previous["seed"]
    result = deepcopy(nodes._object(result, stage))
    point_id = previous["point"]["id"]
    if result.get("point_id") != point_id:
        raise ValueError("固定组知识点 ID 不一致")
    if stage == "enrich":
        nodes._validate_evidence(result, previous)
        return result
    if stage == "events":
        if result.keys() != {"point_id", "expected"}:
            raise ValueError("已有组的事件阶段只接受解释角度")
        nodes._fields(result, "expected")
        return {"point_id": point_id, "events": [
            {"id": "fixed_event", "event": group["event_name"], "expected": result["expected"]}]}
    if stage == "conditions":
        allowed = {"point_id", "reason", "limited", "not_limited", "expected", "wording"}
        cases = base_library.fixed_cases(group)
        if cases is None:
            allowed.add("cases")
            cases = result.get("cases")
        if result.keys() != allowed:
            raise ValueError("已有组的条件阶段只接受解释角度及必要的求值用例")
        nodes._fields(result, "reason limited not_limited expected wording")
        base_library.validate_cases(group, cases)
        row = {field: result[field] for field in ("reason", "limited", "not_limited", "expected", "wording")}
        row.update(id="fixed_condition", event_id="fixed_event", layer="base", name=group["name"],
                   scope=group.get("scope", {}), extra_key=group["extra_key"], expression=group["expression"], cases=cases)
        return {"point_id": point_id, "conditions": [row]}
    if stage == "phrases":
        nodes._validate_phrases(result, previous, after_retry=after_retry,
                                candidate_count=6 if previous.get("local_replies") else 16)
        return result
    raise ValueError("未知固定组节点：" + stage)


def collect(branches):
    fills, links, checks = {}, {}, {}
    for pid, branch in branches.items():
        group = branch["seed"]
        gid = group["id"]
        knowledge, conditions = branch["enrich"], branch["conditions"]
        condition = conditions["conditions"][0]
        phrase = validate("phrases", branch["phrases"], branch, after_retry=True)["groups"][0]
        candidates = {row["id"]: row["text"] for row in phrase["candidates"]}
        links[gid], lines, checks[gid] = {}, [], condition["cases"]
        for selected in phrase["selected"]:
            uid = nodes._stable("u", gid, selected)
            lines.append({"id": uid, "text": candidates[selected]})
            links[gid][uid] = {"point_id": pid, "event_id": condition["event_id"], "condition_id": condition["id"],
                               "candidate_id": selected}
        fills[gid] = {"utterances": lines, "explanation_before": knowledge["knowledge"] + "\n" + condition["reason"],
                      "explanation_source": nodes._dump([*knowledge["source_refs"], *knowledge["card_refs"]]),
                      "explanation_after": phrase["review"]}
    return fills, links, checks
