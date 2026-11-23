"""Strict portable speech template schema. This module performs no I/O."""
from copy import deepcopy
import math
import re
import template_rules as rules

ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
KEY = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
CATEGORIES = {'players','heroes','equipment','talents','derivatives','effect-cards','player-skills'}
WORKFLOW_METADATA = {'review_status','last_modified_by','reviewed_by','reviewed_at','entity_snapshot'}
REVIEW_STATUSES = {'ai_generated','initial_reviewed','final_reviewed'}
GROUP_METADATA = {'version', 'mode', 'tags', 'batch', 'explanation', 'explanation_before',
                  'explanation_source', 'explanation_after'} | WORKFLOW_METADATA


def group_season(group):
    version=group.get('version') or 'S1'
    if not isinstance(version,str):raise ValueError('模板组版本无效')
    return version.upper()


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


def validate_event(event, entities, *, retired_suggestions=None):
    fields(event,{'id','name','category','parameters'},{'id','name','parameters'})
    identity(event['id']);text(event['name']);text(event.get('category','未分类'),'事件分类')
    if event['name'].endswith('（旧版）'):
        raise ValueError('该旧版事件已停用：'+event['name'])
    unique(event['parameters'],'参数');keys=set()
    for p in event['parameters']:
        fields(p,{'id','key','name','type','dsl_type','entity_categories','suggestions','min','max'},{'id','key','name','type'})
        if 'dsl_type' in p:rules.check_type(p['dsl_type'],rules.catalog())
        if not isinstance(p['key'],str) or not KEY.fullmatch(p['key']) or p['key'] in keys:raise ValueError('参数英文键无效或重复')
        if p['key'] in {'and','or','not','true','false','in','is','has'}:raise ValueError('条件关键词不能作为事件参数：'+p['key'])
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
    fields(group,{'id','name','ignored','event_id','scope','conditions','utterances','related_entities'} | GROUP_METADATA | rules.RULE_FIELDS,
           {'id','name','event_id','scope','conditions','utterances'})
    identity(group['id']);text(group['name'])
    if 'ignored' in group and type(group['ignored']) is not bool:
        raise ValueError('模板组忽略状态必须是布尔值')
    if 'explanation' in group:
        explanation = group['explanation']
        if not isinstance(explanation, str) or len(explanation) > 300:
            raise ValueError('模板组说明必须为不超过 300 个字符的文本')
    for key, label in (('version','版本'), ('mode','模式')):
        if key in group and (not isinstance(group[key], str) or len(group[key]) > 80 or group[key] != group[key].strip()):
            raise ValueError(label+'须为不超过 80 字的文本')
    for key, label in (('tags','标签'), ('batch','批次')):
        if key in group:
            values = group[key]
            if (not isinstance(values, list) or any(not isinstance(value, str) or not 0 < len(value) <= 40
                                                    or value != value.strip() for value in values)
                    or len(set(values)) != len(values)):
                raise ValueError(label+'须为互不重复的 1 至 40 字文本')
    if group.get('review_status') is not None and (not isinstance(group['review_status'],str) or group['review_status'] not in REVIEW_STATUSES):
        raise ValueError('模板组审核状态无效')
    if 'last_modified_by' in group:
        modifier=group['last_modified_by']
        fields(modifier,{'kind','username'},{'kind'})
        if modifier['kind'] not in ('ai','user'):raise ValueError('模板组最后修改人无效')
        if modifier['kind']=='user':text(modifier.get('username'),'最后修改人')
        elif 'username' in modifier:raise ValueError('AI 修改人不应包含账号')
    for key in ('reviewed_by','reviewed_at'):
        if key in group:text(group[key],'复核记录')
    if 'entity_snapshot' in group:
        snapshot=group['entity_snapshot']
        fields(snapshot,{'season','version','entities'},{'season','entities'})
        text(snapshot['season'],'官方资料赛季')
        if 'version' in snapshot:text(snapshot['version'],'官方资料版本')
        if (not isinstance(snapshot['entities'],dict) or any(not isinstance(row,dict) for row in snapshot['entities'].values())):
            raise ValueError('模板组官方描述快照无效')
    for key in ('explanation_before', 'explanation_source', 'explanation_after'):
        if key in group and (not isinstance(group[key], str) or len(group[key]) > 100000):
            raise ValueError('说明与依据分项格式无效或过长')
    event=events.get(group['event_id']) if isinstance(group['event_id'],str) else None
    if event is None:raise ValueError('话术组引用的事件不存在')
    rules.validate_rule(group,event)
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
    from src.python.condition import entity_utterance_references, literal_in_bindings, numeric_utterance_bindings, utterance_references
    references = {}
    for u in group['utterances']:
        fields(u,{'id','text','ignored','fixed'},{'id','text'});text(u['text'],'话术')
        references.update(dict.fromkeys(utterance_references(u['text'])))
        if 'ignored' in u and type(u['ignored']) is not bool:
            raise ValueError('话术忽略状态必须是布尔值')
        if 'fixed' in u and type(u['fixed']) is not bool:
            raise ValueError('话术固定状态必须是布尔值')
    if references.keys() - params.keys():
        catalog = rules.library_catalog([event])
        expression = group.get('expression', '')
        allowed = set(params) | entity_utterance_references(references,event['name'],catalog)
        if expression:
            allowed.update(literal_in_bindings(expression,event['name'],catalog))
            allowed.update(numeric_utterance_bindings(expression,event['name'],catalog))
        unknown = [path for path in references if path not in allowed]
        if unknown:
            raise ValueError('话术引用需要已声明参数、单实体路径、必选的 in 字面量条件或数值比较：'+'、'.join(unknown))
    refs=group.get('related_entities',[])
    if not isinstance(refs,list):raise ValueError('关联实体必须为列表')
    seen=set()
    for ref in refs:
        entity_ref(ref,entities)
        if ref['id'] in seen:raise ValueError('关联实体重复')
        seen.add(ref['id'])
    if 'expression' not in group and group['conditions']:
        rules.validate_rule(rules.editor_rule(group,event,entities),event)


def validate_library(document, entities=None, notes=None, *, retired_entities=None, retired_suggestions=None):
    """Validate canonical arrays, returning a detached normalized public document."""
    fields(document,{'kind','schema_version','events','groups'},{'schema_version','events','groups'})
    if document.get('kind','speech-template-library')!='speech-template-library' or type(document['schema_version']) is not int or document['schema_version']!=1:raise ValueError('模板库格式或版本无效')
    unique(document['events'],'事件');unique(document['groups'],'话术组')
    entities=entities or {};notes=notes or {}
    for event in document['events']:validate_event(event,entities,retired_suggestions=(retired_suggestions or {}).get(event['id']))
    if len({e['name'] for e in document['events']})!=len(document['events']):
        raise ValueError('事件名称重复，请为事件使用唯一名称')
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


# Legacy groups could reference a virtual built-in without an event file.
RETIRED_BUILTIN_IDS = {
    'battle_prepare','effect_buy','effect_select','equipment_equip','equipment_transfer',
    'hero_buy','hero_deploy','hero_merge','hero_sell_hand','player_level','shop_lock',
    'shop_refresh','skill_select','skill_use','talent_select','effect_use','equipment_merge',
}


def builtin_events():
    return rules.workbook_events() + [rules.explanation_event(event) for event in legacy_events()]


def legacy_events():
    definitions=[
        ('hero_sell_board','从场上出售英雄','英雄','hero','heroes'),
        ('hero_select','选择英雄牌','英雄','hero','heroes'),
        ('unit_move','移动单位','战场','unit','heroes'),
        ('lineup_ready','阵容成型','关键局势',None,None),('health_crisis','血量危机','关键局势',None,None),
        ('player_streak','玩家连胜','关键局势',None,None),('opponent_streak','对手连胜','关键局势',None,None),
        ('dangerous_opponent','高危对手','关键局势',None,None),('opponent_equipment','对手关键装备','关键局势','equipment','equipment'),
        ('key_card_acquired','获得关键卡牌','关键局势','card',None),('key_card_shop','商店刷出关键卡牌','关键局势','card',None),
        ('auction_start','拍卖开始','拍卖开始',None,None)]
    result=[]
    names={'hero':'英雄','effect':'效果牌','equipment':'装备','unit':'单位','card':'关键卡牌'}
    for eid,name,category,key,entity_category in definitions:
        params=[{'id':'p_situation','key':'situation','name':'场上情况','type':'text'},
                {'id':'p_stage','key':'stage','name':'对局阶段','type':'text','suggestions':['前期','中期','后期']}]
        if key:
            p={'id':'p_'+key,'key':key,'name':names[key],'type':'entity'}
            if entity_category:p['entity_categories']=[entity_category]
            params.append(p)
        if eid in ('health_crisis','dangerous_opponent'):
            params.append({'id':'p_health','key':'health','name':'血量','type':'number','min':0})
        if eid in ('player_streak','opponent_streak'):
            params.append({'id':'p_streak','key':'streak','name':'连胜数','type':'number','min':0})
        result.append({'id':eid,'name':name,'category':category,'parameters':params})
    return result


def order_events(events):
    ranks={event['id']:i for i,event in enumerate(builtin_events())}
    return sorted(events,key=lambda event:(ranks.get(event['id'],len(ranks)),event['id']))
