"""Verify v3 publication and recovery using real formal and private stores."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tempfile

import test_templates as fixtures
from test_templates_proposals import ADMIN, ALICE, BOB
import templates_http
from templates_proposals import TemplateProposals
import templates_store as store
from src.python.condition import evaluate_condition, choose_utterance


class TemplateRuleTests(unittest.TestCase):
    def test_previous_population_catalog_roundtrip(self):
        package = store.refresh_published(self.root, migrate_events=True)
        player = package['condition_catalog']['types']['玩家']
        for field in ('场上英雄数', '人口上限'):
            self.assertEqual(player.pop(field), 'int')
        self.assertEqual(store.preview_import(self.root, package)['errors'], [])
        player['人口上限'] = 'string'
        self.assertTrue(store.preview_import(self.root, package)['errors'])

    def test_upgrade_keeps_existing_event_collisions_addressable(self):
        for uid,name in [('mine','准备战斗'),('other','准备战斗'),('suffix','准备战斗（兼容 1）')]:
            fixtures.TemplateTests.write(self,'templates/events/'+uid+'.json',{'id':uid,'name':name,'parameters':[]})
        package=store.refresh_published(self.root,migrate_events=True)
        self.assertIn('解释为何准备战斗',package['condition_catalog']['events'])
        names=[e['name'] for e in store.snapshot(self.root)['events']]
        self.assertEqual(len(names),len(set(names)))
        self.assertTrue({'解释为何准备战斗（兼容 2）','解释为何准备战斗（兼容 3）'} <= set(names))
        self.assertEqual(store.refresh_published(self.root),package)

    def test_event_defined_entirely_by_text_signature(self):
        document={'kind':'speech-template-library','schema_version':3,
                  'events':[{'signature':'补充事件( arg1: Array<英雄 | 效果牌>, arg2: 英雄 )'}],
                  'groups':[{'event_name':'补充事件','name':'提示','expression':'arg1 has arg2','utterances':['提示']} ]}
        preview=store.preview_import(self.root,document)
        self.assertEqual(preview['errors'],[])
        saved=store.apply(self.root,preview['revision'],preview['changes'])
        event=next(e for e in saved['events'] if e['name']=='补充事件')
        self.assertEqual([p['dsl_type'] for p in event['parameters']],['Array<英雄|效果牌>','英雄'])

    def test_rename_preserves_existing_binding_and_accepts_old_runtime_name(self):
        old_id = 'os_' + hashlib.sha256('上阵英雄'.encode()).hexdigest()[:16]
        document = {'kind':'speech-template-library','schema_version':3,'events':[],
                    'groups':[{'event_name':'上阵英雄','name':'上阵解释','expression':'arg1 is "弈星"',
                               'utterances':['弈星上阵。']}]}
        preview = store.preview_import(self.root,document)
        self.assertEqual(preview['errors'],[])
        saved = store.apply(self.root,preview['revision'],preview['changes'])
        self.assertEqual(saved['groups'][0]['event_id'],old_id)
        package = store.refresh_published(self.root,migrate_events=True)
        self.assertEqual(package['groups'][0]['event_name'],'解释为何上阵英雄')
        for name in ('上阵英雄','解释为何上阵英雄'):
            self.assertEqual(choose_utterance(package,{'事件':name,'参数':{'arg1':{'名称':'弈星'}}},{}),
                             '弈星上阵。')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=fixtures.ROOT / 'temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = SimpleNamespace(root=self.root)
        fixtures.TemplateTests.write(self, 'entities/heroes.json', [
            {'id':'card:1', 'name':'英雄甲', 'category':'heroes'}])
        fixtures.TemplateTests.write(self, 'entities/players.json', [
            {'id':'player:1', 'name':'棋手甲', 'category':'players'}])
        fixtures.TemplateTests.write(self, 'knowledge/index.meta.json', {'notes':[
            {'id':'lineup1', 'type':'lineup', 'player_id':'player:1', 'title':'阵容甲'}]})

    def get(self, path):
        return templates_http.get(self.server, ADMIN, path, path)

    def published(self):
        return json.loads((self.root / store.PUBLISHED).read_text(encoding='utf-8'))

    def save_legacy(self):
        g = fixtures.group()
        g['conditions'].append({'id':'range', 'parameter_key':'count', 'operator':'between', 'value':[2, 3]})
        g['related_entities'] = [{'id':'card:1', 'name':'英雄甲'}]
        return store.apply(self.root, store.snapshot(self.root)['revision'], [
            fixtures.put('event', fixtures.event()), fixtures.put('group', g)])

    def test_legacy_migration_and_named_runtime_publication(self):
        self.save_legacy()
        view = self.get('/api/templates')['groups'][0]
        document = self.get('/api/templates/published')
        self.assertEqual(document, self.published())
        self.assertEqual(document['schema_version'], 3)
        group = document['groups'][0]
        self.assertEqual(group['scope'], {'player':'棋手甲', 'lineup':'阵容甲'})
        self.assertEqual(group['related_entities'], [{'名称':'英雄甲', '类型':'英雄'}])
        self.assertEqual(group['event_name'], '自定义')
        self.assertEqual(document['condition_catalog']['events']['自定义']['parameters']['card'], '英雄')
        self.assertEqual(group['priority'], 0)
        self.assertEqual(view['condition_tree'], group['condition_tree'])
        self.assertEqual(view['editor_mode'], 'tree')
        self.assertEqual(group['condition_tree']['kind'], 'all')
        self.assertEqual(group['expression'], view['expression'])
        self.assertNotIn('card:1', group['expression'])
        state = {'玩家':{'使用棋手':'棋手甲', '使用阵容':'阵容甲'}}
        for name, number, expected in [('英雄甲',2,True), ('英雄甲',3,True),
                                       ('英雄甲',3.1,False), ('英雄乙',2,False)]:
            event = {'事件':'自定义', '参数':{'card':{'名称':name}, 'count':number}}
            with self.subTest(name=name, number=number):
                self.assertEqual(evaluate_condition(event, group['expression'], state, document), expected)
                self.assertEqual(choose_utterance(document, event, state) is not None, expected)

    def test_filtered_v3_roundtrip_resolves_names_and_preserves_editor_fields(self):
        self.save_legacy()
        document = store.export_library(self.root, ['g1'], rules_format=True)
        self.assertEqual([e['name'] for e in document['events']], ['自定义'])
        group = document['groups'][0]
        group.update(editor_mode='text', expression='玩家.等级 >= count', priority=7, explanation='等级满足事件要求时使用')
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        saved = store.apply(self.root, preview['revision'], preview['changes'])
        stored = saved['groups'][0]
        self.assertEqual(stored['id'], 'g1')
        self.assertEqual(stored['scope'], fixtures.group()['scope'])
        self.assertEqual(stored['expression'], '玩家.等级 >= count')
        again = store.export_library(self.root, ['g1'], rules_format=True)
        self.assertEqual(again, document)
        self.assertEqual(store.preview_import(self.root, again)['changes'], [])

    def test_multicategory_legacy_alias_uses_canonical_name_and_category(self):
        event = fixtures.event()
        event['parameters'][0]['entity_categories'] = ['heroes', 'effect-cards']
        group = fixtures.group()
        group['conditions'][0]['value']['name'] = '甲'
        fixtures.TemplateTests.write(self, 'entities/heroes.json', [
            {'id':'card:1', 'name':'英雄甲', 'aliases':['甲'], 'category':'heroes'}])
        store.apply(self.root, store.snapshot(self.root)['revision'],
                    [fixtures.put('event', event), fixtures.put('group', group)])
        config = self.published()
        expr = config['groups'][0]['expression']
        for kind, expected in [('英雄',True), ('效果牌',False)]:
            with self.subTest(kind=kind):
                input_event = {'事件':'自定义','参数':{'card':{'类型':kind,'名称':'英雄甲'}}}
                self.assertEqual(evaluate_condition(input_event, expr, {}, config), expected)

    def test_private_rule_appears_only_after_approval(self):
        self.save_legacy()
        previous = self.published()
        proposals = TemplateProposals(self.root, self.root / 'raw/private.sqlite3')
        state = store.snapshot(self.root)
        edited = deepcopy(state['groups'][0])
        edited.update(expression='玩家.等级 >= 4', priority=6, editor_mode='text', explanation='等级达到四级时提示')
        proposal = proposals.submit(ALICE, {'revision':state['revision'], 'changes':[fixtures.put('group',edited)]})
        self.assertEqual(proposals.list(BOB), [])
        self.assertEqual(self.published(), previous)
        proposals.action(ADMIN, proposal['id'], 'approve', {'proposal_revision':proposal['proposal_revision']})
        published = self.published()['groups'][0]
        self.assertEqual(published['explanation'], edited['explanation'])
        self.assertEqual((published['expression'], published['priority']), ('玩家.等级 >= 4', 6))

    def test_filtered_export_identifies_only_intended_same_name_group(self):
        saved = self.save_legacy()
        sibling = deepcopy(saved['groups'][0])
        sibling['id'] = 'sibling'
        store.apply(self.root, saved['revision'], [fixtures.put('group', sibling)])
        document = store.export_library(self.root, ['sibling'], rules_format=True)
        self.assertEqual(document['groups'][0]['id'], 'sibling')
        document['groups'][0]['priority'] = 4
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        self.assertEqual([change['id'] for change in preview['changes']], ['sibling'])

    def test_named_references_retain_selected_versions_and_retired_scope(self):
        saved = self.save_legacy()
        fixtures.TemplateTests.write(self, 'entities/heroes.json', [
            {'id':'card:1', 'name':'英雄甲', 'category':'heroes'},
            {'id':'other', 'name':'英雄甲', 'category':'heroes'}])
        fixtures.TemplateTests.write(self, 'entities/players.json', [])
        document = store.export_library(self.root, ['g1'], rules_format=True)
        self.assertEqual(document['groups'][0]['scope']['player'], '棋手甲')
        for heroes in (None, []):
            if heroes is not None:
                fixtures.TemplateTests.write(self, 'entities/heroes.json', heroes)
            preview = store.preview_import(self.root, document)
            self.assertEqual(preview['errors'], [])
            proposed = next(c['value'] for c in preview['changes'] if c['kind'] == 'group')
            self.assertEqual(proposed['scope'], saved['groups'][0]['scope'])
            self.assertEqual(proposed['related_entities'], saved['groups'][0]['related_entities'])
        copy = deepcopy(document)
        copy['groups'][0]['name'] += '副本'
        self.assertTrue(store.preview_import(self.root, copy)['errors'])

    def test_malformed_catalog_parameters_and_duplicate_names_fail_in_preview(self):
        self.save_legacy()
        original = store.export_library(self.root, ['g1'], rules_format=True)
        for change in (lambda d: d['condition_catalog'].update(events=[]),
                       lambda d: d['events'][0].update(parameters=[None]),
                       lambda d: d['groups'].append(deepcopy(d['groups'][0]))):
            document = deepcopy(original)
            change(document)
            result = store.preview_import(self.root, document)
            self.assertTrue(result['errors'])
            self.assertEqual(result['changes'], [])

    def test_interrupted_publication_replays_same_revision(self):
        saved = self.save_legacy()
        group = deepcopy(saved['groups'][0])
        group.update(expression='玩家.等级 >= 4', priority=9, editor_mode='text')
        previous = self.published()
        write = store.json_store.write_file

        def interrupt(path, data):
            if Path(path) == self.root / store.PUBLISHED:
                raise OSError('simulated interruption during publication')
            return write(path, data)

        with patch.object(store.json_store, 'write_file', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'interruption'):
                store.apply(self.root, saved['revision'], [fixtures.put('group', group)])
        self.assertEqual(self.published(), previous)
        self.assertTrue((self.root / store.JOURNAL).is_file())
        recovered = self.get('/api/templates/published')
        self.assertEqual(recovered['groups'][0]['priority'], 9)
        self.assertEqual(recovered, self.published())
        self.assertEqual(recovered, store.export_library(self.root, rules_format=True))
        self.assertFalse(store.recover(self.root))


if __name__ == '__main__':
    unittest.main()
