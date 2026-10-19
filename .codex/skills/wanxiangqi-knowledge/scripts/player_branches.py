"""Explicit player scopes and complete, reversible Markdown reading views."""
from copy import deepcopy
from pathlib import Path
import re
import uuid
from difflib import SequenceMatcher

DIMENSIONS = {'formation':'成型难度','ceiling':'上限','floor':'下限','operation':'操作难度',
              'advantages':'优势','disadvantages':'短板','matchups':'对局关系',
              'environment':'环境适应','top3_rate':'前三率','win_rate':'吃鸡率'}
LINK_FIELDS = {'operation_route_ids':'operation_routes','late_variant_ids':'late_variants',
               'major_variant_ids':'major_variants'}
OVERRIDES = {'required_factions','core_heroes','compositions','ban_conditions','matchups','overview'}


def enabled(note):
    return bool(note.get('meta', {}).get('player_branches'))


def branch(note, player=None):
    rows = note.get('meta', {}).get('player_branches', [])
    if not rows:
        return None
    if player is None:
        return rows[0]
    found = next((b for b in rows if player in (b['id'], b['player'])), None)
    if not found:
        raise ValueError('该打法没有所选棋手分支')
    return found


def refs(value, known, label):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value) or len(set(value)) != len(value) or not set(value) <= known:
        raise ValueError(label + '包含重复或无效引用')
    return set(value)


def validate_assessment(rows, claim_ids):
    if not isinstance(rows, list):
        raise ValueError('打法评价必须是列表')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get('dimension') not in DIMENSIONS or row['dimension'] in seen:
            raise ValueError('评价维度无效或重复')
        seen.add(row['dimension'])
        if not isinstance(row.get('text', ''), str):
            raise ValueError('评价正文无效')
        refs(row.get('claim_refs', []), claim_ids, '评价依据')
        stat = row.get('statistic')
        if stat is not None:
            if row['dimension'] not in ('top3_rate', 'win_rate') or not isinstance(stat, dict):
                raise ValueError('统计维度无效')
            if type(stat.get('value')) not in (int, float) or not 0 <= stat['value'] <= 1:
                raise ValueError('统计比例必须为0到1')
            if type(stat.get('sample_size')) is not int or stat['sample_size'] <= 0 or any(not isinstance(stat.get(k), str) or not stat[k].strip() for k in ('scope','period','source')):
                raise ValueError('胜率统计必须包含样本量、口径、时间范围和来源')


def validate(note):
    if not enabled(note):
        return
    meta = note['meta']; claims = note.get('claims', [])
    ids = [c.get('id') for c in claims]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('棋手分支要求唯一稳定结论ID')
    known = set(ids)
    common = refs(meta.get('common_claim_refs'), known, '共通结论')
    validate_assessment(meta.get('assessment', []), common)
    owned = set(common); players = set(); bids = set()
    for b in meta['player_branches']:
        if not isinstance(b, dict) or not re.fullmatch(r'[A-Za-z0-9_-]+', b.get('id', '')) or b['id'] in bids:
            raise ValueError('棋手分支ID无效或重复')
        bids.add(b['id'])
        if b.get('player') not in meta.get('players', []) or b['player'] in players:
            raise ValueError('棋手分支与适用棋手不一致')
        players.add(b['player'])
        private = refs(b.get('claim_refs'), known, '棋手结论')
        if private & common:
            raise ValueError('同一结论不能同时属于共通与棋手专属')
        owned |= private
        available = common | private
        refs(b.get('condition_refs', []), available, '采用条件')
        overrides = b.get('overrides', {})
        if not isinstance(overrides, dict) or set(overrides) - OVERRIDES:
            raise ValueError('棋手覆盖字段无效')
        if 'compositions' in overrides and (not isinstance(overrides['compositions'], dict) or set(overrides['compositions']) - {'early','middle','late'}):
            raise ValueError('棋手成员阶段无效')
        for key, field in LINK_FIELDS.items():
            refs(b.get(key, []), {r['id'] for r in meta.get(field, [])}, '棋手' + key)
        validate_assessment(b.get('assessment', []), available)
    if owned != known:
        raise ValueError('存在尚未指定共通或棋手归属的结论：' + '、'.join(sorted(known-owned)))
    if players != set(meta.get('players', [])):
        raise ValueError('每个适用棋手必须有完整分支')


def project(note, player=None):
    if not enabled(note):
        return deepcopy(note)
    b = branch(note, player); result = deepcopy(note); meta = result['meta']
    allowed = set(meta['common_claim_refs']) | set(b['claim_refs'])
    result['claims'] = [c for c in result['claims'] if c['id'] in allowed]
    meta['players'] = [b['player']]
    for key, value in b.get('overrides', {}).items():
        if key == 'compositions':
            meta[key].update(deepcopy(value))
        else:
            meta[key] = deepcopy(value)
    for key, field in LINK_FIELDS.items():
        meta[field] = [row for row in meta.get(field, []) if row['id'] in b.get(key, [])]
    if meta.get('overview'):
        meta['overview']['presets'] = [p for p in meta['overview'].get('presets', []) if not p.get('players') or any(x.get('player') == b['player'] for x in p['players'])]
        for preset in meta['overview']['presets']:
            for stage in preset.get('stages',{}).values():stage['claim_refs']=[x for x in stage.get('claim_refs',[]) if x in allowed]
    # Project relationships too: a reading view cannot expose the other player's claims.
    for row in meta.get('operation_routes', []):
        row['claim_refs'] = [x for x in row.get('claim_refs', []) if x in allowed]
        row['phases'] = {k:[x for x in v if x in allowed] for k,v in row['phases'].items()}
        row['variant_ids'] = [x for x in row.get('variant_ids', []) if x in b.get('late_variant_ids', [])]
    for row in meta.get('late_variants', []):
        row['claim_refs'] = [x for x in row.get('claim_refs', []) if x in allowed]
    for row in meta.get('major_variants', []):
        for key in ('condition_refs','baseline_refs','claim_refs'):
            row[key] = [x for x in row.get(key, []) if x in allowed]
        row['operation_route_ids'] = [x for x in row.get('operation_route_ids', []) if x in b.get('operation_route_ids', [])]
        row['late_variant_ids'] = [x for x in row.get('late_variant_ids', []) if x in b.get('late_variant_ids', [])]
        for dim in row.get('differences', {}).values():
            dim['claim_refs'] = [x for x in dim.get('claim_refs', []) if x in allowed]
    meta['assessment'] = list({a['dimension']:deepcopy(a) for a in [*meta.get('assessment', []),*b.get('assessment', [])]}.values())
    meta.pop('player_branches', None);meta.pop('common_claim_refs', None)
    result['selected_player'] = b['player'];result['selected_branch'] = b['id']
    result['branch_path'] = document_path(note, b)
    if 'guide_related' in result:
        result['guide_related']=[x for x in result['guide_related'] if x.get('branch',b['id'])==b['id'] and x.get('exclude_branch')!=b['id']]
        result['related']=[x for x in result.get('related',[]) if x.get('player',b['player'])==b['player']]
    if result.get('reading_layout',{}).get('version') in (2,3):
        from guide_layout import project_matchups
        project_matchups(result)
    return result


def player_name(note, b):
    return note.get('entity_names', {}).get(b['player'], b.get('name') or b['player'])


def document_path(note, b):
    from workspace import filename
    return str(Path(note['path']).parent / (filename(note['title']) + '-' + filename(player_name(note,b)) + '.md')).replace('\\','/')


def editable_claim_text(note,c):
    if note.get('reading_layout',{}).get('version')==3:
        from guide_layout import claim_text
        return claim_text(c,3)
    return c['text']

def sections_for(note, scope):
    b = None if scope == 'common' else branch(note, scope)
    ids = note['meta']['common_claim_refs'] if b is None else b['claim_refs']
    result = {}
    for c in note['claims']:
        if c['id'] in ids:
            result.setdefault(c['section'], []).append(editable_claim_text(note,c))
    return {s:'\n\n'.join(texts) for s,texts in result.items()}


def configuration(note, scope):
    """Human names, rather than internal IDs, form the reversible table cells."""
    meta=note['meta'] if scope=='common' else branch(note,scope).get('overrides',{})
    names=note.get('entity_names',{})
    def cell(value):return str(value).replace('\\','\\\\').replace('|','\\|').replace('\n','<br>')
    def name(value):return names.get(value,value.removeprefix('pending:')) if value else ''
    rows=[]
    for field,label in [('required_factions','必须阵营'),('core_heroes','核心英雄')]:
        for ref in meta.get(field,[]):rows.append([label,name(ref),'','','','',''])
    for stage,label in [('early','前期'),('middle','中期'),('late','后期')]:
        members=meta.get('compositions',{}).get(stage)
        if members is not None:
            if not members:rows.append([label,'（空）','','','','',''])
            for m in members:rows.append([label,name(m['hero']),'必需' if m['necessity']=='required' else '可选',m.get('role',''),name(m.get('replaces','')),m.get('replacement_note',''),''])
    for b in meta.get('ban_conditions',[]):rows.append(['禁用',name(b['faction']),{'playable':'可玩','unplayable':'不可玩','unknown':'待确认'}[b['status']],b.get('reason',''),'','',''])
    for m in meta.get('matchups',[]):rows.append(['对局',name(m['target']),'',m.get('text',''),'',m.get('condition',''),''])
    return '| 类型 | 名称 | 要求／状态 | 作用／说明 | 替换 | 条件 | 备注 |\n|---|---|---|---|---|---|---|\n'+'\n'.join('| '+' | '.join(cell(v) for v in row)+' |' for row in rows)


def apply_configuration(note,scope,text):
    if text.strip()==configuration(note,scope).strip():return False
    target=note['meta'] if scope=='common' else branch(note,scope).setdefault('overrides',{})
    names=dict(note.get('entity_names',{}));lookup={}
    from tactics import references
    for value in references(note['meta']):
        if value.startswith('pending:'):names.setdefault(value,value.removeprefix('pending:'))
    for ref,name in names.items():lookup.setdefault(name,[]).append(ref)
    def ref(name,category=None):
        hits=[r for r in lookup.get(name,[]) if category is None or r.startswith(category+':') or r.startswith('pending:')]
        if len(hits)!=1:raise ValueError('名称未知或不唯一：'+name)
        return hits[0]
    updated={'required_factions':[],'core_heroes':[],'compositions':{},'ban_conditions':[],'matchups':[]}
    lines=text.strip().splitlines()
    if len(lines)<2 or not lines[0].startswith('| 类型 |') or not lines[1].startswith('|---'):raise ValueError('成员配置请保留表头')
    for line in lines[2:]:
        if not line.strip():continue
        cells=[c.strip().replace('<br>','\n').replace('\\|','|').replace('\\\\','\\') for c in re.split(r'(?<!\\)\|',line.strip())[1:-1]]
        if len(cells)!=7:raise ValueError('成员配置应为七列表格')
        kind,name,status,role,replaces,condition,_=cells
        if kind in ('必须阵营','核心英雄'):updated['required_factions' if kind=='必须阵营' else 'core_heroes'].append(ref(name,'faction' if kind=='必须阵营' else 'card'))
        elif kind in ('前期','中期','后期'):
            stage={'前期':'early','中期':'middle','后期':'late'}[kind];members=updated['compositions'].setdefault(stage,[])
            if name=='（空）':continue
            if status not in ('必需','可选'):raise ValueError('成员要求须为必需或可选')
            members.append(dict(hero=ref(name,'card'),necessity='required' if status=='必需' else 'optional',role=role,replaces=ref(replaces,'card') if replaces else '',replacement_note=condition))
        elif kind=='禁用':
            if status not in ('可玩','不可玩','待确认'):raise ValueError('禁用状态无效')
            updated['ban_conditions'].append(dict(faction=ref(name,'faction'),status={'可玩':'playable','不可玩':'unplayable','待确认':'unknown'}[status],reason=role))
        elif kind=='对局':updated['matchups'].append(dict(target=ref(name),condition=condition,text=role))
        else:raise ValueError('未知成员配置类型：'+kind)
    if scope=='common':updated['compositions']={k:updated['compositions'].get(k,[]) for k in ('early','middle','late')}
    target.update(updated)
    note.setdefault('manual_scopes',{}).setdefault(scope,[]).append('成员配置')
    return True


def assessment_markdown(rows):
    lines = []
    for a in rows:
        stat = a.get('statistic')
        value = a.get('text', '')
        if stat:
            value = f"{stat['value']:.1%}；样本{stat['sample_size']}；{stat['scope']}；{stat['period']}；{stat['source']}"
        if value:
            lines.append('- **' + DIMENSIONS[a['dimension']] + '**：' + value)
    if not any(a['dimension'] in ('top3_rate','win_rate') and a.get('statistic') for a in rows):
        lines.append('- **前三率／吃鸡率**：暂无可靠统计。')
    return '\n'.join(lines)


def scope_markdown(note, scope):
    result = []
    b = None if scope == 'common' else branch(note, scope)
    rows = note['meta'].get('assessment', []) if b is None else b.get('assessment', [])
    if rows:
        result += ['### 打法评价', '', assessment_markdown(rows), '']
    result += ['### '+('共同成员与依赖' if scope=='common' else '成员与替换'),'',configuration(note,scope),'']
    if b is not None and b.get('selection'):
        result += ['### 采用与转向信号','',selection_markdown(b['selection']),'']
    sections=sections_for(note,scope)
    fixed=['核心机制','共通操作与对局原则'] if scope=='common' else ['采用条件与优势短板','前期运营','中期启动','后期提升','三轮拍卖','天赋、装备与站位','对局应对与战后复盘']
    for section in dict.fromkeys([*fixed,*sections]):
        text=sections.get(section,'暂无已确认的'+('通用' if scope=='common' else '本棋手专属')+'策略。')
        result += ['### ' + section, '', text, '']
    return '\n'.join(result).rstrip() + '\n'


def selection_markdown(selection):
    rows=[('采用',selection.get('adopt','')),('转向',selection.get('avoid','')),*selection.get('signals',{}).items()]
    return '| 判断 | 内容 |\n|---|---|\n'+'\n'.join('| '+str(k).replace('|','\\|')+' | '+str(v).replace('|','\\|').replace('\n','<br>')+' |' for k,v in rows)


def documents(note):
    if not enabled(note):
        return {}
    if note.get('reading_layout',{}).get('version') in (2,3):
        from guide_layout import render
        return {document_path(note,b):render(note,b['id']) for b in note['meta']['player_branches']}
    if note.get('reading_layout',{}).get('preserve_original'):
        from original_layout import render
        return {document_path(note,b):render(note,b['id']) for b in note['meta']['player_branches']}
    common = scope_markdown(note, 'common')
    return {document_path(note,b):f"# {note['title']}-{player_name(note,b)}\n\n## 通用打法\n\n{common}\n## {player_name(note,b)}打法\n\n{scope_markdown(note,b['id'])}" for b in note['meta']['player_branches']}


def entry_markdown(note):
    lines = ['# ' + note['title'], '', '选择棋手，阅读包含共通机制与该棋手完整运营的打法。', '']
    for b in note['meta']['player_branches']:
        lines += ['- [' + player_name(note,b) + '](' + Path(document_path(note,b)).name + ')', '']
    return '\n'.join(lines)


def update_player_adaptations(items):
    for note in items:
        if note['type']!='player':continue
        players=set(note.get('entities',[]));adaptations=[]
        for lineup in items:
            for b in lineup.get('meta',{}).get('player_branches',[]):
                if b['player'] not in players:continue
                selected=project(lineup,b['id']);meta=selected['meta']
                names=lineup.get('entity_names',{})
                rows={a['dimension']:a['text'] for a in meta.get('assessment',[])}
                adaptations.append({'lineup':lineup['id'],'branch':b['id'],'title':lineup['title'],'path':document_path(lineup,b),
                    'selection':deepcopy(b.get('selection',{})),
                    'required_factions':[names.get(f,f) for f in meta['required_factions']],
                    'advantages':rows.get('advantages','暂无已确认结论'), 'disadvantages':rows.get('disadvantages','暂无已确认结论')})
        if adaptations:note['lineup_adaptations']=adaptations


def render_adaptations(note):
    rows=note.get('lineup_adaptations',[])
    if not rows:return []
    lines=['## 适用打法与选择','']
    for row in rows:
        selection=row.get('selection',{})
        lines+=['### ['+row['title']+'](../lineups/'+Path(row['path']).name+')','',
                '采用信号：'+selection.get('adopt','缺少明确判断边界。'),'',
                '放弃或转向信号：'+selection.get('avoid','缺少明确判断边界。'),'',
                '必须阵营：'+('、'.join(row['required_factions']) or '暂无已确认条件')+'。','',
                '优势：'+row['advantages'],'','短板：'+row['disadvantages'],'']
        for label,value in selection.get('signals',{}).items():lines+=[label+'：'+value,'']
    return lines


def parse_document(text, note, bid):
    if note.get('reading_layout',{}).get('version') in (2,3):
        from guide_layout import parse
        return parse(text,note,bid)
    if note.get('reading_layout',{}).get('preserve_original'):
        from original_layout import parse
        return parse(text,note,bid)
    b = branch(note,bid);expected = f"# {note['title']}-{player_name(note,b)}"
    lines = text.replace('\r\n','\n').splitlines()
    if not lines or lines[0] != expected:
        raise ValueError('Markdown标题与棋手文件不一致')
    common_heading = '## 通用打法';private_heading = '## ' + player_name(note,b) + '打法'
    result = {'common':{},'branch':{}};seen = set();current = None;section = None;buffer = [];fence = None
    def flush():
        nonlocal buffer
        if section is not None:
            result[current][section] = '\n'.join(buffer).strip()
        elif any(line.strip() for line in buffer):
            raise ValueError('请把正文写在三级章节下')
        buffer = []
    for line in lines[1:]:
        marker = re.match(r'^(`{3,}|~{3,})', line)
        if marker:
            if fence is None:fence = marker[1][0]
            elif marker[1][0] == fence:fence = None
            buffer.append(line);continue
        if fence:
            buffer.append(line);continue
        if line.startswith('## '):
            flush()
            if line not in (common_heading,private_heading) or line in seen:
                raise ValueError('Markdown作用域重复或未知')
            seen.add(line);current = 'common' if line == common_heading else 'branch';section = None
        elif line.startswith('### '):
            flush()
            if current is None or not line[4:].strip() or line[4:].strip() in result[current]:
                raise ValueError('Markdown章节重复或缺少作用域')
            section = line[4:].strip()
        elif line.startswith('# '):
            raise ValueError('Markdown只能包含一个主标题')
        else:
            buffer.append(line)
    if fence:
        raise ValueError('Markdown代码块尚未闭合')
    flush()
    if seen != {common_heading,private_heading}:
        raise ValueError('缺少通用或棋手专属作用域')
    return result


def apply_sections(note, scope, sections):
    """Apply an explicit human edit without attaching old video evidence to it."""
    from tactics import remap_claims
    target = note['meta'] if scope == 'common' else branch(note, scope)
    ref_key = 'common_claim_refs' if scope == 'common' else 'claim_refs'
    owned = set(target[ref_key]);changed = False
    for section, text in sections.items():
        if not isinstance(section, str) or not section.strip() or not isinstance(text, str):
            raise ValueError('章节名称或正文无效')
        if section.startswith(('运营路线：','后期组合：')):
            from tactical_edit import sections as tactical_sections,apply
            if text.strip()==tactical_sections(note,scope).get(section,'').strip():continue
            apply(note,scope,section,text);changed=True;continue
        if section == ('共同成员与依赖' if scope=='common' else '成员与替换'):
            changed=apply_configuration(note,scope,text) or changed
            continue
        if section=='采用与转向信号' and scope!='common':
            if text.strip()==selection_markdown(target.get('selection',{})).strip():continue
            rows=[]
            for line in text.strip().splitlines()[2:]:
                cells=[v.strip().replace('\\|','|').replace('<br>','\n') for v in re.split(r'(?<!\\)\|',line)[1:-1]]
                if len(cells)!=2:raise ValueError('采用与转向信号请保留两列表格')
                rows.append(cells)
            values=dict(rows)
            if len(values)!=len(rows) or not {'采用','转向'}<=values.keys():raise ValueError('采用与转向信号缺失或重复')
            target['selection']={'adopt':values.pop('采用'),'avoid':values.pop('转向'),'signals':values,'origin':'manual'}
            note.setdefault('manual_scopes',{}).setdefault(scope,[]).append(section);changed=True;continue
        if section == '打法评价':
            old = assessment_markdown(target.get('assessment', [])) if target.get('assessment') else ''
            if text.strip() == old.strip():continue
            rows = []
            for line in text.strip().splitlines():
                if not line.strip():continue
                m = re.fullmatch(r'- \*\*(.+?)\*\*：(.+)', line)
                if not m:raise ValueError('打法评价请保持“名字：内容”的原有列表格式')
                if m[1] == '前三率／吃鸡率' and m[2] == '暂无可靠统计。':continue
                dimension = next((k for k,v in DIMENSIONS.items() if v == m[1]), None)
                if not dimension:raise ValueError('未知评价维度')
                prior = next((x for x in target.get('assessment', []) if x['dimension'] == dimension), {})
                row = {'dimension':dimension,'text':m[2],'claim_refs':[],'origin':'manual'}
                if dimension in ('top3_rate','win_rate'):
                    if m[2] == '暂无可靠统计。':continue
                    stat = re.fullmatch(r'([\d.]+)%；样本(\d+)；(.+?)；(.+?)；(.+)', m[2])
                    if not stat:raise ValueError('统计必须保留比例、样本、口径、时间和来源')
                    row['statistic'] = dict(value=float(stat[1])/100,sample_size=int(stat[2]),scope=stat[3],period=stat[4],source=stat[5])
                elif prior.get('text') == row['text']:
                    row = deepcopy(prior)
                rows.append(row)
            validate_assessment(rows, {c['id'] for c in note['claims']})
            target['assessment'] = rows
            note.setdefault('manual_scopes',{}).setdefault(scope,[]).append(section)
            changed = True;continue
        old = [c for c in note['claims'] if c['id'] in owned and c['section'] == section]
        if not old and text.strip()=='暂无已确认的'+('通用' if scope=='common' else '本棋手专属')+'策略。':continue
        if '\n\n'.join(editable_claim_text(note,c) for c in old).strip() == text.strip():continue
        # Copy-on-write: two players may cite one conclusion until one of them
        # edits it. That player's edit must never mutate the other's text/refs.
        elsewhere=set(x for b in note['meta']['player_branches'] if b is not target for x in b['claim_refs'])
        shared={c['id'] for c in old if c['id'] in elsewhere} if scope!='common' else set()
        clones={cid:'manual-'+uuid.uuid4().hex[:16] for cid in shared}
        if clones:
            locations=note.get('reading_layout',{}).get('claim_locations',{})
            for cid,newid in clones.items():
                if cid in locations:locations[newid]=deepcopy(locations[cid])
            for c in old:
                if c['id'] in clones:
                    clone=deepcopy(c);clone['id']=clones[c['id']];note['claims'].append(clone)
            # Remap only this branch and routes exclusive to it.
            from tactics import remap_claims
            route_fields={field:[deepcopy(r) for r in note['meta'].get(field,[]) if r['id'] in target.get(key,[]) and not any(r['id'] in b.get(key,[]) for b in note['meta']['player_branches'] if b is not target)] for key,field in LINK_FIELDS.items()}
            local={'player_branches':[target],**route_fields}
            for cid,newid in clones.items():remap_claims(local,{cid},newid)
            for field,rows in route_fields.items():
                updates={r['id']:r for r in rows};note['meta'][field]=[updates.get(r['id'],r) for r in note['meta'].get(field,[])]
            owned=set(target[ref_key]);old=[c for c in note['claims'] if c['id'] in owned and c['section']==section]
        # Unchanged blocks retain their original IDs/evidence; changed blocks retain
        # the matching position's ID and store the complete old claims in history.
        blocks = [p.strip() for p in re.split(r'\n\s*\n',text.strip()) if p.strip()]
        locations=note.get('reading_layout',{}).get('claim_locations',{})
        fallback=next((locations[c['id']] for c in old if c['id'] in locations),None)
        matcher = SequenceMatcher(None,[editable_claim_text(note,c) for c in old],blocks,autojunk=False)
        replacement = [];removed = set();old_ids = {c['id'] for c in old}
        for op,a0,a1,b0,b1 in matcher.get_opcodes():
            if op == 'equal':replacement.extend(deepcopy(old[a0:a1]));continue
            for offset, block in enumerate(blocks[b0:b1]):
                cid = old[a0+offset]['id'] if a0+offset < a1 else 'manual-' + uuid.uuid4().hex[:16]
                replacement.append({'id':cid,'section':section,'text':block,'origin':'manual','kind':'general_strategy','condition':'','version':None,'inference':False,'evidence':[]})
                if note.get('reading_layout',{}).get('version')==3:
                    from guide_layout import parse_claim_text
                    replacement[-1].update(parse_claim_text(block))
                if fallback and cid not in locations:locations[cid]=deepcopy(fallback)
            removed |= {c['id'] for c in old[a0:a1]} - {c['id'] for c in replacement}
        at = next((i for i,c in enumerate(note['claims']) if c['id'] in old_ids), len(note['claims']))
        note['claims'] = [c for c in note['claims'] if c['id'] not in old_ids]
        note['claims'][at:at] = replacement
        new_ids = [c['id'] for c in replacement]
        for cid in removed:
            remap_claims(note['meta'],{cid},new_ids[0] if new_ids else None)
            for owner, key in [(note['meta'],'common_claim_refs')] + [(b,'claim_refs') for b in note['meta']['player_branches']]:
                owner[key] = list(dict.fromkeys(x for x in owner[key] if x != cid))
        target[ref_key] = list(dict.fromkeys([x for x in target[ref_key] if x not in old_ids] + new_ids))
        owned = set(target[ref_key]);changed = True
        protected = note.setdefault('manual_scopes', {}).setdefault(scope, [])
        if section not in protected:protected.append(section)
    return changed
