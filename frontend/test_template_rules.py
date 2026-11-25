"""Verify v3 publication and recovery using real formal and private stores."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import tempfile

import test_templates as fixtures
from test_templates_proposals import ADMIN, ALICE, BOB
import templates_http
from templates_proposals import TemplateProposals
import templates_store as store
from src.python.condition import evaluate_condition, choose_utterance


class TemplateRuleTests(unittest.TestCase):
    def test_v04_publication_filters_mode_and_season_before_building_runtime(self):
        event='解释为何购买英雄'
        common={'name':'首个配合','event_name':event,'syntax_version':'0.4','extra_key':'小乔',
                'expression':'对局.当前回合数 >= 3','mode':['万象大赛'],
                'utterances':[{'id':'line','text':'给后续登场留出配合。'}]}
        document={'kind':'speech-template-library','schema_version':3,'events':[],'groups':[
            {**common,'id':'shared','version':['S1','S2']},
            {**common,'id':'seasonOne','version':['S1']},
            {**common,'id':'seasonTwo','version':'S2'},
            {**common,'id':'otherMode','version':['S1','S2'],'mode':'万象速决'},
        ]}
        preview=store.preview_import(self.root,document)
        self.assertEqual(preview['errors'],[])
        store.apply(self.root,preview['revision'],preview['changes'])
        cached=(self.root/store.PUBLISHED).read_bytes()
        path='/api/templates/published'
        for season,mode,expected in [('S1','万象大赛',{'shared','seasonOne'}),
                                     ('S2','万象大赛',{'shared','seasonTwo'}),
                                     ('S2','万象速决',{'otherMode'}),('S2','未知模式',set())]:
            with self.subTest(season=season,mode=mode):
                query=urlencode({'season':season,'mode':mode})
                document=templates_http.get(self.server,ADMIN,path,path+'?'+query)
                groups=document['解释事件'].get(event,{}).get('小乔',[])
                self.assertEqual({group['id'] for group in groups},expected)
        with patch.object(store,'_published_document',side_effect=ValueError('模拟作用域发布失败')):
            query=urlencode({'season':'S1','mode':'万象大赛'})
            with self.assertRaisesRegex(ValueError,'模拟作用域发布失败'):
                templates_http.get(self.server,ADMIN,path,path+'?'+query)
        self.assertEqual((self.root/store.PUBLISHED).read_bytes(),cached)

    def test_numeric_reference_roundtrips_without_display_substitution(self):
        count = '玩家.战场.计数(阵营, "无阵营")'
        line = f'场上有{{{count}}}名无阵营英雄。'
        group = {'event_name':'解释为何选择天赋','name':'无阵营人数',
                 'expression':f'arg2 is "协同一致" and {count} >= 2','utterances':[line]}
        document = {'kind':'speech-template-library','schema_version':3,'events':[],'groups':[group]}
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        store.apply(self.root, preview['revision'], preview['changes'])
        saved = self.get('/api/templates')
        self.assertEqual(saved['groups'][0]['utterances'][0]['text'], line)
        self.assertNotIn(saved['groups'][0]['id'], saved['utterance_bindings'])
        self.assertEqual(self.get('/api/templates/published')['groups'][0]['utterances'], [line])
        group['expression'] = f'{count} >= 2 or arg2 is "协同一致"'
        self.assertTrue(store.preview_import(self.root, document)['errors'])

    def test_literal_membership_references_roundtrip_and_project_choices(self):
        event = '解释为何选择天赋'
        expression = 'arg2 is "穷兵黩武" and 玩家.主C in ["嬴政","蒙犽","孙膑"]'
        line = '选穷兵黩武，{玩家.主C}施法能召唤玄雍士兵。'
        group = {'event_name':event,'name':'主力施法', 'expression':expression,'utterances':[line]}
        document = {'kind':'speech-template-library','schema_version':3,'events':[],'groups':[group]}
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        store.apply(self.root, preview['revision'], preview['changes'])
        saved = self.get('/api/templates')
        uid = saved['groups'][0]['id']
        self.assertEqual(saved['utterance_bindings'][uid], {'玩家.主C':['嬴政','蒙犽','孙膑']})
        self.assertEqual(saved['groups'][0]['utterances'][0]['text'], line)
        self.assertEqual(self.get('/api/templates/published')['groups'][0]['utterances'], [line])
        group['expression'] = '玩家.主C in ["嬴政"] or arg2 is "穷兵黩武"'
        self.assertEqual(store.preview_import(self.root, document)['errors'], [])

    def test_direct_entity_names_roundtrip_without_membership(self):
        line = '{玩家.主C}对上{对局.当前对手.主C.名称}，可走{玩家.当前阵容}。'
        group = {'event_name':'解释为何上阵英雄','name':'实体名称',
                 'expression':'arg1 is "韩信"','utterances':[line]}
        document = {'kind':'speech-template-library','schema_version':3,'events':[],'groups':[group]}
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        store.apply(self.root, preview['revision'], preview['changes'])
        published = self.get('/api/templates/published')
        self.assertEqual(published['groups'][0]['utterances'], [line])
        self.assertEqual(store.preview_import(self.root, published)['errors'], [])
        for path in ('玩家.战场','玩家.不存在','对局','玩家.当前阵容.阵容名'):
            group['utterances'] = ['{' + path + '}。']
            self.assertIn(path,store.preview_import(self.root, document)['errors'][0])

    def test_unit_alias_catalog_still_imports(self):
        package = store.refresh_published(self.root)
        catalog = package['condition_catalog']
        catalog.pop('unit_types')
        catalog['types'].pop('单位')
        catalog['types']['玩家'].pop('已选天赋')
        catalog['types']['英雄'].pop('已穿装备')
        catalog['operations'].pop('单位.标签')
        catalog['aliases'] = {'单位': '英雄'}
        preview = store.preview_import(self.root, package)
        self.assertEqual(preview['errors'], [])
        self.assertEqual(preview['changes'], [])
        catalog['aliases']['单位'] = '天赋'
        self.assertTrue(store.preview_import(self.root, package)['errors'])

    def test_previous_population_catalog_roundtrip(self):
        package = store.refresh_published(self.root, migrate_events=True)
        player = package['condition_catalog']['types']['玩家']
        for field in ('场上英雄数', '人口上限'):
            self.assertEqual(player.pop(field), 'int')
        self.assertEqual(store.preview_import(self.root, package)['errors'], [])
        player['人口上限'] = 'string'
        self.assertTrue(store.preview_import(self.root, package)['errors'])

    def test_retired_events_stay_removed_and_history_is_preserved(self):
        saved = self.save_legacy()
        history = store._load(self.root)[1]['audit']
        for uid,name in [('hero_buy','解释为何购买英雄（旧版）'), ('extra','自定义（旧版）')]:
            fixtures.TemplateTests.write(self,'templates/events/'+uid+'.json',
                                         {'id':uid,'name':name,'parameters':[]})
        for _ in range(2):
            published = store.refresh_published(self.root,migrate_events=True)
            self.assertFalse(any(name.endswith('（旧版）') for name in published['condition_catalog']['events']))
            self.assertFalse((self.root/'templates/events/hero_buy.json').exists())
            self.assertFalse((self.root/'templates/events/extra.json').exists())
            self.assertEqual(store.snapshot(self.root)['groups'], saved['groups'])
            self.assertEqual(store._load(self.root)[1]['audit'], history)
            self.assertIn('解释为何选择英雄牌',published['condition_catalog']['events'])

    def test_fresh_library_preserves_every_unmarked_legacy_seed(self):
        events = store.snapshot(self.root)['events']
        expected = {'auction_start','dangerous_opponent',
                    'health_crisis','hero_select','hero_sell_board','key_card_acquired',
                    'key_card_shop','lineup_ready','opponent_equipment','opponent_streak',
                    'player_streak','unit_move'}
        self.assertEqual({e['id'] for e in events if not e['id'].startswith('os_')},expected)
        sale = next(e for e in events if e['id']=='hero_sell_board')
        self.assertEqual(sale['name'],'解释为何从场上出售英雄')
        self.assertEqual([p['key'] for p in sale['parameters']],['situation','stage','hero'])
        self.assertIn('解释为何从战场出售英雄',{e['name'] for e in events})

    def test_reminders_preserve_ids_and_accept_prior_portable_names(self):
        names = dict(lineup_ready='阵容成型', health_crisis='血量危机', player_streak='玩家连胜',
                     opponent_streak='对手连胜', dangerous_opponent='高危对手',
                     opponent_equipment='对手关键装备', key_card_acquired='获得关键卡牌',
                     key_card_shop='商店刷出关键卡牌', auction_start='拍卖开始')
        events = {e['id']:e for e in store.snapshot(self.root)['events']}
        for event_id, name in names.items():
            event = events[event_id]
            self.assertEqual((event['name'], event['category']), (name, '针对与提醒'))
            fixtures.TemplateTests.write(self, 'templates/events/'+event_id+'.json',
                                         {**event,'name':'解释为何'+name,'category':'解释类'})
        package = store.refresh_published(self.root)
        catalog = package['condition_catalog']['events']
        for event in package['events']:
            if event['name'] not in names.values():
                continue
            name = event['name']
            self.assertEqual(catalog[name]['category'], '针对与提醒')
            event['name'] = '解释为何'+name
            event['category'] = '解释类'
            if 'signature' in event:
                event['signature'] = '解释为何'+event['signature']
            catalog[event['name']] = {**catalog.pop(name),'category':'解释类'}
        preview = store.preview_import(self.root, package)
        self.assertEqual(preview['errors'], [])
        self.assertEqual(preview['changes'], [])

    def test_archive_dependent_groups_atomically_on_old_library_upgrade(self):
        saved = self.save_legacy()
        event = {**fixtures.event(),'id':'obsolete','name':'测试用事件（旧版）'}
        fixtures.TemplateTests.write(self,'templates/events/obsolete.json',event)
        groups = [{**fixtures.group(uid),'event_id':eid} for uid,eid in
                  [('file_group','obsolete'),('virtual_group','hero_buy')]]
        for group in groups:
            fixtures.TemplateTests.write(self,'templates/groups/'+group['id']+'.json',group)
        self.assertEqual(self.get('/api/templates')['groups'][0]['id'],saved['groups'][0]['id'])
        self.assertEqual(len(store.export_library(self.root,rules_format=True)['groups']),1)
        with patch.object(store,'_recover_locked',side_effect=[False,OSError('interrupted')]):
            with self.assertRaises(OSError):
                store.refresh_published(self.root,migrate_events=True)
        recovered = store.snapshot(self.root)
        self.assertEqual(recovered['groups'],saved['groups'])
        archive = store._load(self.root)[1]['tombstones']
        self.assertEqual(archive['event']['obsolete']['record'],event)
        for group in groups:
            self.assertEqual(archive['group'][group['id']]['record'],group)
            self.assertFalse((self.root/'templates/groups'/(group['id']+'.json')).exists())
        self.assertEqual(store.refresh_published(self.root),self.published())
        self.assertEqual(store.snapshot(self.root),recovered)

    def test_custom_active_event_using_retired_id_keeps_groups(self):
        custom = {**fixtures.event(),'id':'hero_buy'}
        group = {**fixtures.group(),'event_id':'hero_buy'}
        snapshot = store.apply(self.root,store.snapshot(self.root)['revision'],
                               [fixtures.put('event',custom),fixtures.put('group',group)])
        store.refresh_published(self.root)
        self.assertEqual(store.snapshot(self.root)['groups'],snapshot['groups'])

    def test_pre_lineup_catalog_still_imports(self):
        package = store.refresh_published(self.root)
        catalog = package['condition_catalog']
        catalog['types'].pop('阵容')
        catalog['types']['玩家'].pop('当前阵容')
        catalog['operations'].pop('阵容.阵容名')
        name = '解释为何建议向某阵容发展'
        catalog['events'].pop(name)
        package['events'] = [event for event in package['events'] if event['name'] != name]
        old_name = '解释为何准备战斗（旧版）'
        package['events'].append({'name':old_name,'category':'解释类','parameters':[]})
        catalog['events'][old_name] = {'category':'解释类','parameters':{}}
        preview = store.preview_import(self.root, package)
        self.assertEqual(preview['errors'], [])
        self.assertEqual(preview['changes'], [])
        package['groups'] = [{'name':'旧提醒','event_name':old_name,'expression':'','utterances':['提示']}]
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
        self.assertIn('玩家.使用棋手 is "棋手甲"', group['effective_expression'])
        self.assertIn('玩家.使用阵容 is "阵容甲"', group['effective_expression'])
        self.assertNotIn('card:1', group['expression'])
        state = {'玩家':{'使用棋手':'棋手甲', '使用阵容':'阵容甲'}}
        for name, number, expected in [('英雄甲',2,True), ('英雄甲',3,True),
                                       ('英雄甲',3.1,False), ('英雄乙',2,False)]:
            event = {'事件':'自定义', '参数':{'card':{'名称':name}, 'count':number}}
            with self.subTest(name=name, number=number):
                self.assertEqual(evaluate_condition(event, group['expression'], state, document), expected)
                self.assertEqual(evaluate_condition(event, group['effective_expression'], state, document), expected)
                self.assertFalse(evaluate_condition(event, group['effective_expression'], {}, document))
                self.assertEqual(choose_utterance(document, event, state) is not None, expected)

    def test_filtered_v3_roundtrip_resolves_names_and_preserves_editor_fields(self):
        self.save_legacy()
        document = store.export_library(self.root, ['g1'], rules_format=True)
        self.assertEqual([e['name'] for e in document['events']], ['自定义'])
        group = document['groups'][0]
        group.update(editor_mode='text', expression='玩家.等级 >= count', priority=7, explanation='等级满足事件要求时使用',
                     version='s1', mode='万象大赛', tags=['技巧'], explanation_before='区分触发时点',
                     explanation_source='笔记原文', explanation_after='核对等级阈值')
        preview = store.preview_import(self.root, document)
        self.assertEqual(preview['errors'], [])
        saved = store.apply(self.root, preview['revision'], preview['changes'])
        stored = saved['groups'][0]
        self.assertEqual(stored['id'], 'g1')
        self.assertEqual(stored['scope'], fixtures.group()['scope'])
        self.assertEqual(stored['expression'], '玩家.等级 >= count')
        again = store.export_library(self.root, ['g1'], rules_format=True)
        self.assertNotEqual(document['groups'][0]['effective_expression'], again['groups'][0]['effective_expression'])
        document['groups'][0]['effective_expression'] = again['groups'][0]['effective_expression']
        self.assertEqual(again, document)
        self.assertEqual(store.preview_import(self.root, again)['changes'], [])

    def test_read_cache_revalidates_external_files_and_warning_entities(self):
        self.save_legacy()
        before = self.get('/api/templates')
        self.assertEqual(before['scope_names']['lineup1'], '阵容甲')
        self.assertEqual(self.get('/api/templates/warnings')['items'], [])
        with patch.object(store,'_load',side_effect=AssertionError('unchanged files reread')):
            self.assertEqual(self.get('/api/templates'), before)
            self.assertEqual(self.get('/api/templates/warnings')['items'], [])
        record = self.root/'templates/groups/g1.json'
        group = json.loads(record.read_text('utf8'))
        fixtures.TemplateTests.write(self, 'templates/groups/g1.json', {**group,'name':'同步后的新组名'})
        self.assertEqual(self.get('/api/templates')['groups'][0]['name'], '同步后的新组名')
        fixtures.TemplateTests.write(self, 'entities/heroes.json', [
            {'id':'card:1','name':'英雄甲','category':'heroes','description':'同步后的技能'}])
        self.assertEqual(self.get('/api/templates/warnings')['items'][0]['group_id'], 'g1')

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
