"""Exercise the exact v3 documents and runtime example bundled in the help UI."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts')]
import templates_store as store
from src.python.condition import evaluate_condition

EXAMPLES = ('speech-template-library-minimal.json', 'speech-template-library.json')


class TemplateHelpTests(unittest.TestCase):
    def test_examples_validate_preview_apply_export_and_roundtrip(self):
        for filename in EXAMPLES:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
                root = Path(folder)
                document = json.loads((ROOT / 'docs/examples' / filename).read_text(encoding='utf-8'))
                self.assertEqual(document['schema_version'], 3)
                preview = store.preview_import(root, document)
                self.assertEqual(preview['errors'], [])
                self.assertFalse((root / store.PUBLISHED).exists())
                stored = store.apply(root, preview['revision'], preview['changes'])
                exported = store.export_library(root, [g['id'] for g in stored['groups']], rules_format=True)
                self.assertEqual(exported['schema_version'], 3)
                self.assertEqual(len(exported['groups']), len(document['groups']))
                exported_groups = {group['name']: group for group in exported['groups']}
                for input_group in document['groups']:
                    output_group = exported_groups[input_group['name']]
                    for key, value in input_group.items():
                        self.assertEqual(output_group[key], value, key)
                    event = input_group['event_name']
                    self.assertIn(event, exported['condition_catalog']['events'])
                    self.assertIn(event, {row['name'] for row in exported['events']})
                again = store.preview_import(root, exported)
                self.assertEqual(again['errors'], [])
                self.assertEqual(again['changes'], [])

    def test_documented_condition_matches_shared_behavior_cases(self):
        doc = (ROOT / 'docs/template-library.md').read_text(encoding='utf-8')
        expression = re.search(r'```text\n(.*?)\n```', doc, re.S).group(1)
        cases = json.loads((ROOT / 'src/condition/cases.json').read_text(encoding='utf-8'))
        matching = [case for case in cases if case['expression'] == expression]
        self.assertTrue({'上阵基准','九级','等级缺失'} <= {c['name'] for c in matching})
        for case in matching:
            self.assertEqual(evaluate_condition(case['event'],expression,case['state']),case['result'])

    def test_documented_workbook_signatures_match_catalog_in_order(self):
        from template_rules import catalog, parse_signature
        doc = (ROOT / 'docs/template-library.md').read_text(encoding='utf-8')
        rows = re.findall(r'^\| ([^|]+) \| `([^`]+\))` \|$',doc,re.M)
        actual = []
        for category,signature in rows:
            name,parameters = parse_signature(signature.replace(r'\|','|'))
            actual.append((category,name,list(parameters.items())))
        self.assertEqual(actual,[(event['category'],name,list(event['parameters'].items()))
                                 for name,event in catalog()['events'].items()])

    def test_canonical_sources_are_bundled(self):
        source = (ROOT / 'frontend/src/templateHelpContent.ts').read_text(encoding='utf-8')
        doc = (ROOT / 'docs/template-library.md').read_text(encoding='utf-8')
        self.assertIn('../../docs/template-library.md?raw', source)
        for name in EXAMPLES:
            self.assertIn('../../docs/examples/' + name + '?raw', source)
        self.assertNotIn('```json',doc)
        for keyword in ('签名','联合型','作用域','主体属性','未知','空列表'):
            self.assertIn(keyword, doc)


if __name__ == '__main__':
    unittest.main()
