import json
from pathlib import Path
import tempfile
import unittest

import test_templates_http  # Initialize project imports.
import card_tags
from workspace import Conflict


class CardTagReviewTests(unittest.TestCase):
    def test_public_reviews_and_effective_tags_follow_site_to_new_release(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            old, new, state = base/'old', base/'new', base/'state'
            cards = {'a':dict(name='英雄',type='英雄',awakened=False,tags=['治疗'])}
            for root in (old, new):
                path = root/'src/condition/card-tags.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(cards),encoding='utf8')
            writer = dict(username='作者',role='annotator')
            admin = dict(username='审核人',role='admin')
            path = '/api/cards/a/tags'
            base_revision = card_tags.read(old,writer,path)['revision']
            proposal = card_tags.mutate(old,writer,path,{'tags':['治疗友军'],'revision':base_revision})
            card_tags.configure_public_database(old,state)
            card_tags.configure_public_database(new,state)
            self.assertEqual(card_tags.read(new,admin,path)['items'][0]['id'],proposal['id'])
            card_tags.mutate(new,admin,'/api/cards/tag-reviews/'+proposal['id']+'/approve',{})
            self.assertEqual(card_tags.effective_tags(old)['a']['tags'],['治疗友军'])
            self.assertEqual(card_tags.database(new),state/'card-tag-reviews.sqlite3')

    def test_review_is_per_form_and_stale_proposal_can_only_be_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'src/condition'
            folder.mkdir(parents=True)
            cards = {k: dict(name='英雄', type='英雄', awakened=k=='b', tags=['提供护盾']) for k in ('a','b')}
            (folder/'card-tags.json').write_text(json.dumps(cards), encoding='utf8')
            writer = dict(username='作者', role='annotator')
            admin = dict(username='审核人', role='admin')
            viewer = dict(username='读者', role='viewer')
            path = '/api/cards/b/tags'
            initial = card_tags.read(root, writer, path)
            change = dict(revision=initial['revision'], tags=['获得护盾受益'])
            with self.assertRaises(PermissionError):
                card_tags.mutate(root, viewer, path, change)
            first = card_tags.mutate(root, writer, path, change)
            second = card_tags.mutate(root, writer, path, {**change,'tags':[]})
            review = '/api/cards/tag-reviews/' + first['id'] + '/approve'
            with self.assertRaises(PermissionError):
                card_tags.mutate(root, writer, review, {})
            self.assertEqual(card_tags.effective_tags(root),cards)
            card_tags.mutate(root, admin, review,{})
            stale = '/api/cards/tag-reviews/' + second['id']
            with self.assertRaises(Conflict):
                card_tags.mutate(root, admin, stale+'/approve',{})
            card_tags.mutate(root, admin, stale+'/reject',{})
            self.assertEqual(card_tags.effective_tags(root)['b']['tags'],change['tags'])
            self.assertEqual(card_tags.effective_tags(root)['a'],cards['a'])
            items=card_tags.read(root,admin,path)['items']
            self.assertEqual([i['status'] for i in items],['rejected','approved'])
            self.assertEqual(items[1]['before_tags'],['提供护盾'])
            self.assertEqual(card_tags.read(root,viewer,path)['items'],[])

class CardTagHttpReviewTests(unittest.TestCase):
    call = test_templates_http.TemplateHttpTests.call
    user = test_templates_http.TemplateHttpTests.user
    setUp = test_templates_http.TemplateHttpTests.setUp

    def test_approval_refreshes_template_snapshot_and_published_catalog(self):
        base = '/os-tutorial/api/'
        card = base + 'cards/a/tags'
        folder = self.root / 'src/condition'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'card-tags.json').write_text(json.dumps({'a':dict(name='卡',type='效果牌',awakened=False,tags=['治疗'])}),encoding='utf8')
        self.user('alice')
        code,state,_ = self.call(card)
        self.assertEqual(code,200,state)
        code,item,_ = self.call(card,'POST',{'tags':['治疗队友'],'revision':state['revision']})
        self.assertEqual(code,200,item)
        review = base + 'cards/tag-reviews/' + item['id'] + '/approve'
        self.assertEqual(self.call(review,'POST',{})[0],403)
        self.assertEqual(self.call(base+'templates')[1]['condition_catalog']['card_tags']['a']['tags'],['治疗'])
        self.user('klywa')
        code,result,_ = self.call(review,'POST',{})
        self.assertEqual(code,200,result)
        for suffix in ('templates','templates/published'):
            code,result,_ = self.call(base+suffix)
            self.assertEqual(code,200,result)
            self.assertEqual(result['condition_catalog']['card_tags']['a']['tags'],['治疗队友'])
