import sys, tempfile, unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import official
import official_profiles as profiles
import json_document, json_store

def sample():
    child={'id':12,'name':'选项乙','type':7,'desc':'第8回合获得奖励。','previewCardIDs':[10],'previewCards':[],'sourceCards':[]}
    main={'id':10,'name':'基础技能','type':7,'desc':'第5/8回合选择。','previewCardIDs':[11,12],
          'previewCards':[{'id':11,'name':'选项甲','type':7,'desc':'甲效果','previewCardIDs':[],'previewCards':[]}], 'sourceCards':[]}
    talent={'id':20,'name':'专属天赋','type':6,'desc':'专属效果','previewCardIDs':[],'previewCards':[]}
    return {'lords':[{'lordId':1,'name':'棋手甲','talent':[{'name':'技能','level':1,'cards':[main]},
           {'name':'专属','level':6,'cards':[talent]}],'lordCards':[child,talent]}]}

class OfficialProfileTests(unittest.TestCase):
    def test_unbound_manual_content_and_changed_reconciliation_are_preserved(self):
        p=official.normalize(sample(),'https://official.test/data','today')['players']['player:1']
        record={'body':json_document.parse('# 棋手甲\n\n## 技能\n\n**基础技能：** 人工独有条件\n\n## 前期思路\n'),
                'metadata':{'id':'p1','type':'player','player_id':'player:1','title':'棋手甲','path':'knowledge/players/棋手甲.json'}}
        nid=record['body']['nodes'][2]['id']
        record['metadata']['node_annotations']={nid:{'origin':'manual'}}
        for rules in ({},{nid:{'usage':'','sha256':'stale'}}):
            updated,_=profiles.merge_profile(record,p,{},rules)
            self.assertIn('人工独有条件',json_document.markdown(updated['body']))
        updated,_=profiles.merge_profile(record,p,{})
        managed=next(n for n in updated['body']['nodes'] if n.get('key')=='基础技能' and n['id']!=nid)
        managed['value']='人为改过的官方段落'
        again,_=profiles.merge_profile(updated,p,{})
        text=json_document.markdown(again['body'])
        self.assertNotIn('人为改过的官方段落',text)
        self.assertIn('人工独有条件',text)
    def test_all_relations_and_exclusive_owner_survive_normalization(self):
        buckets=official.normalize(sample(),'https://official.test/data', '2026-10-25')
        self.assertIn('card:20',buckets['talents'])
        self.assertIn({'kind':'owner','id':'player:1'},buckets['talents']['card:20']['relations'])
        self.assertIn({'kind':'previews','id':'card:11'},buckets['player-skills']['card:10']['relations'])

    def test_profile_covers_nested_options_and_preserves_strategy(self):
        p=official.normalize(sample(),'https://official.test/data','2026-10-25')['players']['player:1']
        record={'body':json_document.parse('# 棋手甲\n\n## 技能\n\n**基础技能：** 旧机制\n\n建议观察来牌再使用。\n\n## 前期思路\n\n保留策略\n'),
                'metadata':{'id':'p1','type':'player','player_id':'player:1','title':'棋手甲','path':'knowledge/players/棋手甲.json'}}
        old_id=record['body']['nodes'][2]['id']
        updated,report=profiles.merge_profile(record,p,{'card:10':{'type':'document','source':'doc-test','paragraph_start':1,'paragraph_end':1}}, {old_id:{'usage':''}})
        text=json_document.markdown(updated['body'])
        for term in ['选项甲','选项乙','专属天赋','第5/8回合','建议观察来牌再使用','保留策略']:self.assertIn(term,text)
        self.assertEqual(report['card_ids'],['card:10','card:11','card:12','card:20'])
        self.assertIn(old_id,[n['id'] for n in updated['body']['nodes']])
        again,_=profiles.merge_profile(updated,p,{})
        self.assertEqual(again,updated)

if __name__=='__main__':unittest.main()
