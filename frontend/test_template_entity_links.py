"""Derived references retain version history without manual associations."""
from copy import deepcopy
import unittest
import test_templates as fixtures

store=fixtures.store


class EntityLinkTests(unittest.TestCase):
    setUp=fixtures.TemplateTests.setUp
    write=fixtures.TemplateTests.write
    saved=fixtures.TemplateTests.saved

    def variants(self):
        self.catalog.append({'id':'card:3','name':'英雄甲','category':'heroes','awakened':True,'description':'觉醒技能'})
        self.write('entities/heroes.json',self.catalog)

    def test_all_versions_derive_but_manual_body_and_suggestions_do_not(self):
        self.variants()
        event=fixtures.event();event['parameters'][0]['suggestions']=[{'id':'card:2','name':'英雄乙'}]
        group=fixtures.group();group['related_entities']=[{'id':'card:2','name':'英雄乙'}]
        group['utterances'][0]['text']='英雄乙与{card}'
        store.apply(self.root,store.snapshot(self.root)['revision'],[fixtures.put('event',event),fixtures.put('group',group)])
        links=store.entity_links(self.root)['g1']
        self.assertEqual({row['id'] for row in links},{'card:1','card:3','player:1'})
        self.catalog[1]['description']='不应监控'
        self.write('entities/heroes.json',self.catalog)
        self.assertEqual(store.warnings(self.root),[])
        self.catalog[2]['description']='觉醒技能变化'
        self.write('entities/heroes.json',self.catalog)
        warning=store.warnings(self.root)[0]
        self.assertEqual([row['id'] for row in warning['entities']],['card:3'])

    def test_added_version_then_rename_and_removal_keep_stable_identity(self):
        self.saved()
        self.variants()
        warning=store.warnings(self.root)[0]
        self.assertEqual(warning['entities'][0]['id'],'card:3')
        self.assertIsNone(warning['entities'][0]['before'])
        store.confirm_warning(self.root,'g1',warning['revision'])
        self.catalog[2]['name']='英雄甲新名称'
        self.write('entities/heroes.json',self.catalog)
        warning=store.warnings(self.root)[0]
        self.assertEqual(warning['entities'][0]['id'],'card:3')
        store.confirm_warning(self.root,'g1',warning['revision'])
        self.write('entities/heroes.json',self.catalog[:2])
        warning=store.warnings(self.root)[0]
        self.assertIsNone(warning['entities'][0]['after'])
        self.assertIn('card:3',{row['id'] for row in store.entity_links(self.root)['g1']})
        store.confirm_warning(self.root,'g1',warning['revision'])
        self.assertEqual(store.warnings(self.root),[])

    def test_removing_condition_revokes_old_versions_and_keeps_legacy_archive(self):
        self.variants();self.saved()
        group=deepcopy(store.snapshot(self.root)['groups'][0]);group['conditions']=[]
        group['related_entities']=[{'id':'card:1','name':'英雄甲'}]
        store.apply(self.root,store.snapshot(self.root)['revision'],[fixtures.put('group',group)])
        self.catalog[0]['description']='已不关联'
        self.catalog[2]['description']='也不关联'
        self.write('entities/heroes.json',self.catalog)
        self.assertEqual(store.warnings(self.root),[])
        self.assertEqual([row['id'] for row in store.entity_links(self.root)['g1']],['player:1'])
        self.assertEqual(store.snapshot(self.root)['groups'][0]['related_entities'],group['related_entities'])

    def test_content_save_does_not_acknowledge_new_matching_version(self):
        self.saved();self.variants()
        before=store.warnings(self.root)[0]
        group=deepcopy(store.snapshot(self.root)['groups'][0]);group['utterances'][0]['text']='仅修改话术'
        store.apply(self.root,store.snapshot(self.root)['revision'],[fixtures.put('group',group)])
        after=store.warnings(self.root)[0]
        self.assertEqual(before['entities'],after['entities'])


if __name__=='__main__':unittest.main()
