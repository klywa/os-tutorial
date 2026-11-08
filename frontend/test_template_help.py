"""The exact bundled help examples must import through the real portable v2 importer."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import templates_schema as schema
import templates_store as store


class TemplateHelpTests(unittest.TestCase):
    def test_examples_validate_preview_apply_export_and_roundtrip(self):
        catalog = json.loads((ROOT/'website-data/cards.json').read_text(encoding='utf-8'))
        entities = {row['id']: row for row in catalog}
        builtin_ids = {row['id'] for row in schema.builtin_events()}
        seen = set()
        for filename in ('speech-template-library-minimal.json', 'speech-template-library.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(dir=ROOT/'temp') as folder:
                root = Path(folder)
                document = json.loads((ROOT/'docs/examples'/filename).read_text(encoding='utf-8'))
                context = {} if 'minimal' in filename else entities
                self.assertEqual(document["schema_version"], 2)
                ids = {row['id'] for row in document['events']}
                self.assertFalse(ids & (builtin_ids | seen))
                seen |= ids
                preview = store.preview_import(root, document, entities=context)
                self.assertEqual(preview['errors'], [])
                self.assertFalse((root/'templates').exists(), 'preview cannot write')
                store.apply(root, preview['revision'], preview['changes'], entities=context)
                exported = store.export_library(root, [row['id'] for row in document['groups']])
                self.assertEqual(exported, document)
                self.assertEqual(store.preview_import(root, exported, entities=context)['changes'], [])
                self.assertEqual(set(exported), {'kind','schema_version','events','groups'})
                self.assertTrue(builtin_ids <= {row['id'] for row in store.snapshot(root)['events']})
                if 'minimal' not in filename:
                    self.assertEqual({p['type'] for p in document['events'][0]['parameters']}, {'text','number','boolean','entity'})
                    self.assertGreaterEqual(len(document['groups'][0]['utterances']), 2)
                    self.assertIsInstance(document['groups'][0]['conditions'][-1]['value'], str)
                    self.assertNotIn('related_entities', document['groups'][0])
                # No-ID nested rows are supported by import (not canonical validation).
                fresh = deepcopy(exported)
                del fresh['groups'][0]['id']
                for event in fresh['events']: event.pop('id')
                for group in fresh['groups']:
                    group.pop('event_id')
                    group['event_name'] = fresh['events'][0]['name']
                self.assertEqual(store.preview_import(root, fresh, entities=context)['errors'], [])

    def test_canonical_sources_are_bundled_without_a_file_read_endpoint(self):
        source = (ROOT/'frontend/src/templateHelpContent.ts').read_text(encoding='utf-8')
        doc = (ROOT/'docs/template-library.md').read_text(encoding='utf-8')
        self.assertIn('../../docs/template-library.md?raw', source)
        for name in ('speech-template-library-minimal.json','speech-template-library.json'):
            self.assertIn('../../docs/examples/'+name+'?raw', source)
            self.assertIn('examples/'+name, doc)
        for keyword in ('schema_version','entity_categories','parameter_key','related_entities','between','{{','私有提案','未知字段'):
            self.assertIn(keyword, doc)


if __name__ == '__main__': unittest.main()
