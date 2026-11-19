"""Check editorial limits for newly generated v3 groups before import."""
import argparse
import json
from pathlib import Path


def check(document):
    if document.get("kind") != "speech-template-library" or document.get("schema_version") != 3:
        raise ValueError("请提供 v3 模板库 JSON")
    if not isinstance(document.get("groups"), list):
        raise ValueError("缺少模板组列表")
    for index, group in enumerate(document["groups"], 1):
        name = group.get("name") or str(index)
        explanation = group.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 300:
            raise ValueError(f"{name}：请填写 300 字以内的说明与依据")
        lines = group.get("utterances")
        if not isinstance(lines, list) or len(lines) < 2:
            raise ValueError(f"{name}：需要多条可独立使用的话术")
        for line in lines:
            if not isinstance(line, str) or not line.strip() or len(line) > 30:
                raise ValueError(f"{name}：每句须完整且不超过 30 字")
        if len({line.strip() for line in lines}) != len(lines):
            raise ValueError(f"{name}：组内有重复话术")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    document = json.loads(parser.parse_args().package.read_text(encoding="utf-8-sig"))
    try:
        check(document)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(f"已检查 {len(document['groups'])} 个模板组")
