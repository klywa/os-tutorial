"""Add the approved wording rules to a Gemini request and check banned phrases."""
import argparse
import json
from pathlib import Path
import re

REFERENCES = Path(__file__).resolve().parents[1] / "references"
CONTEXT_KEY = "话术词表"


def approved_rules():
    strategy = (REFERENCES / "writing-strategy.md").read_text(encoding="utf-8-sig")
    return strategy.split("\n## 按对象选词\n", 1)[1].strip()


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
    request["context"][CONTEXT_KEY] = approved_rules()


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
