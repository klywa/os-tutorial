"""Optional presentation metadata. Members remain owned by compositions/variants."""
from copy import deepcopy
import re

STAGES = ('early','middle','late')


def default_overview(meta):
    variants = meta.get('late_variants', []) or [{'id':'','name':'默认阵容'}]
    return {'version':1, 'presets':[{'id':v['id'] or 'default','name':v['name'], 'variant_id':v['id'],
        'description':'','placements':[],'reserves':[], 'talents':[], 'effect_cards':[],
        'talent_note':'','effect_note':'',
        'stages':{s:{'rounds':'','description':'','claim_refs':[],'reserves':[]} for s in STAGES},
        'players':[{'player':p,'skills':[],'secret':[],'exclusive':[],'description':''} for p in meta.get('players',[])]}
        for v in variants]}


def entity_refs(data):
    result = []
    for p in data.get('presets', []):
        for field in ('reserves','talents','effect_cards'): result += p.get(field, [])
        for place in p.get('placements', []): result += [place.get('hero')] + place.get('equipment', [])
        for stage in p.get('stages', {}).values(): result += stage.get('reserves', [])
        for player in p.get('players', []):
            result += [player.get('player')]
            for field in ('skills','secret','exclusive'): result += player.get(field, [])
    return [r for r in result if r]


def remap(data, old_ids, new_id):
    for p in data.get('presets', []):
        for stage in p.get('stages', {}).values():
            stage['claim_refs'] = list(dict.fromkeys(new_id if r in old_ids else r for r in stage.get('claim_refs', []) if r not in old_ids or new_id))


def validate(meta, rows, claims=None):
    if 'overview' not in meta: return
    data = meta['overview']
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('presets'), list) or not data['presets']:
        raise ValueError('阵容概览须为版本1且至少有一套方案')
    entities = {r['id']:r for r in rows}
    variants = {v['id']:v for v in meta.get('late_variants', [])}
    ids = set()
    def refs(values, category):
        if not isinstance(values, list) or any(not isinstance(v,str) for v in values) or len(values) != len(set(values)):
            raise ValueError('概览实体引用须为不重复的ID列表')
        for value in values:
            if entities.get(value, {}).get('category') != category: raise ValueError('概览实体类别无效：'+value)
    def text(row, keys):
        for k in keys:
            if not isinstance(row.get(k,''),str): raise ValueError('概览说明须为文字')
    for p in data['presets']:
        if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',p['id']) or p['id'] in ids:
            raise ValueError('概览方案ID无效或重复')
        ids.add(p['id'])
        text(p, ['name','description','talent_note','effect_note'])
        if not p.get('name','').strip(): raise ValueError('请填写概览方案名称')
        variant_id = p.get('variant_id','')
        if variant_id and variant_id not in variants: raise ValueError('请先解除已删除组合的概览绑定')
        members = variants[variant_id]['members'] if variant_id else meta.get('compositions', {}).get('late', [])
        heroes = {m['hero'] for m in members}
        refs(p.get('reserves', []),'heroes'); refs(p.get('talents', []),'talents'); refs(p.get('effect_cards', []),'effect-cards')
        if not isinstance(p.get('placements', []),list): raise ValueError('站位须为列表')
        occupied, placed = set(), set()
        for cell in p.get('placements', []):
            if not isinstance(cell,dict): raise ValueError('站位格式无效')
            row,col = cell.get('row'),cell.get('col')
            if type(row) is not int or type(col) is not int or not 0<=row<4 or not 0<=col<7: raise ValueError('站位超出四行七列棋盘')
            if (row,col) in occupied or cell.get('hero') in placed: raise ValueError('站位格或英雄重复')
            occupied.add((row,col)); placed.add(cell.get('hero'))
            if cell.get('hero') not in heroes: raise ValueError('站位英雄必须属于当前后期组合')
            refs([cell['hero']],'heroes'); refs(cell.get('equipment', []),'equipment')
        if not isinstance(p.get('stages'),dict) or set(p['stages']) != set(STAGES): raise ValueError('概览须包含前中后期')
        for stage in p['stages'].values():
            if not isinstance(stage,dict): raise ValueError('阶段格式无效')
            text(stage,['rounds','description']); refs(stage.get('reserves', []),'heroes')
            values = stage.get('claim_refs', [])
            if not isinstance(values,list) or any(not isinstance(v,str) for v in values): raise ValueError('结论引用须为ID列表')
            if claims is not None and set(values)-{c['id'] for c in claims}: raise ValueError('概览引用了不存在的结论')
        if not isinstance(p.get('players',[]),list): raise ValueError('棋手能力须为列表')
        for player in p.get('players', []):
            if not isinstance(player,dict): raise ValueError('棋手能力格式无效')
            refs([player.get('player')],'players'); text(player,['description'])
            for field in ('skills','secret','exclusive'): refs(player.get(field, []),'player-skills')
