"""Verify teaching quotes against an explicitly identified current card field."""
import argparse
import json
from pathlib import Path

from official import plain


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(rows, entities):
    if not isinstance(rows, list) or not rows:
        raise ValueError("请提供至少一个待审条目")
    errors = []
    fields = {}
    for category in ("heroes", "equipment", "talents", "effect-cards", "derivatives", "player-skills"):
        for card in read(entities / (category + ".json")):
            fields[(card["id"], "description")] = card.get("description", "")
            hero = (card.get("properties") or {}).get("heroCard") or {}
            for skill in hero.get("skillList") or []:
                fields[(card["id"], "skill:" + str(skill["id"]))] = plain(skill.get("desc"))
    for index, row in enumerate(rows, start=1):
        label = row.get("node") or str(index)
        if not row.get("quotes"):
            errors.append(f"{label}：缺少机制引文")
            continue
        for quote in row["quotes"]:
            field = quote.get("field", "description")
            source = fields.get((quote["entity"], field)) or ""
            text = quote.get("text")
            if not text or text not in source or text not in row["text"]:
                errors.append(f"{label}：正文与指定卡面字段未同时出现引文 {quote['entity']} / {field} / {text!r}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    rows = read(args.manifest)
    errors = check(rows, args.root / "entities")
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print(f"已核对 {len(rows)} 个条目中的 {sum(len(row['quotes']) for row in rows)} 段引文")


