"""Disposable template library acceptance server; never touches the real library."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store
import server
import templates_store
import website_data


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='template-browser-',dir=ROOT/'temp') as folder:
        root=Path(folder);json_store.initialize(root)
        website_data.export(root)
        cards=json_store.read(ROOT/'website-data/cards.json',[])
        hero=next(c for c in cards if c['category']=='heroes')
        equipment=next(c for c in cards if c['category']=='equipment')
        json_store.write_file(root/'website-data/cards.json',cards)
        shutil.copytree(ROOT/'website-data/entities',root/'website-data/entities',dirs_exist_ok=True)
        images=json_store.read(ROOT/'website-data/images.json',{})
        json_store.write_file(root/'website-data/images.json',images)
        for eid in (hero['id'],equipment['id']):
            for key in images.get('entities',{}).get(eid,{}).values():
                relative=images['assets'][key]['path'];target=root/'website-data'/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/'website-data'/relative,target)
        groups=[{'id':'hero_example','name':'关键英雄购买提醒','event_id':'hero_buy',
            'scope':{'player_id':None,'lineup_note_id':None},
            'conditions':[{'id':'hero_condition','parameter_key':'hero','operator':'eq','value':{'id':hero['id'],'name':hero['name']}},
                          {'id':'stage_condition','parameter_key':'stage','operator':'eq','value':'前期'}],
            'utterances':[{'id':'line_one','text':'{hero}已经到手，先确认这一回合的安排。'},
                          {'id':'line_two','text':'留意{hero}，再决定下一步。'}],
            'related_entities':[{'id':equipment['id'],'name':equipment['name']}]},
            {'id':'prepare_example','name':'战前检查提醒','event_id':'battle_prepare',
             'scope':{'player_id':None,'lineup_note_id':None},'conditions':[],
             'utterances':[{'id':'prepare_line','text':'战斗即将开始，检查站位与装备。'}],'related_entities':[]}]
        templates_store.apply(root,templates_store.snapshot(root)['revision'],[
            {'kind':'group','action':'put','id':g['id'],'value':g} for g in groups],entities=cards)
        # Simulate a new effective official version after template creation.
        updated=deepcopy(cards)
        next(c for c in updated if c['id']==hero['id'])['effect']=hero.get('effect','')+' 测试资料更新。'
        json_store.write_file(root/'website-data/cards.json',updated)
        config=root/'accounts.json'
        config.write_text(json.dumps({'schema_version':2,'sessionSecret':'fixture-secret-'*5,'accounts':[
            {'username':'reviewer','password':'fixture','role':'admin'},
            {'username':'alice','password':'fixture','role':'annotator'},
            {'username':'reader','password':'fixture','role':'viewer'}]}),encoding='utf-8')
        http=server.create_server(root,0,public=True,base_path='',auth_config=config,state_dir=root/'state')
        http.public_origin=f'http://127.0.0.1:{http.server_port}'
        http.auth.secure=False
        http.sync=SimpleNamespace(status=lambda **kw:{'state':'synced'},enqueue=lambda **kw:{'state':'synced'})
        print(json.dumps({'port':http.server_port,'root':str(root),'hero':hero['name']}),flush=True)
        try:http.serve_forever()
        finally:http.server_close()
