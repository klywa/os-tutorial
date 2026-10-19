"""Optional flexible-lineup metadata, references and availability."""
from copy import deepcopy
import hashlib
import json
import re

STAGES = ('early', 'middle', 'late')

def claim_id(claim):
    if claim.get('id'):
        return claim['id']
    key = {k: claim.get(k) for k in ('section','text','version','condition','inference','kind')}
    return 'claim-' + hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]

def faction_references(meta):
    result = meta.get('required_factions', []) + [b['faction'] for b in meta.get('ban_conditions', [])]
    for variant in meta.get('late_variants', []):
        result += variant.get('required_factions', []) + [b['faction'] for b in variant.get('ban_conditions', [])]
        for condition in variant.get('ban_combinations', []):
            result += condition['factions']
    return list(dict.fromkeys(result))

def references(meta):
    result = faction_references(meta)
    from overview import entity_refs
    result += entity_refs(meta.get('overview', {}))
    for branch in meta.get('player_branches', []):
        result.append(branch['player'])
        overrides=branch.get('overrides',{})
        from overview import entity_refs
        result+=entity_refs(overrides.get('overview',{}))
        result+=overrides.get('core_heroes',[])+overrides.get('required_factions',[])
        for members in overrides.get('compositions',{}).values():
            for member in members:result += [member['hero'],member.get('replaces','')]
        result += [m['target'] for m in overrides.get('matchups',[])]
    for variant in meta.get('late_variants', []):
        result += variant.get('core_heroes', []) + variant.get('required_factions', [])
        result += [b['faction'] for b in variant.get('ban_conditions', [])]
        for member in variant.get('members', []):
            result += [member['hero'], member.get('replaces','')]
    return [r for r in result if r]

def validate(meta, reference, claims=None):
    from major_variants import validate as validate_major
    validate_major(meta, claims)
    if 'overview' in meta:
        from overview import entity_refs
        for value in entity_refs(meta['overview']): reference(value)
        if claims is not None:
            known = {claim_id(c) for c in claims}
            for preset in meta['overview'].get('presets', []):
                for stage in preset.get('stages', {}).values():
                    if set(stage.get('claim_refs', [])) - known: raise ValueError('概览引用了不存在的结论')
    routes, variants = meta.get('operation_routes', []), meta.get('late_variants', [])
    def records(rows):
        if not isinstance(rows,list): raise ValueError('运营节奏与后期组合须为列表')
        ids = set()
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',row['id']):
                raise ValueError('节奏或组合 ID 无效')
            if row['id'] in ids: raise ValueError('节奏或组合 ID 重复')
            ids.add(row['id'])
            if not isinstance(row.get('name'),str) or not row['name'].strip(): raise ValueError('请填写节奏或组合名称')
            for field in ('condition','advantages','risks','transition'):
                if field in row and not isinstance(row[field],str): raise ValueError('说明须为文字')
            if not isinstance(row.get('claim_refs',[]),list) or not all(isinstance(x,str) for x in row.get('claim_refs',[])):
                raise ValueError('结论引用须为 ID 列表')
        return ids
    records(routes)
    variant_ids = records(variants)
    for rows, fields in ((routes, ('condition','advantages','risks','transition','phases','claim_refs','variant_ids')),
                         (variants, ('condition','members','core_heroes','required_factions','ban_conditions','ban_combinations','claim_refs'))):
        for row in rows:
            if not set(fields).issubset(row): raise ValueError('节奏或组合缺少必需字段')
    known_claims = {claim_id(c) for c in claims} if claims is not None else None
    if claims is not None and len(known_claims) != len(claims): raise ValueError('结论 ID 重复')
    def refs(values):
        if not isinstance(values,list) or not all(isinstance(x,str) for x in values): raise ValueError('引用须为列表')
        if known_claims is not None and set(values) - known_claims: raise ValueError('节奏或组合引用了不存在的结论')
    for row in routes + variants:
        refs(row.get('claim_refs',[]))
    for route in routes:
        phases = route.get('phases',{})
        if not isinstance(phases,dict) or set(phases) != set(STAGES): raise ValueError('运营节奏须包含前中后期')
        for values in phases.values(): refs(values)
        if not isinstance(route.get('variant_ids',[]),list) or not all(isinstance(x,str) for x in route.get('variant_ids',[])) or set(route.get('variant_ids',[])) - variant_ids:
            raise ValueError('运营节奏引用了不存在的后期组合')
    for variant in variants:
        for field in ('core_heroes','required_factions'):
            if not isinstance(variant.get(field,[]),list): raise ValueError('组合实体须为列表')
            for value in variant.get(field,[]): reference(value)
        if not isinstance(variant.get('members'),list) or not variant['members']: raise ValueError('后期组合须包含英雄')
        for m in variant['members']:
            if not isinstance(m,dict) or m.get('necessity') not in ('required','optional'): raise ValueError('组合成员无效')
            reference(m.get('hero'))
            if m.get('replaces'): reference(m['replaces'])
            for field in ('role','replacement_note'):
                if field in m and not isinstance(m[field],str): raise ValueError('成员说明须为文字')
        for field in ('ban_conditions','ban_combinations'):
            if not isinstance(variant.get(field,[]),list): raise ValueError('禁用条件须为列表')
            for c in variant.get(field,[]):
                if not isinstance(c,dict) or c.get('status') not in ('playable','unplayable','unknown'): raise ValueError('组合禁用状态无效')
                values = [c.get('faction')] if field == 'ban_conditions' else c.get('factions')
                if not isinstance(c.get('reason',''),str): raise ValueError('禁用原因须为文字')
                if not isinstance(values,list) or not values or not all(isinstance(x,str) for x in values) or len(set(values)) != len(values): raise ValueError('禁用阵营无效')
                for value in values: reference(value)

def variant_availability(meta, variant, banned):
    if not banned: return 'playable'
    banned = set(banned)
    if banned & set(meta.get('required_factions',[]) + variant.get('required_factions',[])): return 'unplayable'
    shared = {c['faction']:c['status'] for c in meta.get('ban_conditions',[])}
    if any(shared.get(f) == 'unplayable' for f in banned): return 'unplayable'
    conditions = {**shared, **{c['faction']:c['status'] for c in variant.get('ban_conditions',[])}}
    if any(conditions.get(f) == 'unplayable' for f in banned): return 'unplayable'
    if len(banned) > 1:
        joint = next((c for c in variant.get('ban_combinations',[]) if set(c['factions']) == banned),None)
        return joint['status'] if joint else 'unknown'
    return conditions.get(next(iter(banned)),'unknown')

def availability(meta, banned):
    statuses = [variant_availability(meta,v,banned) for v in meta['late_variants']]
    return 'playable' if 'playable' in statuses else 'unknown' if 'unknown' in statuses else 'unplayable'

def remap_claims(meta, old_ids, new_id):
    for owner in [meta] + meta.get('player_branches', []):
        for key in ('common_claim_refs','claim_refs','condition_refs'):
            if key in owner:owner[key] = list(dict.fromkeys(new_id if x in old_ids else x for x in owner[key] if x not in old_ids or new_id))
        for row in owner.get('assessment', []):
            row['claim_refs'] = list(dict.fromkeys(new_id if x in old_ids else x for x in row.get('claim_refs',[]) if x not in old_ids or new_id))
    from major_variants import remap as remap_major
    remap_major(meta, old_ids, new_id)
    from overview import remap
    remap(meta.get('overview', {}), old_ids, new_id)
    for branch in meta.get('player_branches',[]):
        remap(branch.get('overrides',{}).get('overview',{}),old_ids,new_id)
    for row in meta.get('operation_routes',[]) + meta.get('late_variants',[]):
        keys = [row]
        if 'phases' in row:
            keys.append(row['phases'])
        for container in keys:
            for key in ('claim_refs',) + STAGES:
                if key in container:
                    container[key] = list(dict.fromkeys(new_id if x in old_ids else x for x in container[key] if x not in old_ids or new_id))

def enrich(meta, rows):
    from reference_store import enrich_meta
    result = deepcopy(meta)
    for variant in result.get('late_variants',[]):
        local = {'core_heroes':variant.get('core_heroes',[]),'required_factions':variant.get('required_factions',[]),
                 'compositions':{'late':variant['members']},'ban_conditions':variant.get('ban_conditions',[])}
        enriched = enrich_meta(local,rows)
        variant['required_factions'] = enriched['required_factions']
        variant['ban_conditions'] = enriched['ban_conditions']
    return result

def render(meta, claims, names, link_refs=None):
    lines = []
    by_id = {claim_id(c):c for c in claims}
    def label(ref): return names.get(ref,ref.removeprefix('pending:'))
    def text_refs(refs):
        if link_refs:return [link_refs(refs)] if refs else []
        return [('推测：' if by_id[r].get('inference') else '') + by_id[r]['text'] + ('（适用条件：' + by_id[r]['condition'] + '）' if by_id[r].get('condition') else '') for r in refs if r in by_id]
    if meta.get('operation_routes'):
        lines += ['## 运营节奏','']
        for route in meta['operation_routes']:
            lines += ['### ' + route['name'],'']
            for field,title in [('condition','适用条件'),('advantages','优势'),('risks','风险'),('transition','转向条件')]:
                lines += [title + '：' + (route.get(field) or '待确认'),'']
            compatible = [v['name'] for v in meta.get('late_variants', []) if v['id'] in route.get('variant_ids', [])]
            if compatible: lines += ['已确认适配组合：' + '、'.join(compatible), '']
            for stage,title in zip(STAGES,('前期','中期','后期')):
                lines += [title + '操作：',''] + ['- '+t for t in text_refs(route['phases'][stage])] + ['']
    if meta.get('late_variants'):
        lines += ['## 推荐后期组合','']
        for variant in meta['late_variants']:
            lines += ['### ' + variant['name'],'','适用条件：'+(variant.get('condition') or '待确认'),'']
            lines += ['组合核心：' + ('、'.join(label(r) for r in variant.get('core_heroes', [])) or '待确认'), '']
            for member in variant['members']:
                t = label(member['hero']) + ('（必需）' if member['necessity']=='required' else '（可选）') + '：'+member.get('role','')
                if member.get('replaces'): t += '；替换 '+label(member['replaces'])
                if member.get('replacement_note'): t += '；'+member['replacement_note']
                lines += ['- '+t,'']
            lines += ['必须阵营：'+('、'.join(label(r) for r in variant.get('required_factions',[])) or '待确认'),'']
            for c in variant.get('ban_conditions',[]) + variant.get('ban_combinations',[]):
                factions = [c['faction']] if 'faction' in c else c['factions']
                lines += ['- '+ '、'.join(label(f) for f in factions)+'被禁：'+{'playable':'可玩','unplayable':'不可玩','unknown':'待确认'}[c['status']]+'。'+c.get('reason',''),'']
            lines += ['- '+t for t in text_refs(variant.get('claim_refs',[]))] + ['']
    return lines
