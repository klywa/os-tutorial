"""Validate a reviewed working package before atomically writing the named local library."""
import argparse
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"),
                str(SKILL.parent / "wanxiangqi-knowledge" / "scripts")]

from templates_store import preview_import
from templates_schema import group_modes, group_seasons, group_versions
from frontend.template_v04 import effective_expression

from check_batch import check as check_batch
from check_scenarios import check as check_scenarios
from group_identity import (
    audit_key, has_awakening_guard, merge_duplicate_groups, name_template_group, template_group_trigger,
)
from wording import banned_pattern, check_wording_brief
from src.python.condition import validate_expression

ID = r"E\d{2}-S\d{2,}"
RELATED = ({"E01", "E06", "E07"}, {"E10", "E11", "E12"}, {"E13", "E14", "E15"})
RELATED_EVENTS = (
    ("解释为何购买英雄", "解释为何选择英雄",
     "解释为何竞拍目标英雄（第1次拍卖）", "解释为何竞拍目标英雄（第2次拍卖）"),
    ("解释为何购买效果牌", "解释为何选择效果牌", "解释为何竞拍目标效果牌（第3次拍卖）"),
    ("解释为何穿戴装备", "解释为何铸造装备", "解释为何转移装备"),
)
EFFECT_AUCTION = "解释为何竞拍目标效果牌（第3次拍卖）"
HERO_AUCTIONS = frozenset(RELATED_EVENTS[0][2:])


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def confirmed_events(directory):
    events = {}
    for path in sorted(directory.glob("E[0-9][0-9].md")):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        title = lines[0].removeprefix("# ").strip()
        if any(line.startswith("暂停生成。") for line in lines):
            continue
        ids = set()
        section = ""
        for line in lines:
            if line.startswith("## "):
                section = line[3:].strip()
            if section == "骨架库":
                match = re.match(r"^- \*\*(" + ID + r")\*\*", line)
                if match:
                    code = match[1]
                    if not code.startswith(path.stem + "-") or code in ids:
                        raise ValueError(f"{path.name} 骨架编号错误或重复：{code}")
                    ids.add(code)
        events[title] = (path.stem, ids)
        current = {
            "E07": ("解释为何竞拍目标英雄（第1次拍卖）", "解释为何竞拍目标英雄（第2次拍卖）"),
            "E12": ("解释为何竞拍目标效果牌（第3次拍卖）",),
            "E25": ("解释阵容成型后的提升方向",),
        }
        for name in current.get(path.stem, ()):
            events[name] = (path.stem, ids)
    return events


def check_review(group, review, events):
    event, name = group["event_name"], group["name"]
    event_id, confirmed = events[event]
    used = review["skeletons"]
    if not isinstance(used, list) or not used or not set(used) <= confirmed:
        raise ValueError(f"{name} 没有命中本事件已确认骨架")
    mentioned = set(re.findall(ID, group["explanation_before"]))
    if mentioned != set(used):
        raise ValueError(f"{name} 前置思考与实际采用的骨架不一致")
    if group.get("syntax_version") == "0.4" and "E03-S01" in used and not has_awakening_guard(group["expression"]):
        raise ValueError(f"{name} 每个觉醒合成分支须同时判断已觉醒及觉醒进度为 2")
    for related in RELATED:
        if event_id in related:
            checks = review.get("related_events", {})
            if set(checks) != related or not all(isinstance(v, str) and v.strip() for v in checks.values()):
                raise ValueError(f"{name} 缺少三个关联事件的逐项判断")

    attempt = review.get("attempt")
    if type(attempt) is not int or attempt != 1:
        raise ValueError(f"{name} 只允许首批16句，不接收改写批次")
    candidates = review["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 16:
        raise ValueError(f"{name} 每批须包含16条候选")
    unique = set()
    accepted = []
    pools = {"best": 0, "diverse": 0}
    labeled_selection = any("pool" in item for item in candidates)
    banned = banned_pattern()
    for index, item in enumerate(candidates, 1):
        line = item["text"]
        key = "".join(c for c in unicodedata.normalize("NFKC", line)
                      if not c.isspace() and not unicodedata.category(c).startswith("P"))
        if not key or (item.get("accepted") is True and key in unique):
            raise ValueError(f"{name} 第{index}句重复或为空")
        if item.get("accepted") is True:
            unique.add(key)
        if not isinstance(item.get("verdict"), str) or not item["verdict"].strip():
            raise ValueError(f"{name} 第{index}句缺少 verdict")
        if type(item["accepted"]) is not bool:
            raise ValueError(f"{name} 第{index}句缺少入选结论")
        qualified = item.get("qualified", item["accepted"])
        if type(qualified) is not bool or item["accepted"] and not qualified:
            raise ValueError(f"{name} 第{index}句只有通过合格审核才可入选")
        if item["accepted"]:
            if labeled_selection:
                if item.get("pool") not in pools:
                    raise ValueError(f"{name} 第{index}句缺少最佳或差异入选类别")
                pools[item["pool"]] += 1
            if match := banned.search(line):
                raise ValueError(f"{name} 第{index}句使用禁用表达「{match[0]}」（含生造词），该句须淘汰")
            if "快攻" in line and any(word in str(group) for word in ("驱雷", "司空震")):
                raise ValueError(f"{name} 第{index}句把快速攻击缩写成快攻，该句须淘汰")
            accepted.append(line)
    actual = [row["text"] for row in group["utterances"]] if group.get("syntax_version") == "0.4" else group["utterances"]
    if len(accepted) > 6 or max(pools.values()) > 3:
        raise ValueError(f"{name} 最多收录六条候选")
    if not accepted or accepted != actual:
        raise ValueError(f"{name} 输出必须符合已选达标句记录（全部达标句中的入选原句），并保留首批顺序")


def verify_coverage(audit, reviews, events):
    inventory = audit["inventory"]
    units = audit["units"]
    sources = [unit["source"] for unit in units]
    if (not inventory or len(inventory) != len(set(inventory))
            or len(sources) != len(set(sources)) or set(sources) != set(inventory)):
        raise ValueError("来源清单与逐段审阅记录须完整对应")
    covered = set()
    for unit in units:
        materials = unit["materials"]
        if not materials and not unit.get("reason", "").strip():
            raise ValueError(f"{unit['source']} 无可用素材时须登记理由")
        for material in materials:
            if not material["decision"].strip() or not material["events"]:
                raise ValueError(f"{unit['source']} 素材缺少决策描述或事件判断")
            for assessment in material["events"]:
                event = assessment["event"]
                checks = assessment["checks"]
                skeletons = events.get(event, (None, set()))[1]
                if {row["skeleton"] for row in checks} != skeletons:
                    raise ValueError(f"{event} 须逐项核对已确认骨架")
                if not checks and not assessment.get("reason", "").strip():
                    raise ValueError(f"{event} 无可用骨架时须登记理由")
                earlier = set()
                dispositions = {}
                for row in checks:
                    if not row["reason"].strip():
                        raise ValueError(f"{event} {row['skeleton']} 缺少覆盖或跳过理由")
                    if row["status"] == "skip":
                        if row["skeleton"] in dispositions:
                            raise ValueError(f"{event} {row['skeleton']} 覆盖记录重复或矛盾")
                        dispositions[row["skeleton"]] = "skip"
                        continue
                    key = tuple(row["group"])
                    if row["status"] != "group" or len(key) != 2 or key[0] != event:
                        raise ValueError(f"{event} 覆盖记录须引用同一事件的模板组")
                    if key in earlier or dispositions.get(row["skeleton"]) == "skip":
                        raise ValueError(f"{event} {row['skeleton']} 覆盖记录重复或矛盾")
                    dispositions[row["skeleton"]] = "group"
                    if any(tuple(base) not in earlier for base in row.get("bases", [])):
                        raise ValueError(f"{key[1]} 须先覆盖对应的通用组")
                    if key not in reviews or row["skeleton"] not in reviews[key]["skeletons"]:
                        raise ValueError(f"{key[1]} 通用组或细分组缺失，或骨架不一致")
                    earlier.add(key)
                    covered.add(key)
    if covered != set(reviews):
        raise ValueError("存在未绑定来源和素材的模板组")


@lru_cache(maxsize=2)
def effect_card_tiers(season="S1"):
    directory = ROOT / "website-data"
    path = (directory / "entities" / "effect-cards.json" if season == "S1"
            else directory / "seasons" / season / "cards.json")
    cards = read(path) if path.is_file() else []
    return {name: card["properties"]["quality"] for card in cards
            if card.get("category") == "effect-cards" and "quality" in card.get("properties", {})
            for name in (card["name"], *card.get("aliases", []))}


def verify_related(groups, records):
    tiers = {}
    for group, review in zip(groups, records, strict=True):
        event = group["event_name"]
        family = next((names for names in RELATED_EVENTS if event in names), None)
        if family is None or group.get("ignored"):
            continue
        sync = review.get("sync")
        label = group["name"]
        if not isinstance(sync, dict):
            raise ValueError(f"{label} 缺少关联组同步复核")
        unavailable = sync.get("unavailable", {})
        unavailable_options = HERO_AUCTIONS.intersection(family) if family == RELATED_EVENTS[0] else set(family)
        if (not isinstance(unavailable, dict) or not set(unavailable) <= unavailable_options
                or not all(isinstance(evidence, str) and evidence.strip() for evidence in unavailable.values())):
            raise ValueError(f"{label} 跳过关联入口须提供有效事件和无法发生的证据")
        eligible = tuple(name for name in family if name not in unavailable)
        if EFFECT_AUCTION in family and group.get("syntax_version") == "0.4":
            known_tiers = {effect_card_tiers(season).get(group["extra_key"]) for season in group_seasons(group)} - {None}
            if len(known_tiers) > 1:
                raise ValueError(f"{label} 适用赛季的效果牌阶级不同，须按赛季核对关联入口")
            tier = sync.get("effect_card_tier", next(iter(known_tiers), None))
            if type(tier) is not int or not 1 <= tier <= 6:
                raise ValueError(f"{label} 须登记经过核对的效果牌阶级（1 至 6）")
            if known_tiers and tier not in known_tiers:
                raise ValueError(f"{label} 登记的效果牌阶级与卡面不符")
            if tier != 6:
                eligible = tuple(name for name in eligible if name != EFFECT_AUCTION)
        if event not in eligible:
            raise ValueError(f"{label} 在该拍卖轮次不可取得")
        if sync.get("exclusive"):
            if not all(isinstance(sync.get(key), str) and sync[key].strip()
                       for key in ("exclusive", "evidence")):
                raise ValueError(f"{label} 的事件独有理由须附证据")
            continue
        if not all(isinstance(sync.get(key), str) and sync[key].strip() for key in ("reason", "tier")):
            raise ValueError(f"{label} 须登记共享理由与细分层级，或提供事件独有理由及证据")
        scope_key = group_versions(group), group_modes(group)
        expected, members, triggers = tiers.setdefault((family, sync["reason"], sync["tier"], scope_key), (eligible, {}, {}))
        if expected != eligible:
            raise ValueError(f"{label} 在同一共享层级登记了不同的有效事件")
        trigger = template_group_trigger(group) if group.get("syntax_version") == "0.4" else None
        if event in members:
            if trigger is not None and triggers[event] == trigger:
                continue
            raise ValueError(f"{label} 在同一共享层级重复登记 {event}")
        triggers[event] = trigger
        expr = effective_expression(group.get("scope", {}), group["expression"])
        tokens = re.findall(r'"(?:\\.|[^"\\])*"|[\w.]+|[^\s]', expr)
        key = group["extra_key"].split("-")
        if event in {"解释为何铸造装备", "解释为何转移装备"}:
            if len(key) != 3 or key[1] != "*":
                raise ValueError(f"{label} 的共享条件不能限定动作独有的转出英雄或原装备")
            key = [key[0], key[2]]
            if event == "解释为何铸造装备":
                tokens = [re.sub(r"^动作\.目标装备(?=\.|$)", "动作.装备", token) for token in tokens]
        members[event] = (key, tokens)
    for (_, reason, tier, _), (eligible, members, _) in tiers.items():
        missing = [event for event in eligible if event not in members]
        if missing:
            raise ValueError(f"{reason}（{tier}）缺少关联组：{'、'.join(missing)}")
        if any(condition != members[eligible[0]] for condition in members.values()):
            raise ValueError(f"{reason}（{tier}）的同步组条件不一致")


def validate(package, records, cases, directory):
    if not package.get("condition_catalog"):
        raise ValueError("缺少正式条件目录")
    check_batch(package, scenarios=cases)
    events = confirmed_events(directory)
    reviews, keys = review_keys(package["groups"], records)
    if len(reviews) != len(records) or len(keys) != len(set(keys)) or set(keys) != set(reviews):
        raise ValueError("组和复核记录须逐一对应")
    verify_related(package["groups"], [reviews[key] for key in keys])
    for group, key in zip(package["groups"], keys):
        if key[0] not in events:
            raise ValueError(f"未登记事件：{key[0]}")
        check_review(group, reviews[key], events)
        if group.get("syntax_version") != "0.4":
            validate_expression(key[0], group["expression"], package["condition_catalog"])
    runtime = package
    if any(group.get("syntax_version") == "0.4" for group in package["groups"]):
        runtime = {"解释事件": {}}
        for group in package["groups"]:
            if group.get("ignored"):
                continue
            event = group["event_name"]
            event_groups = runtime["解释事件"].setdefault(event, {})
            event_groups.setdefault(group["extra_key"], []).append({
                "id": group["id"], "name": group["name"], "event_id": event, "priority": group.get("priority", 0),
                "expression": effective_expression(group.get("scope", {}), group["expression"]),
                "explanation": group["explanation_before"],
                "utterances": [{"id": row["id"], "text": row["text"]}
                               for row in group["utterances"] if not row.get("ignored")],
            })
    scopes = {group["id"]: group for group in package["groups"] if group.get("id")}
    errors = check_scenarios(runtime, cases, scopes=scopes)
    if errors:
        raise ValueError("\n".join(errors))


def verify_gemini(records, directory, briefs=None):
    for row in records:
        name = row["name"]
        if not all(isinstance(row.get(k), str) and row[k].strip()
                   for k in ("gemini_request", "gemini_state")):
            raise ValueError(f"{name} 缺少 Gemini 请求或成功状态文件")
        request = read(directory / row["gemini_request"])
        state = read(directory / row["gemini_state"])
        key = row.get("gemini_key", "utterances")
        if briefs is not None:
            brief = briefs[audit_key(row["event_name"], name, row.get("group_id"))]
            if not isinstance(brief, str) or not brief.strip():
                raise ValueError(f"{name} 须提供话术构思")
            check_wording_brief(brief)
            context = request.get("context", {})
            supplied_brief = (context.get("话术构思") if key == "utterances"
                              else context.get("各组输入", {}).get(key))
            if supplied_brief != brief:
                raise ValueError(f"{name} Gemini 请求中的话术构思与输出组不同")
            draft_request = read(directory / row["gemini_brief_request"])
            draft_state = read(directory / row["gemini_brief_state"])
            fingerprint = hashlib.sha256(json.dumps(draft_request, sort_keys=True, ensure_ascii=False,
                                                    allow_nan=False).encode("utf-8")).hexdigest()
            brief_key = row.get("gemini_brief_key", "wording_brief")
            if (draft_state.get("phase") != "draft" or draft_state.get("request") != fingerprint
                    or draft_request.get("fields", {}).get(brief_key) != "text"
                    or draft_state.get("content", {}).get(brief_key) != brief):
                raise ValueError(f"{name} 构思须原样来自独立的 Gemini 响应")
        encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        if state.get("phase") != "draft" or state.get("request") != digest:
            raise ValueError(f"{name} Gemini 请求与状态不对应")
        if state.get("feedback_count", 0) or "feedback" in state or "previous_draft" in state:
            raise ValueError(f"{name} 只使用 Gemini 首批原稿，不接收反馈改写稿")
        candidates = [c["text"] for c in row["candidates"]]
        if request.get("fields", {}).get(key) != "lines" or state.get("content", {}).get(key) != candidates:
            raise ValueError(f"{name} 候选必须按原序来自 Gemini 成功响应，该批仅接受首批原句")


def include_referenced_events(package):
    events = package["events"]
    declared = {event.get("name") or event["signature"].rpartition("(")[0].strip() for event in events}
    catalog = package["condition_catalog"]["events"]
    for name in dict.fromkeys(group["event_name"] for group in package["groups"]):
        if name in declared:
            continue
        definition = catalog[name]
        parameters = ", ".join(f"{key}: {kind}" for key, kind in definition["parameters"].items())
        events.append({"name": name, "category": definition["category"], "signature": f"{name}({parameters})"})


def review_keys(groups, records):
    reviews = {audit_key(row["event_name"], row["name"], row.get("group_id")): row for row in records}
    keys = []
    for group in groups:
        event, name = group["event_name"], group["name"]
        by_id = audit_key(event, name, group.get("id"))
        keys.append(by_id if by_id in reviews else audit_key(event, name))
    return reviews, keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("draft", "review", "scenarios", "output"):
        parser.add_argument(field, type=Path)
    parser.add_argument("--coverage", type=Path, required=True, help="逐段、素材、事件与骨架覆盖记录")
    args = parser.parse_args()
    target = args.output.resolve()
    if target in {p.resolve() for p in (args.draft, args.review, args.scenarios, args.coverage)}:
        parser.error("输出文件不能与工作稿、复核记录或场景相同")
    try:
        package = read(args.draft)
        records = read(args.review)
        events_directory = SKILL / "references" / "events"
        reviews, keys = review_keys(package["groups"], records)
        briefs = {key: group.get("wording_brief") for group, key in zip(package["groups"], keys, strict=True)}
        verify_coverage(read(args.coverage), reviews, confirmed_events(events_directory))
        verify_gemini(records, args.review.parent, briefs)
        validate(package, records, read(args.scenarios), events_directory)
        package["groups"] = merge_duplicate_groups(package["groups"])
        for group in package["groups"]:
            group["name"] = name_template_group(group)
        include_referenced_events(package)
        preview = preview_import(ROOT, package)
        if preview["errors"]:
            raise ValueError("正式 v3 导入校验失败：" + "；".join(preview["errors"]))
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
                pending = Path(tmp.name)
                json.dump(package, tmp, ensure_ascii=False, indent=2, allow_nan=False)
                tmp.write("\n")
            os.replace(pending, target)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{target}（{len(package['groups'])} 组）")


if __name__ == "__main__":
    main()
