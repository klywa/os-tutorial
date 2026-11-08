"""Template merges exercise real disposable Git trees and record conflicts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'frontend'),str(ROOT/'deploy'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]

import templates_sync as sync


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


class TemplateMergeTests(unittest.TestCase):
    def test_derived_version_bindings_survive_metadata_merge(self):
        selector={'key':'hero','name':'英雄','anchor':'h1','categories':['heroes']}
        def tree(ids):return {'templates/library.meta.json':{'entity_bindings':{'g':{'c':{'selector':selector,'ids':ids}}}}}
        merged=sync._metadata([tree(['h1']),tree(['h1','h2']),tree(['h1','h3'])])
        self.assertEqual(merged['entity_bindings']['g']['c']['ids'],['h1','h2','h3'])

    def setUp(self):
        folder=ROOT/'raw/tests/templates-sync';folder.mkdir(parents=True,exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def record(self):
        return {'id': 'g', 'name': '原名', 'event_id': 'e', 'conditions': [
            {'id': 'c1', 'parameter': 'level', 'op': 'eq', 'value': 1},
            {'id': 'c2', 'parameter': 'round', 'op': 'eq', 'value': 2}],
            'utterances': [{'id': 'u', 'text': '原话'}]}

    def test_stable_child_ids_and_independent_fields_merge(self):
        base = self.record(); left = deepcopy(base); right = deepcopy(base)
        left['name'] = '新名'; left['conditions'][0]['value'] = 3
        right['conditions'][1]['value'] = 4; right['utterances'][0]['text'] = '新话'
        result = sync.merge_record(base, left, right)
        self.assertEqual(result['conflicts'], [])
        self.assertEqual(result['record']['name'], '新名')
        self.assertEqual([c['value'] for c in result['record']['conditions']], [3, 4])
        self.assertEqual(result['record']['utterances'][0]['text'], '新话')

    def test_same_field_and_delete_edit_keep_current_whole_record(self):
        base = self.record(); left = deepcopy(base); right = deepcopy(base)
        left['name'] = '网站'; right['name'] = '本地'
        result = sync.merge_record(base, left, right, preferred='left')
        self.assertTrue(result['conflicts']); self.assertEqual(result['record'], left)
        result = sync.merge_record(base, None, right, preferred='left')
        self.assertTrue(result['conflicts']); self.assertIsNone(result['record'])

    def test_parameter_keys_merge_and_competing_order_is_conflict(self):
        base = {'id':'e','parameters':[{'key':'a','name':'甲'},{'key':'b','name':'乙'},{'key':'c','name':'丙'}]}
        left = deepcopy(base); right = deepcopy(base)
        left['parameters'][0]['name'] = '新甲'; right['parameters'][1]['name'] = '新乙'
        self.assertFalse(sync.merge_record(base,left,right)['conflicts'])
        left['parameters'] = [left['parameters'][1],left['parameters'][0],left['parameters'][2]]
        right['parameters'] = [right['parameters'][0],right['parameters'][2],right['parameters'][1]]
        self.assertTrue(sync.merge_record(base,left,right)['conflicts'])

    def test_real_git_merge_pins_pending_conflict_and_resolution_does_not_revive(self):
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        path=self.root/'templates/groups/g.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.record()),encoding='utf-8')
        git(self.root,'add','.');git(self.root,'commit','-m','base');base=git(self.root,'rev-parse','HEAD')
        left=self.record();left['name']='网站';path.write_text(json.dumps(left),encoding='utf-8')
        git(self.root,'commit','-am','left');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        right=self.record();right['name']='本地';path.write_text(json.dumps(right),encoding='utf-8')
        git(self.root,'commit','-am','right');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        sync.integrate(self.root,base,lref,rref,preferred='left',validate=False)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['name'],'网站')
        conflict=sync.list_conflicts(self.root)['items'][0]
        self.assertTrue(sync.is_blocked(self.root,'group','g'))
        sync.integrate(self.root,base,lref,rref,preferred='left',validate=False)
        self.assertEqual(sync.list_conflicts(self.root)['items'][0]['revision'],conflict['revision'])
        # Immutable resolution events cover exact requests, including after a later import.
        resolved={**left,'name':'人工解决'}
        sync._write_resolution(self.root,conflict,resolved,'admin')
        self.assertFalse(sync.is_blocked(self.root,'group','g'))
        sync.integrate(self.root,base,lref,rref,preferred='left',validate=False)
        self.assertEqual(sync.list_conflicts(self.root)['items'],[])
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['name'],'人工解决')

    def test_public_whitelist_excludes_private_and_traversal(self):
        from website_sync import allowed_path
        from deploy.local_sync import allowed_local_path
        for path in ('templates/events/e.json','templates/groups/g.json','templates/library.meta.json','templates/conflicts/'+('a'*64)+'.json'):
            self.assertTrue(allowed_path(path),path);self.assertTrue(allowed_local_path(path),path)
        for path in ('raw/templates/pending.json','templates/../raw/a.json','templates/groups/a/b.json','templates/proposals/private.json'):
            self.assertFalse(allowed_path(path),path);self.assertFalse(allowed_local_path(path),path)

    def test_backup_preserves_templates_and_private_proposal_wal(self):
        import sqlite3
        from contextlib import closing
        from deploy.update_sites import snapshot_os
        state=self.root/'state';state.mkdir()
        group=self.root/'templates/groups/g.json';group.parent.mkdir(parents=True);group.write_text('{"id":"g"}',encoding='utf-8')
        with closing(sqlite3.connect(state/'template-proposals.sqlite3')) as connection:
            connection.execute('pragma journal_mode=WAL')
            connection.execute('create table proposals(body text)')
            connection.execute("insert into proposals values ('私有草稿')");connection.commit()
            destination=self.root/'backup'
            snapshot_os(self.root,state,destination)
            self.assertEqual(json.loads((destination/'templates/groups/g.json').read_text(encoding='utf-8')),{'id':'g'})
            with closing(sqlite3.connect(destination/'template-proposals.sqlite3')) as backup:
                self.assertEqual(backup.execute('select body from proposals').fetchall(),[('私有草稿',)])
            self.assertFalse((destination/'template-proposals.sqlite3-wal').exists())

    def test_formal_fingerprint_detects_same_path_edits_and_pending_journal(self):
        first=sync.fingerprint(self.root)
        self.assertFalse((self.root/'templates').exists())
        path=self.root/'templates/groups/g.json';path.parent.mkdir(parents=True);path.write_text('{"id":"g"}',encoding='utf-8')
        second=sync.fingerprint(self.root);self.assertNotEqual(first,second)
        path.write_text('{"id":"g","name":"新"}',encoding='utf-8')
        self.assertNotEqual(second,sync.fingerprint(self.root))
        before=sync.fingerprint(self.root)
        pending=self.root/'raw/templates/pending.json';pending.parent.mkdir(parents=True);pending.write_text('{}',encoding='utf-8')
        self.assertNotEqual(before,sync.fingerprint(self.root))

    def test_resolution_is_revision_fenced_and_only_target_record_is_locked(self):
        import templates_store as library
        from workspace import Conflict
        group={'id':'g','name':'网站','event_id':'shop_refresh','scope':{'player_id':None,'lineup_note_id':None},'conditions':[],'utterances':[{'id':'u','text':'刷新'}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':group}],actor='admin')
        incoming={**group,'name':'本地'}
        request={'schema_version':1,'kind':'group','record_id':'g','base':{**group,'name':'原名'},'current':group,'incoming':incoming,'conflicts':['/name']}
        request['id']=sync._digest(request);sync._immutable(self.root,'conflicts',request)
        item=sync.list_conflicts(self.root)['items'][0]
        with self.assertRaises(Conflict):
            library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':incoming}],actor='admin')
        other={**group,'id':'other'}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'other','value':other}],actor='admin')
        with self.assertRaises(Conflict):sync.resolve_conflict(self.root,item['id'],'stale',incoming,'admin')
        result=sync.resolve_conflict(self.root,item['id'],item['revision'],incoming,'admin')
        self.assertEqual(next(g['name'] for g in result['groups'] if g['id']=='g'),'本地')
        self.assertFalse(sync.is_blocked(self.root,'group','g'))
        with self.assertRaises(Conflict):sync.resolve_conflict(self.root,item['id'],item['revision'],group,'admin')

    def test_resolution_validation_rejects_unknown_request(self):
        request={'id':'c','revision':'r','kind':'group','record_id':'g','request_ids':['a'*64]}
        sync._write_resolution(self.root,request,None,'admin')
        with self.assertRaisesRegex(ValueError,'引用'):sync.validate_events(self.root)

    def test_resolution_content_and_receipt_recover_together_after_power_loss(self):
        import templates_store as library
        import json_store
        group={'id':'g','name':'网站','event_id':'shop_refresh','scope':{'player_id':None,'lineup_note_id':None},'conditions':[],'utterances':[{'id':'u','text':'刷新'}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':group}],actor='admin')
        incoming={**group,'name':'本地'}
        request={'schema_version':1,'kind':'group','record_id':'g','base':{**group,'name':'原名'},'current':group,'incoming':incoming,'conflicts':['/name']}
        request['id']=sync._digest(request);sync._immutable(self.root,'conflicts',request)
        conflict=sync.list_conflicts(self.root)['items'][0]
        write=json_store.write_file
        def power_loss(path,value):
            if Path(path).parent.name=='resolutions':raise OSError('模拟掉电')
            return write(path,value)
        with patch.object(json_store,'write_file',side_effect=power_loss):
            with self.assertRaises(OSError):sync.resolve_conflict(self.root,conflict['id'],conflict['revision'],incoming,'admin')
        self.assertTrue((self.root/'raw/templates/pending.json').exists())
        result=library.snapshot(self.root)
        self.assertEqual(result['groups'][0]['name'],'本地')
        self.assertFalse(sync.is_blocked(self.root,'group','g'))

    def test_canonical_git_handler_merges_template_json_before_code_conflict_check(self):
        import json_store
        import knowledge_git
        import templates_store as library
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\nentities/\n*.bak\n*.tmp\n',encoding='utf-8');json_store.initialize(self.root)
        group={'id':'g','name':'原名','event_id':'shop_refresh','scope':{'player_id':None,'lineup_note_id':None},'conditions':[{'id':'c','parameter_key':'stage','operator':'eq','value':'前期'}],'utterances':[{'id':'u','text':'刷新'}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':group}],actor='admin')
        git(self.root,'add','.');git(self.root,'commit','-m','base');base=git(self.root,'rev-parse','HEAD')
        left=deepcopy(group);left['conditions'][0]['value']='中期'
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':left}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','left');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        right=deepcopy(group);right['utterances'][0]['text']='网站刷新'
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':right}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','right');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        result=knowledge_git.merge_branches(self.root,lref,rref,preferred='left')
        self.assertTrue(result['handled']);self.assertEqual(result['conflict_template_ids'],[])
        merged=library.snapshot(self.root)['groups'][0]
        self.assertEqual(merged['conditions'][0]['value'],'中期');self.assertEqual(merged['utterances'][0]['text'],'网站刷新')
        self.assertEqual(git(self.root,'status','--porcelain'),'')

    def test_cross_record_parameter_delete_and_new_condition_conflict_pins_serving_group(self):
        import templates_store as library
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\n*.bak\n*.tmp\n',encoding='utf-8')
        event={'id':'e','name':'测试','parameters':[{'id':'pa','key':'a','name':'数值','type':'number'}]}
        group={'id':'g','name':'组','event_id':'e','scope':{'player_id':None,'lineup_note_id':None},'conditions':[],'utterances':[{'id':'u','text':'刷新'}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':event},{'kind':'group','action':'put','id':'g','value':group}],actor='admin')
        git(self.root,'add','.');git(self.root,'commit','-m','base');base=git(self.root,'rev-parse','HEAD')
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':{**event,'parameters':[]}}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','website delete parameter');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        changed={**group,'conditions':[{'id':'c','parameter_key':'a','operator':'eq','value':1}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':changed}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','local add condition');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        sync.integrate(self.root,base,lref,rref,preferred='left')
        self.assertEqual(library.snapshot(self.root)['groups'][0]['conditions'],[])
        self.assertTrue(sync.is_blocked(self.root,'group','g'))
        self.assertFalse(sync.is_blocked(self.root,'event','e'))

    def test_virtual_builtin_delete_edit_conflict_does_not_resurrect_deleted_event(self):
        import templates_store as library
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\n*.bak\n*.tmp\n',encoding='utf-8')
        git(self.root,'add','.');git(self.root,'commit','-m','unseeded base');base=git(self.root,'rev-parse','HEAD')
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'delete','id':'hero_buy'}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','website delete builtin');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        event=next(e for e in library.snapshot(self.root)['events'] if e['id']=='hero_buy');event['name']='本地新名'
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'hero_buy','value':event}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','local edit builtin');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        sync.integrate(self.root,base,lref,rref,preferred='left')
        self.assertNotIn('hero_buy',[e['id'] for e in library.snapshot(self.root)['events']])
        self.assertTrue(sync.is_blocked(self.root,'event','hero_buy'))

    def test_new_conflict_versions_are_causally_ordered_even_with_lower_hash(self):
        first={'schema_version':1,'kind':'group','record_id':'g','base':None,'current':{'id':'g','name':'网站'},'incoming':{'id':'g','name':'旧本地'},'conflicts':['/name']}
        first['id']=sync._digest(first);sync._immutable(self.root,'conflicts',first)
        for n in range(1000):
            second={**{k:v for k,v in first.items() if k!='id'},'incoming':{'id':'g','name':'新版'+str(n)},'parents':[first['id']]}
            second['id']=sync._digest(second)
            if second['id']<first['id']:break
        sync._immutable(self.root,'conflicts',second)
        item=sync.list_conflicts(self.root)['items'][0]
        self.assertEqual(item['incoming'],second['incoming'])
        self.assertEqual([r['id'] for r in item['versions']],[first['id'],second['id']])
        self.assertEqual([r['id'] for r in item['frontier']],[second['id']])

    def test_confirmation_baselines_merge_three_way_without_hiding_concurrent_changes(self):
        base={'templates/library.meta.json':{'baselines':{'g':{'hero':{'effect':'旧'}}}}}
        left=deepcopy(base);right=deepcopy(base)
        right['templates/library.meta.json']['baselines']['g']['hero']={'effect':'已确认的新'}
        result=sync._metadata([base,left,right],preferred='left')
        self.assertEqual(result['baselines']['g']['hero'],{'effect':'已确认的新'})
        left['templates/library.meta.json']['baselines']['g']['hero']={'effect':'另一端独立确认'}
        result=sync._metadata([base,left,right],preferred='left')
        self.assertEqual(result['baselines']['g']['hero'],{'effect':'旧'})

    def test_retired_reference_archives_merge_per_group_and_entity(self):
        base={'templates/library.meta.json':{'entity_archive':{'g':{'h':{'id':'h','name':'旧英雄','category':'heroes'}}}}}
        left=deepcopy(base);right=deepcopy(base)
        left['templates/library.meta.json']['entity_archive']['g']['player']={'id':'player','name':'棋手','category':'players'}
        right['templates/library.meta.json']['entity_archive']['other']={'h':{'id':'h','name':'旧英雄','category':'heroes'}}
        result=sync._metadata([base,left,right],preferred='left')
        self.assertEqual(result['entity_archive']['g']['h']['category'],'heroes')
        self.assertEqual(result['entity_archive']['g']['player']['name'],'棋手')
        self.assertEqual(result['entity_archive']['other']['h']['name'],'旧英雄')
        for tree in (base,left,right):
            tree['templates/library.meta.json']['event_entity_archive']={'e':{'p':{'h':{'id':'h','name':'旧英雄','category':'heroes'}}}}
        right['templates/library.meta.json']['event_entity_archive']['e']['p']['h2']={'id':'h2','name':'另一英雄','category':'heroes'}
        result=sync._metadata([base,left,right],preferred='left')
        self.assertEqual(result['event_entity_archive']['e']['p']['h']['name'],'旧英雄')
        self.assertEqual(result['event_entity_archive']['e']['p']['h2']['name'],'另一英雄')

    def test_retired_event_suggestions_survive_independent_git_edits(self):
        import json_store
        import templates_store as library
        import website_data
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\nentities/\n*.bak\n*.tmp\n',encoding='utf-8');json_store.initialize(self.root)
        hero={'id':'hero:retired','name':'旧英雄','category':'heroes'}
        json_store.write_file(self.root/'entities/heroes.json',[hero])
        event={'id':'e','name':'事件','parameters':[{'id':'ph','key':'hero','name':'英雄','type':'entity','entity_categories':['heroes'],
                'suggestions':[{'id':hero['id'],'name':hero['name']}]}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':event}],actor='admin')
        json_store.write_file(self.root/'entities/heroes.json',[])
        git(self.root,'add','.');git(self.root,'commit','-m','retired event suggestion');base=git(self.root,'rev-parse','HEAD')
        left={**event,'name':'网站名称'}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':left}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','website edit');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        right=deepcopy(event);right['parameters'][0]['name']='本地参数名称'
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':right}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','local edit');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master');sync.integrate(self.root,base,lref,rref,preferred='left')
        self.assertEqual(sync.list_conflicts(self.root)['items'],[])
        merged=next(e for e in library.snapshot(self.root)['events'] if e['id']=='e')
        self.assertEqual(merged['name'],'网站名称');self.assertEqual(merged['parameters'][0]['name'],'本地参数名称')
        website_data.export(self.root);self.assertEqual(website_data.validate(self.root),{'valid':True,'notes':0})

    def test_retired_group_survives_git_merge_and_offline_deployment_validation(self):
        import json_store
        import templates_store as library
        import website_data
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\nentities/\n*.bak\n*.tmp\n',encoding='utf-8')
        json_store.initialize(self.root)
        hero={'id':'hero:retired','name':'旧英雄','category':'heroes','effect':'旧技能'}
        json_store.write_file(self.root/'entities/heroes.json',[hero])
        group={'id':'g','name':'旧关联组','event_id':'hero_buy','scope':{'player_id':None,'lineup_note_id':None},
               'conditions':[{'id':'hero-condition','parameter_key':'hero','operator':'eq','value':{'id':hero['id'],'name':hero['name']}}],
               'utterances':[{'id':'u','text':'刷新'}],'related_entities':[{'id':hero['id'],'name':hero['name']}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':group}],actor='admin')
        json_store.write_file(self.root/'entities/heroes.json',[])
        warning=library.warnings(self.root)[0];library.confirm_warning(self.root,'g',warning['revision'])
        git(self.root,'add','.');git(self.root,'commit','-m','confirmed retired association');base=git(self.root,'rev-parse','HEAD')
        left={**group,'name':'网站修改名称'}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':left}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','website edit');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        right=deepcopy(group);right['utterances'][0]['text']='本地修改话术'
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'g','value':right}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','local edit');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        sync.integrate(self.root,base,lref,rref,preferred='left')
        self.assertEqual(sync.list_conflicts(self.root)['items'],[])
        merged=library.snapshot(self.root)['groups'][0]
        self.assertEqual(merged['name'],'网站修改名称');self.assertEqual(merged['utterances'][0]['text'],'本地修改话术')
        self.assertEqual(library.warnings(self.root),[])
        self.assertEqual(library._load(self.root)[1]['entity_archive']['g'][hero['id']]['name'],'旧英雄')
        website_data.export(self.root)
        self.assertEqual(website_data.validate(self.root),{'valid':True,'notes':0})
        # Metadata for g cannot authorize a new corrupted group referencing the retired ID.
        corrupt={**merged,'id':'new'}
        json_store.write_file(self.root/'templates/groups/new.json',corrupt)
        with self.assertRaisesRegex(ValueError,'未知实体'):website_data.validate(self.root)

    def test_restoring_event_rechecks_previously_valid_groups(self):
        import templates_store as library
        git(self.root,'init','-b','master');git(self.root,'config','user.name','Test');git(self.root,'config','user.email','test@example.invalid')
        (self.root/'.gitignore').write_text('raw/\n*.bak\n*.tmp\n',encoding='utf-8')
        event={'id':'e','name':'测试','parameters':[{'id':'px','key':'x','name':'值','type':'text'}]}
        group={'id':'z','name':'网站','event_id':'e','scope':{'player_id':None,'lineup_note_id':None},'conditions':[{'id':'c','parameter_key':'x','operator':'eq','value':'文字'}],'utterances':[{'id':'u','text':'网站'}]}
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':event}],actor='admin')
        git(self.root,'add','.');git(self.root,'commit','-m','base');base=git(self.root,'rev-parse','HEAD')
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'group','action':'put','id':'z','value':group}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','website text group');lref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','-b','incoming',base)
        event['parameters'][0]['type']='number'
        local=deepcopy(group);local['id']='a';local['conditions'][0]['value']=3
        library.apply(self.root,library.snapshot(self.root)['revision'],[{'kind':'event','action':'put','id':'e','value':event},{'kind':'group','action':'put','id':'a','value':local}],actor='admin')
        git(self.root,'add','templates');git(self.root,'commit','-m','local number group');rref=git(self.root,'rev-parse','HEAD')
        git(self.root,'checkout','master')
        sync.integrate(self.root,base,lref,rref,preferred='left')
        self.assertEqual([g['id'] for g in library.snapshot(self.root)['groups']],['z'])
        self.assertTrue(sync.is_blocked(self.root,'event','e'))
        self.assertTrue(sync.is_blocked(self.root,'group','a'))


if __name__ == '__main__':
    unittest.main()
