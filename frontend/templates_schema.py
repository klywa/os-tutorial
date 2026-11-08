"""Strict portable speech template schema. This module performs no I/O."""
from copy import deepcopy
import math
import re

ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
KEY = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
CATEGORIES = {'players','heroes','equipment','talents','derivatives','effect-cards','player-skills'}


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value)-set(allowed) or set(required)-set(value):
        raise ValueError('模板字段无效或包含不允许的隐藏字段')


def identity(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('模板身份必须为 1–128 位英文字母、数字、下划线或连字符')
    return value


def text(value, label='名称'):
    if not isinstance(value, str) or not value.strip() or len(value)>100000:
        raise ValueError(label+'不能为空或过长')
    return value


def number(value):
    return type(value) is int or isinstance(value,float) and math.isfinite(value)


def unique(items, label):
    if not isinstance(items,list):raise ValueError(label+'必须为列表')
    seen=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError(label+'格式无效')
        uid=identity(item.get('id'))
        if uid in seen:raise ValueError(label+'身份重复：'+uid)
        seen.add(uid)


def entity_ref(value, entities, categories=None):
    fields(value,{'id','name'},{'id','name'})
    text(value.get('id'),'实体身份');text(value.get('name'),'实体名称')
    entity=entities.get(value['id'])
    if entity is None:raise ValueError('未知实体：'+value['id'])
    if categories and entity.get('category') not in categories:raise ValueError('实体类别不匹配：'+value['id'])


def typed(value, parameter, entities):
    kind=parameter['type']
    valid=(kind=='text' and isinstance(value,str) or kind=='number' and number(value)
           or kind=='boolean' and isinstance(value,bool) or kind=='entity' and isinstance(value,dict))
    if not valid:raise ValueError('参数值类型不匹配：'+parameter['key'])
    if kind=='entity':entity_ref(value,entities,parameter.get('entity_categories'))


def placeholders(value, keys):
    """Accept {key}, {{ and }} while rejecting every unmatched literal brace."""
    i=0
    while i<len(value):
        if value.startswith('{{',i) or value.startswith('}}',i):i+=2;continue
        if value[i]=='{':
            end=value.find('}',i+1)
            if end<0 or value[i+1:end] not in keys:raise ValueError('话术引用了未知参数或花括号未闭合')
            i=end+1;continue
        if value[i]=='}':raise ValueError('话术包含未配对的花括号')
        i+=1


def validate_event(event, entities, *, retired_suggestions=None):
    fields(event,{'id','name','category','parameters'},{'id','name','parameters'})
    identity(event['id']);text(event['name']);text(event.get('category','未分类'),'事件分类')
    unique(event['parameters'],'参数');keys=set()
    for p in event['parameters']:
        fields(p,{'id','key','name','type','entity_categories','suggestions','min','max'},{'id','key','name','type'})
        if not isinstance(p['key'],str) or not KEY.fullmatch(p['key']) or p['key'] in keys:raise ValueError('参数英文键无效或重复')
        keys.add(p['key']);text(p['name'],'参数名称')
        if p['type'] not in ('text','number','boolean','entity'):raise ValueError('未知参数类型')
        if 'entity_categories' in p:
            cats=p['entity_categories']
            if p['type']!='entity' or not isinstance(cats,list) or not cats or any(not isinstance(c,str) or c not in CATEGORIES for c in cats) or len(set(cats))!=len(cats):raise ValueError('实体参数类别无效')
        if any(k in p for k in ('min','max')):
            if p['type']!='number' or any(not number(p[k]) for k in ('min','max') if k in p):raise ValueError('数字范围建议无效')
            if 'min' in p and 'max' in p and p['min']>p['max']:raise ValueError('数字范围建议顺序无效')
        if 'suggestions' in p:
            if not isinstance(p['suggestions'],list):raise ValueError('参数建议必须为列表')
            scoped={**(retired_suggestions or {}).get(p['id'],{}),**entities}
            for v in p['suggestions']:typed(v,p,scoped)


def validate_group(group, events, entities, notes):
    fields(group,{'id','name','event_id','scope','conditions','utterances','related_entities'},
           {'id','name','event_id','scope','conditions','utterances'})
    identity(group['id']);text(group['name'])
    event=events.get(group['event_id']) if isinstance(group['event_id'],str) else None
    if event is None:raise ValueError('话术组引用的事件不存在')
    scope=group['scope'];fields(scope,{'player_id','lineup_note_id'},{'player_id','lineup_note_id'})
    player,lineup=scope['player_id'],scope['lineup_note_id']
    if player is not None:
        if not isinstance(player,str) or player not in entities or entities[player].get('category')!='players':raise ValueError('适用棋手不存在')
    if lineup is not None:
        note=notes.get(lineup) if isinstance(lineup,str) else None
        if note is None or note.get('type')!='lineup':raise ValueError('适用阵容笔记不存在')
        if player is None or note.get('player_id')!=player:raise ValueError('阵容笔记与适用棋手不一致')
    params={p['key']:p for p in event['parameters']}
    unique(group['conditions'],'条件')
    for c in group['conditions']:
        fields(c,{'id','parameter_key','operator','value'},{'id','parameter_key','operator','value'})
        p=params.get(c['parameter_key']) if isinstance(c['parameter_key'],str) else None
        if p is None:raise ValueError('条件引用了未知参数')
        op=c['operator']
        if op in ('eq','ne'):typed(c['value'],p,entities)
        elif p['type']=='number' and op in ('gt','gte','lt','lte','between'):
            value=c['value']
            if op=='between':
                if not isinstance(value,list) or len(value)!=2 or not all(number(v) for v in value) or value[0]>value[1]:raise ValueError('数字区间必须为有序的两个数字')
            elif not number(value):raise ValueError('数字比较需要数字值')
        else:raise ValueError('参数不支持该比较方式')
    unique(group['utterances'],'话术')
    if not group['utterances']:raise ValueError('每组至少需要一条话术')
    for u in group['utterances']:
        fields(u,{'id','text'},{'id','text'});text(u['text'],'话术');placeholders(u['text'],params)
    refs=group.get('related_entities',[])
    if not isinstance(refs,list):raise ValueError('关联实体必须为列表')
    seen=set()
    for ref in refs:
        entity_ref(ref,entities)
        if ref['id'] in seen:raise ValueError('关联实体重复')
        seen.add(ref['id'])


def validate_library(document, entities=None, notes=None, *, retired_entities=None, retired_suggestions=None):
    """Validate canonical arrays, returning a detached normalized public document."""
    fields(document,{'kind','schema_version','events','groups'},{'schema_version','events','groups'})
    if document.get('kind','speech-template-library')!='speech-template-library' or type(document['schema_version']) is not int or document['schema_version']!=1:raise ValueError('模板库格式或版本无效')
    unique(document['events'],'事件');unique(document['groups'],'话术组')
    entities=entities or {};notes=notes or {}
    for event in document['events']:validate_event(event,entities,retired_suggestions=(retired_suggestions or {}).get(event['id']))
    events={e['id']:e for e in document['events']}
    for group in document['groups']:
        # Retired references are scoped to an existing canonical record. Never
        # insert these into the global catalog used by new groups or imports.
        scoped={**(retired_entities or {}).get(group['id'],{}),**entities}
        validate_group(group,events,scoped,notes)
    result=deepcopy(document)
    for e in result['events']:e.setdefault('category','未分类')
    result['events']=order_events(result['events'])
    for g in result['groups']:g.setdefault('related_entities',[])
    return result


def builtin_events():
    definitions=[
        ('hero_buy','购买英雄','英雄','hero','heroes'),('hero_deploy','上阵英雄','英雄','hero','heroes'),
        ('hero_merge','合成英雄','英雄','hero','heroes'),('hero_sell_hand','从手牌出售英雄','英雄','hero','heroes'),
        ('hero_sell_board','从场上出售英雄','英雄','hero','heroes'),('hero_select','选择英雄牌','英雄','hero','heroes'),
        ('effect_use','使用效果牌','效果牌','effect','effect-cards'),('effect_buy','购买效果牌','效果牌','effect','effect-cards'),
        ('effect_select','选择效果牌','效果牌','effect','effect-cards'),
        ('equipment_equip','穿戴装备','装备','equipment','equipment'),('equipment_merge','合成装备','装备','equipment','equipment'),
        ('equipment_transfer','转移装备','装备','equipment','equipment'),
        ('skill_use','使用棋手技能','技能牌','skill','player-skills'),('skill_select','选择棋手技能','技能牌','skill','player-skills'),
        ('shop_refresh','刷新商店','商店',None,None),('shop_lock','锁定商店','商店',None,None),
        ('player_level','棋手升级','升级',None,None),('talent_select','选择天赋','升级','talent','talents'),
        ('unit_move','移动单位','战场','unit','heroes'),('battle_prepare','准备战斗','准备战斗',None,None),
        ('lineup_ready','阵容成型','关键局势',None,None),('health_crisis','血量危机','关键局势',None,None),
        ('player_streak','玩家连胜','关键局势',None,None),('opponent_streak','对手连胜','关键局势',None,None),
        ('dangerous_opponent','高危对手','关键局势',None,None),('opponent_equipment','对手关键装备','关键局势','equipment','equipment'),
        ('key_card_acquired','获得关键卡牌','关键局势','card',None),('key_card_shop','商店刷出关键卡牌','关键局势','card',None),
        ('auction_start','拍卖开始','拍卖开始',None,None)]
    result=[]
    names={'hero':'英雄','effect':'效果牌','equipment':'装备','skill':'棋手技能','talent':'天赋','unit':'单位','card':'关键卡牌'}
    for eid,name,category,key,entity_category in definitions:
        params=[{'id':'p_situation','key':'situation','name':'场上情况','type':'text'},
                {'id':'p_stage','key':'stage','name':'对局阶段','type':'text','suggestions':['前期','中期','后期']}]
        if key:
            p={'id':'p_'+key,'key':key,'name':names[key],'type':'entity'}
            if entity_category:p['entity_categories']=[entity_category]
            params.append(p)
        if eid in ('hero_merge','player_level'):
            params.append({'id':'p_level','key':'level','name':'等级','type':'number','min':1})
        if eid in ('health_crisis','battle_prepare','dangerous_opponent'):
            params.append({'id':'p_health','key':'health','name':'血量','type':'number','min':0})
        if eid in ('player_streak','opponent_streak'):
            params.append({'id':'p_streak','key':'streak','name':'连胜数','type':'number','min':0})
        result.append({'id':eid,'name':name,'category':category,'parameters':params})
    return result


def order_events(events):
    ranks={event['id']:i for i,event in enumerate(builtin_events())}
    return sorted(events,key=lambda event:(ranks.get(event['id'],len(ranks)),event['id']))
