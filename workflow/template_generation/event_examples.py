"""Load and validate the workflow's own event-specific editorial examples."""
import argparse
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RESOURCE = HERE / 'references/event-examples.json'
REQUIRED = {'condition', 'utterance'}
ENERGY = re.compile(r'[0-9零〇一二两三四五六七八九十百]+\s*(?:点)?\s*能量')
BUDGET = re.compile(r'预算|出价|建议|不超过|上限|能量内')


def load():
    return json.loads(RESOURCE.read_text(encoding='utf-8'))


def validate_row(row, event):
    if (not isinstance(row, dict) or row.keys() != REQUIRED
            or any(not isinstance(row[key], str) or not row[key].strip() for key in REQUIRED)):
        raise ValueError(f'{event} 的样例只能包含非空的条件和话术')
    if '拍卖' in event and not any(ENERGY.search(part) and BUDGET.search(part)
                                 for part in re.split(r'[。！？；，]', row['utterance'])):
        raise ValueError(f'{event} 的样例话术须明确写出拍卖预算')


def validate(examples, definitions):
    if not isinstance(examples, dict):
        raise ValueError('样例库须按正式事件组织')
    for event, rows in examples.items():
        if event not in definitions or not isinstance(rows, list):
            raise ValueError(f'样例库的事件未登记或样例不是数组：{event}')
        for row in rows:
            validate_row(row, event)


def main(argv=None):
    parser = argparse.ArgumentParser(description='检查工作流人工话术样例。')
    parser.add_argument('--check', action='store_true', help='校验样例库格式、事件和条件')
    parser.parse_args(argv)
    try:
        definitions = json.loads((HERE / 'references/events.json').read_text(encoding='utf-8'))
        examples = load()
        validate(examples, definitions)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'{sum(map(len, examples.values()))} 条样例，覆盖 {sum(map(bool, examples.values()))}/{len(definitions)} 个正式事件。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
