"""Validate a reviewed working package before atomically writing the named local library."""
import argparse
import hashlib
import json
import os
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

from check_batch import check as check_batch
from check_scenarios import check as check_scenarios
from wording import banned_pattern
from src.python.condition import validate_expression

ID = r"E\d{2}-S\d{2,}"
RELATED = ({"E01", "E06", "E07"}, {"E10", "E11", "E12"})


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
        if item["accepted"]:
            if match := banned.search(line):
                raise ValueError(f"{name} 第{index}句使用禁用表达「{match[0]}」（含生造词），该句须淘汰")
            if "快攻" in line and any(word in str(group) for word in ("驱雷", "司空震")):
                raise ValueError(f"{name} 第{index}句把快速攻击缩写成快攻，该句须淘汰")
            accepted.append(line)
    if not accepted or accepted != group["utterances"]:
        raise ValueError(f"{name} 输出必须恰好包含全部达标句且保留顺序")


def validate(package, records, cases, directory):
    if not package.get("condition_catalog"):
        raise ValueError("缺少正式条件目录")
    check_batch(package, scenarios=cases)
    events = confirmed_events(directory)
    reviews = {(r["event_name"], r["name"]): r for r in records}
    keys = [(g["event_name"], g["name"]) for g in package["groups"]]
    if len(reviews) != len(records) or len(keys) != len(set(keys)) or set(keys) != set(reviews):
        raise ValueError("组和复核记录须逐一对应")
    for group, key in zip(package["groups"], keys):
        if key[0] not in events:
            raise ValueError(f"未登记事件：{key[0]}")
        check_review(group, reviews[key], events)
        validate_expression(key[0], group["expression"], package["condition_catalog"])
    errors = check_scenarios(package, cases)
    if errors:
        raise ValueError("\n".join(errors))


def verify_gemini(records, directory):
    for row in records:
        name = row["name"]
        if not all(isinstance(row.get(k), str) and row[k].strip()
                   for k in ("gemini_request", "gemini_state")):
            raise ValueError(f"{name} 缺少 Gemini 请求或成功状态文件")
        request = read(directory / row["gemini_request"])
        state = read(directory / row["gemini_state"])
        encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        if state.get("phase") != "draft" or state.get("request") != digest:
            raise ValueError(f"{name} Gemini 请求与状态不对应")
        if state.get("feedback_count", 0) or "feedback" in state or "previous_draft" in state:
            raise ValueError(f"{name} 只使用 Gemini 首批原稿，不接收反馈改写稿")
        candidates = [c["text"] for c in row["candidates"]]
        if request.get("fields", {}).get("utterances") != "lines" or state.get("content", {}).get("utterances") != candidates:
            raise ValueError(f"{name} 候选必须按原序来自 Gemini 成功响应，该批仅接受首批原句")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("draft", "review", "scenarios", "output"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    target = args.output.resolve()
    if target in {p.resolve() for p in (args.draft, args.review, args.scenarios)}:
        parser.error("输出文件不能与工作稿、复核记录或场景相同")
    try:
        package = read(args.draft)
        records = read(args.review)
        verify_gemini(records, args.review.parent)
        validate(package, records, read(args.scenarios), SKILL / "references" / "events")
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
