"""Read the lineup and talent sheets of the project's XLSX definition table."""
from pathlib import PurePosixPath
import posixpath
import re
from xml.etree import ElementTree
from zipfile import ZipFile

from .initialize import Lineup, add_members, card_name, names_from_label, official_lineup_name


def workbook_sheets(path, selected):
    with ZipFile(path) as workbook:
        def xml(member):
            return ElementTree.fromstring(workbook.read(member))

        rels = {r.get("Id"): r.get("Target") for r in xml("xl/_rels/workbook.xml.rels")}
        strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            strings = ["".join(t.text or "" for t in item.findall(".//{*}t"))
                       for item in xml("xl/sharedStrings.xml")]

        for sheet in xml("xl/workbook.xml").findall("./{*}sheets/{*}sheet"):
            name = sheet.get("name")
            if name not in selected:
                continue
            relationship = next(value for key, value in sheet.attrib.items() if key.endswith("}id"))
            target = rels[relationship]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(f"xl/{target}")
            if PurePosixPath(target).parts[:2] != ("xl", "worksheets"):
                raise ValueError(f"工作表路径无效：{name}")

            rows = []
            for row in xml(target).findall("./{*}sheetData/{*}row"):
                record = {}
                for cell in row.findall("./{*}c"):
                    column = re.match(r"[A-Z]+", cell.get("r", ""))
                    if not column:
                        continue
                    value = cell.findtext("./{*}v") or ""
                    if cell.get("t") == "s" and value:
                        value = strings[int(value)]
                    elif cell.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall("./{*}is//{*}t"))
                    if value.strip():
                        record[column.group()] = value.strip()
                if record:
                    rows.append(record)
            yield name, rows


def headers(rows, required):
    for offset, row in enumerate(rows):
        if required.issubset(row.values()):
            return [
                {label: record[column] for column, label in row.items() if column in record}
                for record in rows[offset + 1:]
            ]
    return []


def table_names(value):
    labels = re.sub(r"[（(][^）)]*[）)]", "", value)
    return [name for name in names_from_label(labels) if name and name not in {"无", "暂无", "-"}]


def lineup_from_table(path, cards, requested):
    name_column, hero_column = "打法名称", "英雄名称"
    sheets = dict(workbook_sheets(path, {"阵容英雄配置", "CP天赋打法"}))
    rows = headers(sheets.get("阵容英雄配置", []), {name_column, hero_column})
    if not rows:
        raise ValueError("阵容定义表缺少有效的阵容英雄配置数据")

    names = {row[name_column] for row in rows if row.get(name_column)}
    if requested is None and len(names) != 1:
        raise ValueError("阵容定义表含多个阵容，请用 --lineup 指定打法名称")
    name = requested or next(iter(names))
    matches = [row_name for row_name in names if official_lineup_name(row_name) == official_lineup_name(name)]
    if name in names:
        matches = [name]
    if len(matches) != 1:
        raise ValueError(f"阵容定义表没有唯一匹配的打法：{name}")

    selected = []
    active = ""
    for row in rows:
        active = row.get(name_column, active)
        if active == matches[0]:
            selected.append(row)

    lineup = Lineup(official_lineup_name(matches[0]))
    gear_columns = re.compile(r"(?:依赖装备|上位替代装备)\d+|(?:普通|特殊)装备推荐及理由.*")
    for row in selected:
        add_members(lineup, cards, table_names(row.get("核心输出", "")))
        hero_labels = table_names(row.get(hero_column, ""))
        add_members(lineup, cards, hero_labels)
        heroes = {hero for label in hero_labels for hero, _ in cards.get(("heroes", label), ())
                  if hero in lineup.heroes}
        for column, value in row.items():
            if gear_columns.fullmatch(column):
                for label in table_names(value):
                    gear = card_name(cards, "equipment", label, lineup.gaps)
                    if gear:
                        for hero in sorted(heroes):
                            lineup.equipment[gear, hero] = f"阵容英雄配置 · {hero} · {column}：{value}"
            elif re.fullmatch(r"(?:适配|推荐)?天赋\d*|CP天赋", column):
                lineup.talents.update(filter(None, (card_name(cards, "talents", label, lineup.gaps)
                                                    for label in table_names(value))))
            elif re.fullmatch(r"(?:适配|推荐|关键)?效果牌\d*", column):
                lineup.effects.update(filter(None, (card_name(cards, "effect-cards", label, lineup.gaps)
                                                    for label in table_names(value))))

    for row in headers(sheets.get("CP天赋打法", []), {"CP天赋", "完全匹配打法"}):
        mappings = [*table_names(row.get("完全匹配打法", "")), *table_names(row.get("新增打法支持", ""))]
        if row.get("CP天赋") and lineup.name in map(official_lineup_name, mappings):
            talent = card_name(cards, "talents", row["CP天赋"], lineup.gaps)
            if talent:
                lineup.talents.add(talent)
    return lineup
