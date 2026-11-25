"""Add the complete writing strategy to a Gemini request and check banned phrases."""
import argparse
import json
from pathlib import Path
import re

REFERENCES = Path(__file__).resolve().parents[1] / "references"
CONTEXT_KEY = "完整写作策略"
BRIEF_HEADINGS = ("生效条件", "当前事件", "局面解释", "写法与措辞", "建议话术")


def check_wording_brief(text):
    headings = "|".join(BRIEF_HEADINGS)
    parts = re.split(rf"(?m)^[ \t]*(?:#{{1,4}}[ \t]*)?[「“]?({headings})[」”]?[：:]?[ \t]*$", text.strip())
    if tuple(parts[1::2]) != BRIEF_HEADINGS or any(not content.strip() for content in parts[2::2]):
        raise ValueError("话术构思须完整包含五段")
    if any(phrase in text for phrase in ("围绕本次行动兑现的取舍", "先说明具体收益，必要时提兑现前提")):
        raise ValueError("话术构思含脱离当前组的套话")
    examples = [line.strip()[2:].strip() for line in parts[-1].splitlines() if line.strip().startswith("- ")]
    if not 1 <= len(examples) <= 2 or any(not line or banned_pattern().search(line) or
                                        len("".join(line.split())) > 30 for line in examples if "{{" not in line):
        raise ValueError("话术构思须给出一到两条合规建议话术")


def writing_strategy():
    return (REFERENCES / "writing-strategy.md").read_text(encoding="utf-8-sig")


def approved_rules():
    return writing_strategy().split("\n## 按对象选词\n", 1)[1].strip()


def banned_pattern():
    rules = approved_rules()
    banned = [term for line in rules.splitlines() if line.startswith("- **禁用表达**")
              for term in re.findall(r"`([^`]+)`", line)]
    patterns = {
        "接等级": r"(?<!承)接等级",
        "加级": r"(?<!增)加级",
    }
    legacy = r"(?:接|吃)(?:不?到|住)?(?:落)?雷|重触发|双触发"
    return re.compile("|".join([legacy, *(patterns.get(term, re.escape(term)) for term in banned)]))


def add_rules(request):
    context = request["context"]
    context.pop("话术词表", None)
    context[CONTEXT_KEY] = writing_strategy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.draft.read_text(encoding="utf-8-sig"))
    add_rules(payload)
    args.request.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
