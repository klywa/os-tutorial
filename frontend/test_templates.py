"""Template domain tests use isolated real catalog files and transactions."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store
from workspace import Conflict
try:
    import templates_store as store
except ModuleNotFoundError:
    store = None


def event():
    return {'id':'custom','name':'自定义', 'parameters':[
        {'id':'p-card','key':'card','name':'卡牌','type':'entity','entity_categories':['heroes']},
        {'id':'p-count','key':'count','name':'数量','type':'number','min':0,'max':10},
        {'id':'p-text','key':'stage','name':'阶段','type':'text','suggestions':['前期','后期']},
        {'id':'p-bool','key':'ready','name':'就绪','type':'boolean'}]}


def group(gid='g1'):
    return {'id':gid,'name':'买牌提醒','event_id':'custom',
        'scope':{'player_id':'player:1','lineup_note_id':'lineup1'},
        'conditions':[{'id':'c1','parameter_key':'card','operator':'eq','value':{'id':'card:1','name':'英雄甲'}}],
        'utterances':[{'id':'u1','text':'买下{card}，{{数量}}：{count}'}],
        'related_entities':[]}


def put(kind, value):
    return {'kind':kind,'action':'put','id':value['id'],'value':value}


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(store, 'template persistence domain is not implemented')
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.catalog=[{'id':'card:1','name':'英雄甲','category':'heroes','description':'旧技能','retrieved_at':'old','image_url':'old.png'},
                      {'id':'card:2','name':'英雄乙','category':'heroes','description':'乙技能'}]
        self.write('entities/heroes.json',self.catalog)
        self.write('entities/players.json',[{'id':'player:1','name':'棋手甲','category':'players','description':'棋手技能'},
                                          {'id':'player:2','name':'棋手乙','category':'players'}])
        self.write('knowledge/index.meta.json',{'notes':[{'id':'lineup1','type':'lineup','player_id':'player:1','title':'阵容'}]})

    def write(self,path,value):
        target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def saved(self):
        return store.apply(self.root,store.snapshot(self.root)['revision'],[put('event',event()),put('group',group())])

    def files(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_seed_and_preview_do_not_write_and_cover_all_event_families(self):
        before=self.files(); snap=store.snapshot(self.root)
        self.assertEqual(len(snap['events']),29)
        self.assertIn('auction_start',{x['id'] for x in snap['events']})
        preview=store.preview_import(self.root,{'kind':'speech-template-library','schema_version':1,'events':[event()],'groups':[group()]})
        self.assertEqual(preview['errors'],[])
        self.assertEqual(len(preview['changes']),2)
        self.assertEqual(self.files(),before)

    def test_export_round_trip_is_portable_filtered_and_import_does_not_delete(self):
        saved=self.saved(); other=group('g2');other['name']='同名不合并'
        store.apply(self.root,saved['revision'],[put('group',other)])
        doc=store.export_library(self.root,['g1'])
        self.assertEqual(set(doc),{'kind','schema_version','events','groups'})
        self.assertEqual([x['id'] for x in doc['events']],['custom'])
        self.assertEqual([x['id'] for x in doc['groups']],['g1'])
        preview=store.preview_import(self.root,doc)
        self.assertEqual(preview['errors'],[])
        self.assertEqual(preview['changes'],[])
        self.assertEqual(len(store.snapshot(self.root)['groups']),2)

    def test_atomic_reject_and_stale_revision_never_overwrite(self):
        saved=self.saved();bad=group();bad['utterances'][0]['text']='{unknown}'
        before=self.files()
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',bad),{'kind':'event','action':'delete','id':'custom'}])
        self.assertEqual(self.files(),before)
        changed=group();changed['name']='新名字'
        newer=store.apply(self.root,saved['revision'],[put('group',changed)])
        with self.assertRaises(Conflict):store.apply(self.root,saved['revision'],[put('group',group())])
        self.assertEqual(store.snapshot(self.root)['revision'],newer['revision'])

    def test_noop_preserves_revision_and_tombstone_prevents_seed_resurrection(self):
        saved=self.saved();same=store.apply(self.root,saved['revision'],[put('group',group())])
        self.assertEqual(saved['revision'],same['revision'])
        deleted=store.apply(self.root,same['revision'],[{'kind':'event','action':'delete','id':'auction_start'}])
        self.assertNotIn('auction_start',{x['id'] for x in deleted['events']})
        self.assertNotIn('auction_start',{x['id'] for x in store.snapshot(self.root)['events']})
        meta=json_store.read(self.root/'templates/library.meta.json')
        self.assertIn('auction_start',meta['tombstones']['event'])
        self.assertTrue(meta['audit'])

    def test_definition_change_validates_all_dependents(self):
        saved=self.saved();changed=event();changed['parameters']=[p for p in changed['parameters'] if p['key']!='card']
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('event',changed)])
        changed=event();changed['parameters'][1]['type']='text'
        bad=group();bad['conditions']=[{'id':'numeric','parameter_key':'count','operator':'gte','value':3}]
        saved=store.apply(self.root,saved['revision'],[put('group',bad)])
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('event',changed)])

    def test_strict_types_categories_placeholders_scope_and_duplicate_ids(self):
        saved=self.saved()
        mutations=[
            lambda g:g['conditions'][0].update(value={'id':'missing','name':'不存在'}),
            lambda g:g['conditions'][0].update(value={'id':'player:1','name':'错类'}),
            lambda g:g['conditions'][0].update(parameter_key='ready',value=1),
            lambda g:g['conditions'][0].update(parameter_key='count',value=True),
            lambda g:g['conditions'][0].update(parameter_key='count',operator='between',value=[4,2]),
            lambda g:g['scope'].update(player_id='player:2'),
            lambda g:g['scope'].update(lineup_note_id='missing'),
            lambda g:g['utterances'][0].update(text='未闭合{card'),
            lambda g:g['utterances'][0].update(text='多余card}'),
            lambda g:g['utterances'][0].update(text='   '),
            lambda g:g['utterances'].append(deepcopy(g['utterances'][0])),
            lambda g:g.update(private_notes='private')]
        for change in mutations:
            with self.subTest(change=change):
                bad=group();change(bad)
                with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',bad)])

    def test_number_hints_are_soft_and_all_numeric_operators_work(self):
        saved=self.saved()
        for op,value in [('eq',20),('ne',20),('gt',20),('gte',20),('lt',20),('lte',20),('between',[-50,50])]:
            g=group();g['conditions']=[{'id':'c1','parameter_key':'count','operator':op,'value':value}]
            saved=store.apply(self.root,saved['revision'],[put('group',g)])
            self.assertEqual(saved['groups'][0]['conditions'][0]['value'],value)

    def test_import_generates_missing_ids_preserves_same_names_and_rejects_metadata(self):
        self.saved();doc={'kind':'speech-template-library','schema_version':1,'events':[event()],'groups':[group()]};del doc['groups'][0]['id']
        del doc['groups'][0]['conditions'][0]['id'];del doc['groups'][0]['utterances'][0]['id']
        preview=store.preview_import(self.root,doc)
        self.assertEqual(preview['errors'],[])
        created=next(c['value'] for c in preview['changes'] if c['kind']=='group')
        self.assertNotEqual(created['id'],'g1');self.assertTrue(created['conditions'][0]['id'])
        doc['groups'][0]['_baseline']={}
        self.assertTrue(store.preview_import(self.root,doc)['errors'])
        doc=store.export_library(self.root);doc['groups'].append(deepcopy(doc['groups'][0]))
        self.assertTrue(store.preview_import(self.root,doc)['errors'])

    def test_preview_changes_does_not_write_or_confirm_warning(self):
        saved=self.saved();before=self.files();g=group();g['name']='预览'
        projected=store.preview_changes(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(projected['groups'][0]['name'],'预览');self.assertEqual(before,self.files())

    def test_semantic_warning_ignores_media_time_and_content_save_does_not_ack(self):
        saved=self.saved();self.assertEqual(store.warnings(self.root),[])
        self.catalog[0].update(image_url='new.png',retrieved_at='new')
        self.write('entities/heroes.json',self.catalog)
        self.assertEqual(store.warnings(self.root),[])
        self.catalog[0]['description']='新技能';self.write('entities/heroes.json',self.catalog)
        warning=store.warnings(self.root)[0]
        self.assertEqual(warning['group_id'],'g1');self.assertEqual(warning['entities'][0]['id'],'card:1')
        g=group();g['name']='改名'
        store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertTrue(store.warnings(self.root))
        with self.assertRaises(Conflict):store.confirm_warning(self.root,'g1',warning['revision'],'admin')
        warning=store.warnings(self.root)[0]
        store.confirm_warning(self.root,'g1',warning['revision'],'admin')
        self.assertEqual(store.warnings(self.root),[])

    def test_stale_entity_confirmation_keeps_new_changes(self):
        self.saved();self.catalog[0]['description']='一改';self.write('entities/heroes.json',self.catalog)
        warning=store.warnings(self.root)[0]
        self.catalog[0]['description']='二改';self.write('entities/heroes.json',self.catalog)
        with self.assertRaises(Conflict):store.confirm_warning(self.root,'g1',warning['revision'],'admin')
        self.assertTrue(store.warnings(self.root))

    def test_partial_catalog_failure_does_not_fake_removal_but_known_deletion_warns(self):
        self.saved();self.write('entities/heroes.json',{'error':'fetch failed'})
        self.assertEqual(store.warnings(self.root),[])
        self.write('entities/heroes.json',[self.catalog[1]])
        warning=store.warnings(self.root)[0]
        self.assertIsNone(warning['entities'][0]['after'])

    def test_automatic_player_and_manual_links_create_baselines(self):
        g=group();g['related_entities']=[{'id':'card:2','name':'英雄乙'}]
        store.apply(self.root,store.snapshot(self.root)['revision'],[put('event',event()),put('group',g)])
        players=json_store.read(self.root/'entities/players.json');players[0]['description']='改棋手'
        self.write('entities/players.json',players)
        self.assertEqual(store.warnings(self.root)[0]['entities'][0]['id'],'player:1')

    def test_journal_recovers_committed_after_image_after_interrupted_file_replace(self):
        saved=self.saved();g=group();g['name']='恢复后的名字'
        original=json_store.write_file
        def fail(path,value):
            if Path(path).as_posix().endswith('/templates/groups/g1.json'):raise OSError('simulated power loss')
            return original(path,value)
        with patch.object(json_store,'write_file',side_effect=fail):
            with self.assertRaises(OSError):store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertTrue((self.root/'raw/templates/pending.json').is_file())
        recovered=store.snapshot(self.root)
        self.assertEqual(recovered['groups'][0]['name'],'恢复后的名字')
        self.assertFalse((self.root/'raw/templates/pending.json').exists())

    def test_published_catalog_fallback_validates_entity_references(self):
        (self.root/'entities/heroes.json').unlink()
        self.write('website-data/cards.json',self.catalog)
        self.assertEqual(len(self.saved()['groups']),1)

    def test_auxiliary_resolution_receipt_commits_with_canonical_batch(self):
        saved=self.saved();before,meta=store._load(self.root)
        after=deepcopy(before);after['groups'][0]['name']='冲突已解决'
        receipt='templates/resolutions/'+'a'*64+'.json'
        from workspace import store_lock
        original=json_store.write_file
        def fail(path,value):
            if Path(path).as_posix().endswith(receipt):raise OSError('resolution interrupted')
            return original(path,value)
        with store_lock(self.root):
            with patch.object(json_store,'write_file',side_effect=fail):
                with self.assertRaises(OSError):
                    store._commit(self.root,before,after,meta,'admin',[],extra_writes={receipt:{'id':'resolution'}})
        self.assertTrue((self.root/'raw/templates/pending.json').exists())
        recovered=store.snapshot(self.root)
        self.assertEqual(recovered['groups'][0]['name'],'冲突已解决')
        self.assertEqual(json_store.read(self.root/receipt),{'id':'resolution'})

    def test_effective_catalog_override_is_used_for_validation_and_baseline(self):
        effective=deepcopy(self.catalog)
        effective[0]['description']='网站更新技能'
        effective+=json_store.read(self.root/'entities/players.json')
        saved=store.apply(self.root,store.snapshot(self.root)['revision'],[put('event',event()),put('group',group())],entities=effective)
        self.assertEqual(store.warnings(self.root,effective),[])
        self.assertTrue(store.warnings(self.root))
        effective[0]['description']='网站再次更新'
        warning=store.warnings(self.root,effective)[0]
        store.confirm_warning(self.root,'g1',warning['revision'],entities=effective)
        self.assertEqual(store.warnings(self.root,effective),[])

    def test_incomplete_effective_catalog_does_not_report_false_deletion(self):
        self.saved()
        players=json_store.read(self.root/'entities/players.json')
        incomplete={'items':players,'complete_categories':['players']}
        self.assertEqual(store.warnings(self.root,incomplete),[])
        complete={'items':players,'complete_categories':['players','heroes']}
        self.assertIsNone(store.warnings(self.root,complete)[0]['entities'][0]['after'])

    def test_malformed_untrusted_changes_raise_value_error_without_writing(self):
        saved=self.saved();before=self.files()
        malformed=[None,{},['bad'],[None],[{'kind':[],'id':'g1','action':'put','value':group()}],
                   [{'kind':'group','id':{},'action':'delete'}],
                   [{'kind':'group','id':'g1','action':{},'value':group()}]]
        for changes in malformed:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],changes)
                self.assertEqual(self.files(),before)

    def test_nonfinite_numbers_rejected_but_large_finite_integer_is_valid(self):
        saved=self.saved()
        g=group();g['conditions']=[{'id':'c1','parameter_key':'count','operator':'eq','value':10**400}]
        result=store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(result['groups'][0]['conditions'][0]['value'],10**400)
        for invalid in (float('inf'),float('nan'),float('-inf')):
            g['conditions'][0]['value']=invalid
            with self.assertRaises(ValueError):store.apply(self.root,result['revision'],[put('group',g)])

    def test_retired_entity_does_not_block_other_groups_or_incremental_repair(self):
        saved=self.saved();saved=store.apply(self.root,saved['revision'],[put('group',group('g2'))])
        self.write('entities/heroes.json',[self.catalog[1]])
        g=group();g['name']='只改名字'
        saved=store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(saved['groups'][0]['name'],'只改名字')
        # Repair g1 while g2 still references the retired card.
        g['conditions'][0]['value']={'id':'card:2','name':'英雄乙'}
        saved=store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(saved['groups'][1]['conditions'][0]['value']['id'],'card:1')
        store.validate(self.root,saved['events'],saved['groups'])
        # A removed old association cannot later be reintroduced as unknown.
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',group())])
        saved=store.apply(self.root,saved['revision'],[{'kind':'group','action':'delete','id':'g2'}])
        self.assertEqual([g['id'] for g in saved['groups']],['g1'])

    def test_retired_association_archive_survives_confirmation_and_rejects_new_links(self):
        saved=self.saved();self.write('entities/heroes.json',[self.catalog[1]])
        warning=store.warnings(self.root)[0]
        store.confirm_warning(self.root,'g1',warning['revision'])
        saved=store.snapshot(self.root);g=group();g['name']='已确认后修改'
        saved=store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(store.warnings(self.root),[])
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',group('new'))])
        bad=deepcopy(g);bad['related_entities']=[{'id':'unseen','name':'从未存在'}]
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',bad)])
        preview=store.preview_import(self.root,store.export_library(self.root,['g1']))
        self.assertEqual(preview['errors'],[])
        self.assertEqual(preview['changes'],[])

    def test_retired_player_scope_remains_maintainable_only_on_existing_group(self):
        self.saved();self.write('entities/players.json',[])
        saved=store.snapshot(self.root);g=group();g['name']='棋手已移除'
        saved=store.apply(self.root,saved['revision'],[put('group',g)])
        self.assertEqual(saved['groups'][0]['scope']['player_id'],'player:1')
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('group',group('new'))])

    def test_legacy_baseline_is_archived_before_deletion_confirmation(self):
        self.saved();meta=json_store.read(self.root/'templates/library.meta.json')
        del meta['entity_archive'];self.write('templates/library.meta.json',meta)
        self.write('entities/heroes.json',[self.catalog[1]])
        warning=store.warnings(self.root)[0]
        store.confirm_warning(self.root,'g1',warning['revision'])
        saved=store.snapshot(self.root);g=group();g['name']='旧库确认后编辑'
        self.assertEqual(store.apply(self.root,saved['revision'],[put('group',g)])['groups'][0]['name'],'旧库确认后编辑')

    def test_retired_suggestions_only_trusted_in_original_event_parameter_slot(self):
        e=event();e['parameters'][0]['suggestions']=[{'id':'card:1','name':'英雄甲'}]
        saved=store.apply(self.root,store.snapshot(self.root)['revision'],[put('event',e)])
        self.write('entities/heroes.json',[self.catalog[1]])
        e['name']='旧建议仍可维护'
        saved=store.apply(self.root,saved['revision'],[put('event',e)])
        store.validate(self.root,saved['events'],saved['groups'])
        new=deepcopy(e);new['id']='another'
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('event',new)])
        new=deepcopy(e);new['parameters'][0]['id']='different-slot'
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('event',new)])
        e['parameters'][0]['suggestions']=[]
        saved=store.apply(self.root,saved['revision'],[put('event',e)])
        e['parameters'][0]['suggestions']=[{'id':'card:1','name':'英雄甲'}]
        with self.assertRaises(ValueError):store.apply(self.root,saved['revision'],[put('event',e)])

    def test_builtin_sidebar_follows_requested_event_order_and_categories(self):
        snap=store.snapshot(self.root)
        self.assertEqual([e['id'] for e in snap['events'][:3]],['hero_buy','hero_deploy','hero_merge'])
        self.assertEqual(list(dict.fromkeys(e['category'] for e in snap['events'])),
                         ['英雄','效果牌','装备','技能牌','商店','升级','战场','准备战斗','关键局势','拍卖开始'])
        saved=self.saved()
        self.assertEqual(saved['revision'],store.snapshot(self.root)['revision'])
        self.assertEqual(saved['events'][0]['id'],'hero_buy')


if __name__=='__main__':unittest.main()
