"""Canonical official card graphs and bounded player-note reconciliation."""
from copy import deepcopy
import hashlib
import html
import json
import re
import json_document
import json_store


def clean(value):
    return html.unescape(re.sub('<[^>]+>', '', str(value or ''))).strip()


def merge_values(old, new):
    """Union relations/embedded cards by identity, never by serialized length."""
    if isinstance(old, dict) and isinstance(new, dict):
        result=deepcopy(old)
        for key,value in new.items():
            result[key]=merge_values(result[key],value) if key in result else deepcopy(value)
        return result
    if isinstance(old,list) and isinstance(new,list):
        result=deepcopy(old)
        for value in new:
            identity='id' if isinstance(value,dict) and 'id' in value else 'name' if isinstance(value,dict) and 'cards' in value and 'name' in value else None
            if identity:
                found=next((i for i,r in enumerate(result) if isinstance(r,dict) and r.get(identity)==value[identity]),None)
                if found is not None:result[found]=merge_values(result[found],value);continue
            if value not in result:result.append(deepcopy(value))
        return result
    return deepcopy(new if new not in (None,'') else old)


def card_graph(lord):
    cards={}; issues=[]; owners=[]
    def visit(value,ancestry=()):
        if not isinstance(value,dict) or 'id' not in value:return
        cid='card:'+str(value['id'])
        # Descendants are indexed separately; compact properties avoid exponential copies.
        own={k:deepcopy(v) for k,v in value.items() if k not in ('previewCards','sourceCards')}
        own['previewCardIDs']=list(dict.fromkeys([*own.get('previewCardIDs',[]),*[c['id'] for c in value.get('previewCards',[]) if 'id' in c]]))
        old=cards.get(cid)
        if old and clean(old.get('desc')) and clean(own.get('desc')) and clean(old['desc'])!=clean(own['desc']):
            issues.append({'kind':'same_id_conflict','id':cid,'values':[clean(old['desc']),clean(own['desc'])]})
        cards[cid]=merge_values(old or {},own)
        if cid in ancestry:return
        for child in value.get('previewCards',[]):visit(child,(*ancestry,cid))
        for parent in value.get('sourceCards',[]):
            visit(parent,(*ancestry,cid))
            pid='card:'+str(parent['id'])
            cards[pid]['previewCardIDs']=list(dict.fromkeys([*cards[pid].get('previewCardIDs',[]),value['id']]))
    # Source-only ancestor copies are visited first; direct lord cards are authoritative.
    for card in lord.get('relatedCards',[]):visit(card)
    for card in lord.get('lordCards',[]):visit(card)
    for group in lord.get('talent',[]):
        for card in group.get('cards',[]):visit(card);owners.append('card:'+str(card['id']))
    for cid,card in cards.items():
        for target in card.get('previewCardIDs',[]):
            if 'card:'+str(target) not in cards:issues.append({'kind':'missing_option','from':cid,'id':'card:'+str(target)})
    return cards,issues


def normalize_entities(data,url,at):
    import wxq
    buckets={c:{} for c in wxq.CATEGORIES}
    def add(card,owner=None):
        if not all(k in card for k in ('id','name','type')):return
        category={1:'heroes',9:'heroes',2:'effect-cards',5:'equipment',6:'talents',7:'player-skills'}.get(card['type'],'derivatives')
        hero=card.get('heroCard') or {}
        if hero.get('actorType') not in (None,1) or hero.get('isNotShowInAtlas'):category='derivatives'
        eid='card:'+str(card['id']);relations=[{'kind':'previews','id':'card:'+str(i)} for i in card.get('previewCardIDs',[])]
        if owner:relations.append({'kind':'owner','id':owner})
        record={'id':eid,'category':category,'name':card['name'],'aliases':[],'description':clean(card.get('desc')),
                'properties':deepcopy(card),'relations':relations,'sources':[url],'version':None,'status':'official','retrieved_at':at}
        buckets[category][eid]=merge_values(buckets[category].get(eid,{}),record)
    from official import walk_cards
    for key,value in data.items():
        if key=='lords':continue
        for card in walk_cards(value):add({k:deepcopy(v) for k,v in card.items() if k not in ('previewCards','sourceCards')})
    for lord in data.get('lords',[]):
        pid='player:'+str(lord.get('lordId',lord.get('id','')))
        graph,issues=card_graph(lord)
        props={k:deepcopy(v) for k,v in lord.items() if k not in ('talent','lordCards','relatedCards')}
        props.update(talent=[{**{k:deepcopy(v) for k,v in g.items() if k!='cards'},'cards':[graph['card:'+str(c['id'])] for c in g.get('cards',[])]} for g in lord.get('talent',[])],
                     official_cards=graph,official_issues=issues)
        buckets['players'][pid]={'id':pid,'name':lord.get('name') or lord.get('lordName') or '棋手-'+pid.split(':')[-1],
            'category':'players','aliases':[],'description':clean(lord.get('desc')),'properties':props,
            'relations':[{'kind':'skill','id':cid} for cid in graph],'sources':[url],'version':None,'status':'official','retrieved_at':at}
        for card in graph.values():add(card,pid)
    for cms in data.get('data',[]):
        if isinstance(cms,dict) and 'uid' in cms and 'title' in cms:
            pid='player:'+str(cms['uid']);row={'id':pid,'category':'players','name':cms['title'],'aliases':[],
                'description':'','properties':{'cms':cms},'relations':[],'sources':[url],'version':None,'status':'official','retrieved_at':at}
            buckets['players'][pid]=merge_values(buckets['players'].get(pid,{}),row)
    return buckets


def stable(pid,key):return 'official-'+hashlib.sha256((pid+'|'+key).encode()).hexdigest()[:20]


def profile_nodes(player):
    pid=player['id'];props=player['properties'];cards=props.get('official_cards')
    if cards is None:cards,_=card_graph(props)
    result=[];bindings={};seen=set();issues=list(props.get('official_issues',[]))
    def heading(key,title,level=3):
        nid=stable(pid,'heading:'+key);result.append({'id':nid,'type':'heading','level':level,'title':title,'separator':'\n\n'});bindings[nid]={'kind':'heading','key':key}
    def visit(cid,group=None,depth=0,expand=True):
        if cid not in cards:return
        if cid in seen:return
        seen.add(cid);card=cards[cid];value=clean(card.get('desc')) or '官网未提供效果说明。'
        details=[]
        if group and group.get('level'):
            details.append('官网等级标记：'+str(group['level'])+'级（字段含义待确认，不等同于必定获得）')
        if card.get('cardGetDesc'):details.append('获得方式：'+clean(card['cardGetDesc']).removeprefix('来源:').strip())
        if card.get('talentStageDesc'):details.append('出现阶段：'+clean(card['talentStageDesc']))
        targets=['card:'+str(i) for i in card.get('previewCardIDs',[])]
        if targets:details.append('后续选项：'+'、'.join(cards[t]['name'] if t in cards else t+'（官网资料缺失）' for t in targets))
        if details:value+='\n\n'+'；'.join(details)+'。'
        nid=stable(pid,cid);result.append({'id':nid,'type':'entry','key':card['name'],'show_key':True,'value':value,'separator':'\n\n'})
        bindings[nid]={'kind':'card','card_id':cid,'group':group.get('name') if group else '关联选项','parent_ids':[
            p for p,c in cards.items() if int(cid.split(':')[1]) in c.get('previewCardIDs',[])]}
        if expand:
            for target in targets:visit(target,depth=depth+1)
    for i,group in enumerate(props.get('talent',[])):
        heading('group:'+str(i),{'专属':'专属天赋','天赋':'专属天赋'}.get(group.get('name'),group.get('name') or '技能分组'))
        for card in group.get('cards',[]):visit('card:'+str(card['id']),group,expand=False)
    remaining=[cid for cid in cards if cid not in seen]
    if remaining:
        heading('related','关联选项')
        for cid in remaining:visit(cid)
    return result,bindings,{'player_id':pid,'card_ids':sorted(seen),'issues':issues}


def merge_profile(record,player,evidence,reconciliation=None):
    pid=player['id'];generated,bindings,report=profile_nodes(player)
    if not generated or not report['card_ids']:raise ValueError('官网缺少棋手技能分组：'+player['name'])
    if record is None:
        body=json_document.parse('# '+player['name']+'\n\n'+''.join('## '+s+'\n\n' for s in ['技能','前期思路','适用打法与选择','适用技巧','关联知识']))
        record={'body':body,'metadata':{'id':'official-player-'+pid.split(':')[-1],'type':'player','title':player['name'],
                   'player_id':pid,'path':'knowledge/players/'+player['name']+'.json','entities':[pid],'claim_annotations':[]}}
    before=record;result=json_store.editable_record(record);body=result['body'];meta=result['metadata']
    managed=meta.get('official_profile',{}).get('nodes',{});nodes=body['nodes']
    start=next((i for i,n in enumerate(nodes) if n['type']=='heading' and n.get('title')=='技能' and n['level']==2),None)
    if start is None:raise ValueError('棋手笔记缺少技能章节：'+meta['title'])
    end=start+1
    while end<len(nodes) and not(nodes[end]['type']=='heading' and nodes[end]['level']<=2):end+=1
    old_section=nodes[start+1:end];supplements=[];mapping={};reconciliation=reconciliation or {}
    if not managed:
        for old in old_section:
            if old['type']!='entry':continue
            rule=reconciliation.get(old['id'])
            if rule is None or (rule.get('sha256') and rule['sha256']!=json_store.digest(old)):
                supplements.append(old);continue
            if rule is not None and rule.get('usage'):
                supplements.append({**old,'value':rule['usage']});continue
            match=next((n for n in generated if n['type']=='entry' and n['key'] in old.get('key','') and n['id'] not in mapping),None)
            if match is None and rule is not None:
                match=next((n for n in generated if n['type']=='entry' and n['key'] in old['value'] and n['id'] not in mapping),None)
            if match is not None:mapping[match['id']]=old['id']
            elif rule is None:supplements.append(old)
    else:
        supplements=[n for n in old_section if n['id'] not in managed and n['id']!=stable(pid,'heading:usage')]
        for old_id,info in managed.items():
            if info.get('kind')=='card':mapping[stable(pid,info['card_id'])]=old_id
    if mapping:
        for n in generated:
            old_id=n['id'];n['id']=mapping.get(old_id,old_id)
            bindings[n['id']]=bindings.pop(old_id) if n['id']!=old_id else bindings[old_id]
    if supplements:
        generated.append({'id':stable(pid,'heading:usage'),'type':'heading','level':3,'title':'技能运用与补充','separator':'\n\n'})
        generated.extend(supplements)
    body['nodes']=[*nodes[:start+1],*generated,*nodes[end:]]
    old_map={n['id']:n for n in before['body']['nodes']};new_map={n['id']:n for n in body['nodes']}
    changed={nid for nid in old_map.keys()|new_map.keys() if old_map.get(nid)!=new_map.get(nid)}
    old_claims=meta.get('claim_annotations',[]);retired=[];active=[]
    for claim in old_claims:
        if claim['text_ref'] in bindings or claim['text_ref'] not in new_map:
            retired.append(claim)
        else:active.append(claim)
    # Stable generated claims are only rebuilt when the official node actually changes.
    for nid,binding in bindings.items():
        if binding.get('kind')!='card':continue
        old=next((c for c in old_claims if c['text_ref']==nid and c.get('origin')=='official'),None)
        ref=evidence.get(binding['card_id'])
        if old and nid not in changed:active.append(old)
        elif ref:active.append({'id':stable(pid,'claim:'+binding['card_id']),'text_ref':nid,'section':'技能','kind':'mechanic','origin':'official','evidence':[ref]})
    retired=[c for c in retired if not any(c==a for a in active)]
    meta['claim_annotations']=active
    for nid in bindings:
        if nid in changed and nid in meta.get('node_annotations',{}):
            meta['node_annotations'][nid]={'origin':'official','section':'技能'}
    meta['official_profile']={'player_id':pid,'nodes':bindings,'card_ids':report['card_ids']}
    if body==before['body'] and meta==before['metadata']:return before,report
    if body!=before['body']:
        from wxq import now
        meta.setdefault('history',[]).append({'at':now(),'origin':'official','previous':json_store.snapshot(before)})
        meta.setdefault('retired_claim_annotations',[]).extend({**c,'history_index':len(meta['history'])-1} for c in retired if c not in meta.get('retired_claim_annotations',[]))
    report.update(changed_nodes=sorted(changed),retained_supplements=len(supplements))
    json_store.check_record(result)
    return result,report
