"""Reader layout profiles. These do not change the knowledge data contract."""
from pathlib import Path
import re
from major_variants import render as render_major, containers

def major_refs(meta):
    baseline={cid for row in meta.get('major_variants',[]) for cid in row['baseline_refs']}
    return {cid for row in meta.get('major_variants',[]) for box in containers(row) for key in ('condition_refs','claim_refs') for cid in box.get(key,[])}-baseline

PROFILE_ID = 'yaomei-sacrifice-lixin'
# Each claim has exactly one primary location. Route references remain data,
# rather than causing the same paragraphs to be printed a second time.
GROUPS = [
 ('阵容概览与成员清单', [('阵容选择', ['composition-ming'])]),
 ('禁用阵营与适用条件', [('', ['ban-core'])]),
 ('成长机制与关键节点', [('', ['growth-sacrifice','growth-deer','growth-zhongkui','growth-ming','growth-hundred','growth-deer-timeline','growth-taiyi'])]),
 ('主要变阵', []),
 ('运营路线选择', []),
 ('前中后期共通流程', [
  ('前期：保血与升本', ['opening-four','opening-missing','opening-level-plan','opening-wins','opening-blood-cushion']),
  ('中期：找李信与缺牌应变', ['middle-budget','middle-fast-five','route-four-core','middle-item-holder','six-budget-pressure','middle-no-lixin','middle-hold-four','middle-ming-choice','ming-first-lixin']),
  ('后期：等级培养与操作顺序', ['late-play-slot','late-bank-six','level-without-ming','level-effect-cards','level-play-batch','order-six-before-double'])]),
 ('三轮拍卖与天赋选择', [
  ('第一轮拍卖', ['auction-one-budget']), ('第二轮拍卖', ['auction-two-lixin']), ('第三轮拍卖', ['auction-three-growth']),
  ('天赋选择', ['talent-tyrant','talent-economy','talent-final-guard'])]),
 ('装备与站位', [
  ('李信：基础装备与换装', ['equipment-rebuild','equipment-current-default','equipment-armor-lives','equipment-time-stage','equipment-control-duration','equipment-cleanse-choice','equipment-thunder']),
  ('小鹿：保护李信与奉献', ['equipment-deer-pressure','equipment-deer-cover']),
  ('共同站位与复生形态', ['position-deer-back','taiyi-by-target'])]),
 ('对局威胁与应对', [
  ('海月、百里守约：爆发与牺牲控制', ['counter-haiyue-zhong','equipment-burst-counter']),
  ('班叔、杨玉环、诸葛亮：屏障与持续施法', ['counter-barrier','equip-milk-bell','equip-sanfen-support']),
  ('嬴政：远程输出与解控', ['equip-warplane']),
  ('东皇太一、敖隐：前排与回复', ['equip-dahe-front']),
  ('艾琳：减速与风筝', ['equipment-double-reflect','equipment-kite']),
  ('孙尚香：小鹿奉献前击败李信', ['equipment-mingdao-conditional']),
  ('钟馗：开局勾走李信', ['position-hook-bait'])]),
 ('终局检查与待裁决', [
  ('终局检查', ['late-revive-dilution','talent-guardian-reinforcement','combat-reborn-form']),
  ('尚待裁决', ['ming-wakeup-conflict','equipment-ailin-pending'])]),
]

ROUTE_DETAILS = {
 'ming-growth': ('李信、明世隐、钟馗、太乙真人；铠、盾山、程咬金按缺口选', '以明世隐固定量和保血能力决定升本，不固定停留回合'),
 'four-core': ('四本先找李信、明世隐、钟馗、铠；太乙真人补复生', '四本齐牌后存钱；第14回合预留六本预算，第15回合先升六本再用共鸣'),
 'four-hold': ('李信、明世隐；钟馗、太乙真人补牺牲和复生', '第8—11回合四本培养；第三轮拍卖后升五本；第14回合预留六本预算'),
}


def _render_markdown(note):
    meta = note.get('meta', {})
    names = note.get('entity_names', {})
    label = lambda ref: names.get(ref, ref.removeprefix('pending:'))
    claims = [c for c in note.get('claims', []) if c.get('kind') in {'mechanic','general_strategy','conditional_strategy'}]
    by_id = {c.get('id'): c for c in claims}
    used = set()
    reserved=major_refs(meta)
    locations={cid:title for title,groups in GROUPS for _,ids in groups for cid in ids}
    locations.update({cid:'主要变阵' for cid in reserved})
    def links(ids):
        titles=list(dict.fromkeys(locations.get(cid,'终局检查与待裁决') for cid in ids if cid in by_id))
        return ['参见'+ '、'.join('['+title+'](#chapter-'+str([g[0] for g in GROUPS].index(title)+1)+')' for title in titles)] if titles else ['待确认']
    lines = ['# ' + note['title'], '']

    def emit(ids,force=False):
        for cid in ids:
            if cid not in by_id or cid in used or cid in reserved and not force:
                continue
            c = by_id[cid]
            text = c['text']
            condition = c.get('condition', '').strip()
            if condition and condition not in text:
                text = f'当{condition}{"" if condition.endswith("时") else "时"}，{text}'
            if c.get('inference'):
                text = '推测：' + text
            lines.extend(['- ' + text, ''])
            used.add(cid)

    def members(rows):
        if not rows:
            return
        lines.extend(['| 英雄 | 必需或可选 | 作用与替换条件 |', '|---|---|---|'])
        for row in rows:
            role = row.get('role', '')
            if row.get('replaces'):
                role += '；替换' + label(row['replaces'])
            if row.get('replacement_note'):
                role += '；' + row['replacement_note']
            lines.append(f'| {label(row["hero"])} | {"必需" if row["necessity"] == "required" else "可选"} | {role.replace("|", "、")} |')
        lines.append('')

    for title, groups in GROUPS:
        if title=='主要变阵':
            def take(ids):
                before=len(lines);emit([cid for cid in ids if cid in reserved],True);result=lines[before:];del lines[before:]
                return result or links(ids)
            lines.extend(render_major(meta,take,links));continue
        lines.extend(['## ' + title, ''])
        if title == '阵容概览与成员清单':
            for field, heading in [('players','适用棋手'),('core_heroes','核心输出'),('required_factions','必须阵营')]:
                lines.extend([heading + '：' + ('、'.join(label(x) for x in meta.get(field, [])) or '待确认'), ''])
            lines.extend(['### 前期过渡英雄', ''])
            members(meta.get('compositions', {}).get('early', []))
            lines.extend(['### 中期共同骨架', ''])
            members(meta.get('compositions', {}).get('middle', []))
            for variant in meta.get('late_variants', []):
                lines.extend(['### 后期：' + variant['name'], '', '适用条件：' + (variant.get('condition') or '待确认'), ''])
                members(variant['members'])
        if title == '运营路线选择':
            lines.extend(['三条路线共用下文的保血、站位和装备规则；这里比较找牌与升本的差异。', '',
                          '| 路线 | 适用条件 | 找牌目标 | 升本节点 | 优势 | 风险与转向 |', '|---|---|---|---|---|---|'])
            for route in meta.get('operation_routes', []):
                targets, timing = ROUTE_DETAILS.get(route['id'], ('暂无已确认的通用策略','暂无已确认的通用策略'))
                cells = [route['name'], route.get('condition','待确认'), targets, timing, route.get('advantages','待确认'), route.get('risks','待确认').rstrip('。；') + '；' + route.get('transition','待确认')]
                lines.append('| ' + ' | '.join(c.replace('|','、').replace('\n',' ') for c in cells) + ' |')
            lines.append('')
        for subtitle, ids in groups:
            if subtitle and any(cid in by_id for cid in ids):
                lines.extend(['### ' + subtitle, ''])
            emit(ids)
    remaining = [c for c in claims if c.get('id') not in used]
    if remaining:
        lines.extend(['### 补充规则', ''])
        # Keep future and manual claims visible instead of silently dropping them.
        for c in remaining:
            lines.extend(['- ' + c['text'], ''])
    lines.extend(['## 关联知识', ''])
    for link in note.get('related', []):
        path = Path(link.get('path', 'knowledge/' + ('lineups' if link['type'] == 'lineup' else 'players') + '/' + link['id'] + '.md'))
        lines.append(f'- [{link["title"]}](../{path.parent.name}/{path.name})')
    if not note.get('related'):
        lines.append('暂无')
    return '\n'.join(lines) + '\n'


def _render_generic(note):
    import wxq
    from tactics import claim_id,render as render_tactics
    from workspace import FACTIONS
    meta=note.get('meta',{});names={f['id']:f['name'] for f in FACTIONS};names.update(note.get('entity_names',{}))
    label=lambda ref:names.get(ref,ref.removeprefix('pending:'))
    claims=[{**c,'id':claim_id(c)} for c in note.get('claims',[]) if c.get('kind') in wxq.KNOWLEDGE_KINDS]
    by_id={c['id']:c for c in claims};used=set();reserved=major_refs(meta)
    sections=['阵容信息',*wxq.SECTIONS['lineup']]
    sections.insert(sections.index('核心机制')+1,'主要变阵')
    sections.insert(sections.index('主要变阵')+1,'运营路线与后期组合')
    sections += sorted({c['section'] for c in claims}-set(sections))+['关联知识']
    if note.get('reading_layout',{}).get('preserve_original'):
        sections=note['reading_layout']['sections']
    locations={c['id']:'主要变阵' if c['id'] in reserved else c['section'] for c in claims}
    def links(ids):
        titles=list(dict.fromkeys(locations[cid] for cid in ids if cid in locations))
        return ['参见'+'、'.join('['+title+'](#chapter-'+str(sections.index(title)+1)+')' for title in titles)] if titles else ['待确认']
    def emit(ids):
        out=[]
        for cid in ids:
            if cid not in by_id:continue
            if cid in used:out+=links([cid]);continue
            used.add(cid);c=by_id[cid];text=c['text'];condition=c.get('condition','').strip()
            if condition and condition not in text:text=f'当{condition}{"" if condition.endswith("时") else "时"}，{text}'
            out+=['- '+('推测：' if c.get('inference') else '')+text,'']
        return out
    lines=['# '+note['title'],'']
    def major_emit(ids):
        primary=[cid for cid in ids if cid in reserved]
        baseline=[cid for cid in ids if cid not in reserved]
        return emit(primary)+(links(baseline) if baseline else [])
    for section in sections:
        if section=='主要变阵':lines+=render_major(meta,major_emit,links);continue
        lines+=['## '+section,'']
        if section=='阵容信息':
            for field,title in [('players','适用棋手'),('core_heroes','核心英雄'),('required_factions','必须阵营')]:lines += [title+'：'+('、'.join(label(x) for x in meta.get(field,[])) or ('随组合查看，无全局共同要求' if meta.get('late_variants') and field!='players' else '待确认')),'']
            for stage,title in [('early','前期'),('middle','中期'),('late','后期')]:
                lines += ['### '+title+'英雄组成','']
                for m in meta.get('compositions',{}).get(stage,[]):lines += ['- '+label(m['hero'])+('（必需）' if m['necessity']=='required' else '（可选）')+'：'+m.get('role','')+('；替换'+label(m['replaces']) if m.get('replaces') else '')+('；'+m['replacement_note'] if m.get('replacement_note') else ''),'']
        elif section=='运营路线与后期组合':
            lines+=[('#'+line if line.startswith('##') else line) for line in render_tactics(meta,claims,names,link_refs=lambda ids:'；'.join(links(ids)))]
        elif section=='关联知识':
            for r in note.get('related',[]):
                path=Path(r.get('path','knowledge/'+('lineups' if r.get('type')=='lineup' else 'players')+'/'+r['id']+'.md'));lines+=['- ['+r['title']+'](../'+path.parent.name+'/'+path.name+')','']
            if not note.get('related'):lines+=['暂无','']
        else:
            ids=[c['id'] for c in claims if c['section']==section and c['id'] not in reserved]
            content=emit(ids);lines+=content or ['暂无已确认的通用策略','']
            if section=='禁用阵营适用情况':
                for c in meta.get('ban_conditions',[]):lines+=['- '+label(c['faction'])+'被禁：'+{'playable':'可玩','unplayable':'不可玩','unknown':'待确认'}[c['status']]+'。'+c.get('reason',''),'']
            if section=='克制手段':
                for m in meta.get('matchups',[]):lines+=['- 针对'+label(m['target'])+'：'+m.get('condition','')+' '+m['text'],'']
    return '\n'.join(lines)+'\n'

def reading_document(note, player=None):
    """Read-only presentation projection shared with the exported Markdown."""
    result = {'note_id': note['id'], 'revision': note.get('revision', ''),
              'profile': None, 'sections': [], 'section_aliases': {}}
    if note.get('type') not in ('lineup','player') and not note.get('lineup_adaptations'):
        return result
    if note.get('type') != 'lineup':
        import wxq
        markdown=wxq.render_note(note,{})
        headings=list(re.finditer(r'^## (.+)\n',markdown,re.M))
        result['profile']='player-v5'
        result['section_aliases']=dict(wxq.PLAYER_SECTION_ALIASES)
        result['sections']=[{'id':f'chapter-{i+1}','title':m[1],'markdown':markdown[m.end():headings[i+1].start() if i+1<len(headings) else len(markdown)].strip()+'\n'} for i,m in enumerate(headings)]
        return result
    from player_branches import enabled, project, branch, player_name, assessment_markdown
    is_branch = enabled(note)
    if is_branch:
        _family=note
        b = branch(note,player)
        result.update(player=b['player'],branch=b['id'],player_options=[{'id':x['player'],'name':player_name(note,x)} for x in note['meta']['player_branches']])
        from player_branches import documents, document_path, parse_document
        result['scope_sections']=parse_document(documents(note)[document_path(note,b)],note,b['id'])
        note = project(note,player)
        result['projected_note']=note
        if note.get('reading_layout',{}).get('version') in (2,3):
            import guide_layout
            from original_layout import split_chapters
            text=guide_layout.render(_family,b['id']);body=split_chapters(text)
            result['profile']='lineup-v5';result['layout_version']=note['reading_layout']['version']
            result['opening']=text.split('\n\n',1)[1].split('\n## ',1)[0].strip()
            result['sections']=[{'id':f'chapter-{i+1}','title':s,'markdown':value+'\n'} for i,(s,value) in enumerate(body.items())]
            result['section_aliases']=guide_layout.ALIASES
            result['coverage']=guide_layout.coverage(_family,b['id'])
            return result
        if note.get('reading_layout',{}).get('preserve_original'):
            from original_layout import render,split_chapters
            body=split_chapters(render(_family,b['id']))
            result['profile']='lineup-v5'
            result['sections']=[{'id':f'chapter-{i+1}','title':s,'markdown':text+'\n'} for i,(s,text) in enumerate(body.items())]
            result['section_aliases']={}
            return result
        # The website and Markdown use the same section projection, including
        # editable member tables and the selected player's own conditions.
        sections=result['scope_sections']
        result['profile']='lineup-v5'
        ordered=[('common',s,t) for s,t in sections['common'].items()]+[('branch',s,t) for s,t in sections['branch'].items()]
        result['sections']=[{'id':f'chapter-{i+1}','title':('通用·' if scope=='common' else '')+title,'markdown':text+'\n'} for i,(scope,title,text) in enumerate(ordered)]
        result['section_aliases']={s:'通用·'+s for s in sections['common']}
        return result
    markdown = _render_markdown(note) if note['id']==PROFILE_ID and not is_branch else _render_generic(note)
    if is_branch:
        assessment = assessment_markdown(note['meta'].get('assessment',[]))
        heading_end = markdown.index('\n\n')+2
        markdown = markdown[:heading_end] + '## 采用条件与优势短板\n\n' + assessment + '\n\n' + markdown[heading_end:]
    headings = list(re.finditer(r'^## (.+)\n', markdown, re.M))
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        result['sections'].append({'id': f'chapter-{i+1}', 'title': match.group(1),
                                   'markdown': markdown[match.end():end].lstrip('\n')})
    aliases = result['section_aliases']
    by_id = {c.get('id'): c for c in note.get('claims', [])}
    for title, groups in GROUPS:
        for _, ids in groups:
            for cid in ids:
                if cid in by_id:
                    aliases.setdefault(by_id[cid]['section'], title)
    aliases.update({'阵容组成':'阵容概览与成员清单','运营节奏':'运营路线选择',
                    '推荐后期组合':'阵容概览与成员清单','推荐装备':'装备与站位',
                    '站位技巧':'装备与站位','克制手段':'对局威胁与应对'})
    if note['id']!=PROFILE_ID or is_branch:
        result['section_aliases']={'运营节奏':'运营路线与后期组合','推荐后期组合':'运营路线与后期组合'}
    result['profile'] = 'lineup-v5' if is_branch else PROFILE_ID if note['id']==PROFILE_ID else 'lineup-v4'
    if result['sections']:
        result['sections'][-1]['markdown']=result['sections'][-1]['markdown'].rstrip()+'\n'
    return result


def render(note):
    document = reading_document(note)
    return '# ' + note['title'] + '\n\n' + ''.join(
        '## ' + section['title'] + '\n\n' + section['markdown'] for section in document['sections'])
