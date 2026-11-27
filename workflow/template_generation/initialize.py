"""Build an empty v0.5 speech-template library from a lineup definition."""
import argparse
from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
import re
import sys

from frontend.template_v04 import validate_rule
from src.python.condition.v04 import lineup_name as official_lineup_name

from .nodes import HERE, REF, SEASONS, _json, _stable
from .run import encoded, read, write_bytes


SECTION_NAMES = {
    "关键装备": "equipment", "推荐装备": "equipment",
    "推荐天赋": "talents", "适配天赋": "talents",
    "关键效果牌": "effect-cards", "适配效果牌": "effect-cards",
}
ROSTER_SECTION = re.compile(r"(?:前期|中期|后期)?(?:阵容组成(?:与运营节奏)?|英雄组成(?:与运营)?|成员英雄)")
MEMBER_SUFFIX = re.compile(r"[（(](?:必需|必要|必备|可选|备选|核心|主C|副C)[）)]$")
NAME_SEPARATOR = re.compile(r"[／/、，,；;\n]+")


@dataclass
class Lineup:
    name: str
    heroes: dict[str, int] = field(default_factory=dict)
    talents: set[str] = field(default_factory=set)
    equipment: dict[tuple[str, str], str] = field(default_factory=dict)
    effects: set[str] = field(default_factory=set)
    gaps: list[str] = field(default_factory=list)


@lru_cache(maxsize=None)
def card_lookup(season):
    cards = {}
    for tag in (season,) if season else SEASONS:
        for row in _json(HERE / "knowledge" / (tag + ".json")):
            if row.get("awakened"):
                continue
            for key in (row["id"], row["name"], *row.get("aliases", ())):
                if key:
                    cards.setdefault((row["category"], key), set()).add((row["name"], row.get("tier")))
    return cards


def names_from_label(label):
    return [MEMBER_SUFFIX.sub("", name.strip().strip("*` ")).strip()
            for name in NAME_SEPARATOR.split(label) if name.strip()]


def card_name(cards, category, label, gaps):
    choices = cards.get((category, label), set())
    names = {name for name, _ in choices}
    if len(names) == 1:
        return next(iter(names))
    gaps.append(f"{label}：无法从卡牌表唯一确认名称")
    return None


def add_members(lineup, cards, labels):
    for label in dict.fromkeys(labels):
        name = card_name(cards, "heroes", label, lineup.gaps)
        if name is None:
            continue
        tiers = {tier for _, tier in cards[("heroes", label)] if type(tier) is int}
        if len(tiers) != 1 or (name in lineup.heroes and lineup.heroes[name] not in tiers):
            lineup.gaps.append(f"{name}：品阶无法唯一确认，可指定 --season")
            continue
        lineup.heroes[name] = next(iter(tiers))


def markdown_nodes(source):
    # Use the same section and entry parser as the knowledge editor.
    scripts = HERE.parents[1] / ".codex/skills/wanxiangqi-knowledge/scripts"
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("lineup_json_document", scripts / "json_document.py")
    parser = module_from_spec(spec)
    spec.loader.exec_module(parser)
    return parser.parse(source)


def section_entries(document):
    headings = []
    for node in document["nodes"]:
        if node["type"] == "heading":
            headings = [(level, title) for level, title in headings if level < node["level"]]
            headings.append((node["level"], node["title"].strip()))
        elif node["type"] == "entry" and headings:
            yield [title for _, title in headings], node


def mentioned(text, names):
    """Match whole known names, taking longer overlapping names first."""
    names = sorted(names, key=lambda name: (-len(name), name))
    if not names:
        return set()
    return set(re.findall("|".join(map(re.escape, names)), text))


def equipment_pairs(lineup, equipment_notes, reviewed):
    recipients = {}
    links = []
    for gear, evidence in equipment_notes.items():
        # Explicit assignment takes precedence over names mentioned as beneficiaries.
        assigned = {hero for hero in lineup.heroes if re.search(
            rf"(?:交给?|交由|给)[\s「“]*{re.escape(hero)}|{re.escape(hero)}(?:亲自)?(?:穿戴|佩戴|装备|核心)",
            evidence,
        )}
        if not assigned:
            heroes_in_text = mentioned(evidence, lineup.heroes)
            assigned = heroes_in_text if len(heroes_in_text) == 1 else set()
        recipients[gear] = {hero: evidence for hero in assigned}
        for other in equipment_notes:
            label = {other}
            if len(other) >= 4 and sum(name.startswith(other[:2]) for name in equipment_notes) == 1:
                label.add(other[:2])
            if other != gear and any(re.search(
                rf"(?:缺少|缺|替换|替代|比较)[^。；;]{{0,20}}?{re.escape(name)}|{re.escape(name)}[^。；;]{{0,10}}?(?:替代|换下)",
                evidence,
            ) for name in label):
                links.append((gear, other, evidence))

    for gear, hero in reviewed:
        if gear not in equipment_notes or hero not in lineup.heroes:
            raise ValueError(f"装备归属复核不在本次阵容资料内：{gear} → {hero}")
        recipients[gear][hero] = reviewed[gear, hero]

    # Alternatives share a recipient only when the connected notes identify one unambiguous wearer.
    for _ in range(len(equipment_notes)):
        pending = {gear: {} for gear in equipment_notes if not recipients[gear]}
        for gear, other, evidence in links:
            for target, known in ((gear, other), (other, gear)):
                if target in pending and len(recipients[known]) == 1:
                    hero, reason = next(iter(recipients[known].items()))
                    pending[target][hero] = f"{gear}：{evidence}\n{known}：{reason}"
        updates = {gear: candidates for gear, candidates in pending.items() if len(candidates) == 1}
        if not updates:
            break
        recipients.update(updates)

    for gear, assigned in recipients.items():
        if not assigned:
            lineup.gaps.append(f"{gear}：装备适用英雄待确认")
        for hero, evidence in sorted(assigned.items()):
            lineup.equipment[gear, hero] = evidence


def lineup_from_note(document, cards, name, reviewed):
    entries = list(section_entries(document))
    title = next((n["title"] for n in document["nodes"] if n["type"] == "heading" and n["level"] == 1), "")
    lineup = Lineup(official_lineup_name(name or document.get("topic") or title))
    if not lineup.name:
        raise ValueError("资料未提供阵容名，请使用 --lineup")

    semantics = document.get("semantics") or {}
    compositions = semantics.get("compositions") or {}
    members = list(semantics.get("core_heroes") or [])
    members.extend(row["hero"] for stage in compositions.values() for row in stage if row.get("hero"))
    if not any(compositions.values()):
        for path, entry in entries:
            label = entry["key"]
            if label in {"核心英雄", "核心输出"}:
                members.extend(names_from_label(entry["value"]))
            elif ROSTER_SECTION.fullmatch(path[-1]) and label != "正文":
                members.extend(value for value in names_from_label(label)
                               if MEMBER_SUFFIX.search(label) or ("heroes", value) in cards)
    add_members(lineup, cards, members)

    equipment_notes = {}
    for path, entry in entries:
        category = next((SECTION_NAMES[h] for h in reversed(path) if h in SECTION_NAMES), None)
        if category is None or entry["key"] == "正文":
            continue
        for label in names_from_label(entry["key"]):
            item = card_name(cards, category, label, lineup.gaps)
            if item is None:
                continue
            if category == "equipment":
                equipment_notes[item] = entry["value"]
            elif category == "talents":
                lineup.talents.add(item)
            else:
                lineup.effects.add(item)
    equipment_pairs(lineup, equipment_notes, reviewed)
    return lineup


def read_lineup(path, lineup_name=None, season=None, reviewed=None):
    cards = card_lookup(season)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        from .initialize_table import lineup_from_table
        return lineup_from_table(path, cards, lineup_name)
    if suffix == ".json":
        document = read(path)
    elif suffix in {".md", ".markdown"}:
        document = markdown_nodes(path.read_text(encoding="utf-8-sig"))
    else:
        raise ValueError("输入须为知识 JSON、Markdown 或 XLSX 阵容定义表")
    return lineup_from_note(document, cards, lineup_name, reviewed or {})


def build_library(lineup):
    if not lineup.heroes:
        raise ValueError("资料中没有可确认的阵容成员英雄")
    groups = []
    expression = "我方.阵容名称 == " + json.dumps(lineup.name, ensure_ascii=False)
    ending = "，禁止依赖任何特定局势"

    def add(action, entities, keys, instruction, evidence=""):
        event = "解释为何" + action
        extra_key = "-".join(keys)
        group = {
            "id": _stable("g", lineup.name, event, extra_key),
            "name": f"{lineup.name}：{action} · {'、'.join(entities)}",
            "event_name": event,
            "extra_key": extra_key,
            "scope": {"player": None, "lineup": None},
            "syntax_version": "0.5",
            "priority": 0,
            "expression": expression,
            "effective_expression": expression,
            "instruction": f"结合知识，{instruction}{ending}",
            "utterances": [],
        }
        if evidence:
            group["explanation_source"] = evidence
        validate_rule(group, event)
        groups.append(group)

    for hero, tier in lineup.heroes.items():
        role = f"解释{hero}在{lineup.name}阵容中的定位和作用"
        for action in ("购买英雄", "选择英雄"):
            add(action, (hero,), (hero,), f"{role}，如果{hero}是主C不得忽略{hero}的作战能力")
        auction_round = {2: 1, 3: 1, 4: 2, 5: 2}.get(tier)
        if auction_round:
            add(f"竞拍目标英雄（第{auction_round}次拍卖）", (hero,), (hero,),
                f"{role}。若有充足信息，应补充拍卖预算（用建议预期，不要说死）")

    for talent in sorted(lineup.talents):
        add("选择天赋", (talent,), (talent,), f"解释{talent}为何适合{lineup.name}阵容")
    for (gear, hero), evidence in lineup.equipment.items():
        instruction = f"解释在{lineup.name}阵容中，为何{gear}适合{hero}"
        add("铸造装备", (gear, hero), (hero, "*", gear), instruction, evidence)
        add("穿戴装备", (gear, hero), (hero, gear), instruction, evidence)
        add("转移装备", (gear, hero), (hero, "*", gear), instruction, evidence)
    for effect in sorted(lineup.effects):
        for action in ("购买效果牌", "选择效果牌"):
            add(action, (effect,), (effect,), f"解释为何{effect}适用于{lineup.name}阵容")

    definitions = _json(REF / "events.json")
    events = sorted({group["event_name"] for group in groups})
    return {"kind": "speech-template-library", "schema_version": 3,
            "events": [definitions[event]["portable"] for event in events], "groups": groups}


def main(argv=None):
    parser = argparse.ArgumentParser(description="从万象棋阵容资料初始化空话术模板库。")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--lineup", help="正式阵容名称。多阵容表格必填。")
    parser.add_argument("--season", choices=SEASONS)
    parser.add_argument("--equipment-review", type=Path, help="装备归属复核 JSON，包含 equipment、hero、quote")
    args = parser.parse_args(argv)
    try:
        reviewed = {}
        if args.equipment_review:
            source = args.source.read_text(encoding="utf-8-sig")
            for row in read(args.equipment_review):
                if not row["quote"].strip() or row["quote"] not in source:
                    raise ValueError(f"装备归属复核引文不在原文：{row['equipment']}")
                reviewed[row["equipment"], row["hero"]] = row["quote"]
        lineup = read_lineup(args.source, args.lineup, args.season, reviewed)
        for gap in lineup.gaps:
            print(f"待确认：{gap}", file=sys.stderr)
        library = build_library(lineup)
        data = encoded(library)
        if not args.output.is_file() or args.output.read_bytes() != data:
            write_bytes(args.output, data, exclusive=True)
        print(f"{args.output} · {len(library['groups'])} 组")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        parser.exit(1, f"初始化失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
