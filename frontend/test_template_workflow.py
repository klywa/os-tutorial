from copy import deepcopy
import unittest

import test_templates as fixtures
import template_workflow as workflow
from test_templates import group, put, store
from templates_proposals import TemplateProposals


class WorkflowTests(unittest.TestCase):
    def test_edit_preserves_legacy_history_and_publishes_changed_tags(self):
        from json_store import read, write_file
        path=self.root/store.META
        legacy=read(path)
        legacy['audit']=[{'id':'legacy','actor':'old','changes':[],'at':'2020-01-01'}]
        write_file(path,legacy)
        original=path.read_bytes()
        current=store.snapshot(self.root)
        g={**current['groups'][0],'tags':['复盘']}
        updated=store.apply(self.root,current['revision'],[put('group',g)])
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(store.snapshot(self.root),updated)
        self.assertEqual(read(self.root/store.PUBLISHED)['groups'][0]['tags'],['复盘'])
        self.assertEqual(workflow.revisions(self.root,'g1')[0]['value']['tags'],['复盘'])
        inserted={**g,'id':'new-group','name':'第二组'}
        state=store.apply(self.root,updated['revision'],[put('group',inserted)])
        self.assertTrue((self.root/store.STATE).is_file())
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(store.snapshot(self.root),state)

    def test_status_save_leaves_published_library_and_records_audit(self):
        actor={'role':'admin','username':'reviewer'}
        path=self.root/store.PUBLISHED
        published=path.read_bytes()
        original_metadata=(self.root/store.META).read_bytes()
        updated=store.set_review_status(self.root,self.saved['revision'],'g1',actor,{'status':'initial_reviewed'})
        self.assertEqual(path.read_bytes(),published)
        self.assertEqual((self.root/store.META).read_bytes(),original_metadata)
        self.assertEqual(len([row for row in store.review_history(self.root)
                              if row.get('manual')=={'source':'review-status'}]),1)
        self.assertEqual(store.snapshot(self.root)['revision'],updated['revision'])
        self.assertEqual(updated['groups'][0],{**self.saved['groups'][0],'review_status':'initial_reviewed'})
        self.assertEqual(workflow.revisions(self.root,'g1')[0]['by'],'reviewer')
        with self.assertRaises(store.Conflict):
            store.set_review_status(self.root,self.saved['revision'],'g1',actor,{'status':None})

    def test_status_only_can_downgrade_and_preserves_authorship(self):
        actor={'role':'admin','username':'reviewer'}
        author={'kind':'user','username':'writer'}
        record={**group(),'review_status':'final_reviewed','last_modified_by':author,
                'reviewed_by':'qa','reviewed_at':'yesterday','entity_snapshot':{'season':'S1','entities':{}}}
        current={**self.saved,'groups':[record]}
        changed=workflow.review_status_change(current,'g1',actor,None)['value']
        self.assertIsNone(changed['review_status'])
        cleared={**current,'groups':[changed]}
        self.assertIsNone(workflow.review_status_change(cleared,'g1',actor,None))
        self.assertEqual(workflow.review_status_change(cleared,'g1',actor,'ai_generated')['value']['review_status'],'ai_generated')
        self.assertEqual(changed['last_modified_by'],author)
        self.assertEqual(changed['entity_snapshot'],record['entity_snapshot'])
        self.assertNotIn('reviewed_by',changed)
        writer={'role':'annotator','username':'writer'}
        with self.assertRaises(PermissionError):
            workflow.review_status_change(current,'g1',writer,'final_reviewed')
        self.assertIsNone(workflow.review_status_change(current,'g1',actor,'final_reviewed'))

    def test_status_proposal_keeps_content_and_cannot_be_elevated_at_approval(self):
        service=TemplateProposals(self.root,self.root/'raw'/'template-proposals.sqlite3',workflow_enabled=True)
        writer={'role':'annotator','username':'writer'}
        admin={'role':'admin','username':'admin'}
        change=workflow.review_status_change(self.saved,'g1',writer,'initial_reviewed')
        pending=service.submit(writer,{'revision':self.saved['revision'],'changes':[change],'source':'review-status'},
                               workflow_source='review-status')
        data={'proposal_revision':pending['proposal_revision']}
        with self.assertRaises(ValueError):
            service.action(admin,pending['id'],'approve',{**data,'changes':[{**change,'value':{**change['value'],'review_status':'final_reviewed'}}]})
        service.action(admin,pending['id'],'approve',data)
        self.assertEqual(store.snapshot(self.root)['groups'][0],{**self.saved['groups'][0],'review_status':'initial_reviewed'})

    def setUp(self):
        fixture = fixtures.TemplateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.saved = fixture.saved()
        self.catalog = {'items': fixture.catalog, 'complete_categories': ['heroes']}

    def apply(self, value, actor, source='editor'):
        changes = workflow.prepare(self.root, self.saved, [put('group', value)], actor,
                                   source=source, entities=self.catalog)
        self.saved = store.apply(self.root, self.saved['revision'], changes, actor=actor['username'])
        return self.saved['groups'][0]

    def test_noop_human_edit_and_reviewer_restriction(self):
        actor = {'username': 'writer', 'role': 'annotator'}
        self.assertEqual(self.apply(group(), actor), group())
        edited = self.apply({**group(), 'batch': ['b1', 'b2']}, actor)
        self.assertIsNone(edited['review_status'])
        self.assertEqual(edited['last_modified_by'], {'kind': 'user', 'username': 'writer'})
        self.assertEqual(edited['entity_snapshot']['entities']['card:1']['description'], '旧技能')
        with self.assertRaises(PermissionError):
            workflow.review_change(self.saved, 'g1', actor)
        self.saved=store.set_review_status(self.root,self.saved['revision'],'g1',actor,{'status':'initial_reviewed'})
        change = workflow.review_change(self.saved, 'g1', {'username': 'qa', 'role': 'quality'})
        reviewed = change['value']
        self.assertEqual(reviewed['review_status'], 'final_reviewed')
        self.assertEqual(reviewed['last_modified_by'], edited['last_modified_by'])

    def test_import_is_capped_by_uploader_role(self):
        imported = {**group(), 'name': '导入改稿', 'review_status': 'final_reviewed',
                    'last_modified_by': {'kind': 'user', 'username': 'original'}}
        saved = self.apply(imported, {'username': 'uploader', 'role': 'annotator'}, 'file-import')
        self.assertIsNone(saved['review_status'])
        self.assertEqual(saved['last_modified_by'], imported['last_modified_by'])

    def test_ai_edit_snapshots_text_references_and_noop_keeps_existing_provenance(self):
        actor = {'username':'uploader','role':'admin'}
        edited = {**group(), 'expression':'card.名称 is "英雄乙"', 'editor_mode':'text',
                  'priority':0, 'conditions':[], 'last_modified_by':{'kind':'ai'}}
        saved = self.apply(edited, actor, 'file-import')
        self.assertEqual(saved['review_status'], 'ai_generated')
        self.assertEqual(saved['entity_snapshot']['entities']['card:2']['description'], '乙技能')
        revision=self.saved['revision']
        same = self.apply({**saved,'review_status':'final_reviewed','version':'s1'}, actor, 'file-import')
        self.assertEqual(self.saved['revision'],revision)
        self.assertEqual(same,saved)

    def test_published_runtime_isolated_by_group_season(self):
        actor={'username':'author','role':'admin'}
        saved=self.apply({**group(),'version':'S2'},actor)
        self.assertEqual(saved['entity_snapshot']['season'],'S2')
        self.assertTrue(saved['entity_snapshot']['entities']['card:1']['missing'])
        self.assertEqual(store.refresh_published(self.root)['groups'],[])
        self.assertEqual(store.refresh_published(self.root,season='S2')['groups'][0]['version'],'S2')

    def test_legacy_pending_proposal_is_attributed_to_author_on_approval(self):
        proposals=TemplateProposals(self.root,self.root/'raw'/'template-proposals.sqlite3',workflow_enabled=True)
        researcher={'username':'researcher','role':'annotator'}
        legacy={**group(),'name':'旧提案的新名称','review_status':'final_reviewed'}
        pending=proposals.submit(researcher,{'revision':self.saved['revision'],'changes':[put('group',legacy)]})
        self.assertNotIn('workflow_source',pending)
        proposals.action({'username':'admin','role':'admin'},pending['id'],'approve',
                         {'proposal_revision':pending['proposal_revision']})
        actual=store.snapshot(self.root)['groups'][0]
        self.assertIsNone(actual['review_status'])
        self.assertEqual(actual['last_modified_by'],{'kind':'user','username':'researcher'})

    def test_restore_appends_revision_and_preserves_history(self):
        actor = {'username': 'reviewer', 'role': 'quality'}
        edited = self.apply({**group(), 'name': '新名字'}, actor)
        history = workflow.revisions(self.root, 'g1')
        self.assertEqual([entry['value']['name'] for entry in history], [edited['name'], group()['name']])
        prior = workflow.restore_change(self.root, self.saved, 'g1', history[-1]['id'])
        restored = self.apply(deepcopy(prior['value']), actor)
        self.assertEqual(restored['name'], group()['name'])
        self.assertEqual(restored['last_modified_by']['username'], actor['username'])
        self.assertEqual(len(workflow.revisions(self.root, 'g1')), 3)
