"""Player views retain the existing note's chapter hierarchy and order.

Scope ownership is kept in JSON; Markdown readers never see scope wrappers.
"""
from copy import deepcopy
from difflib import SequenceMatcher
import re


def split_chapters(text):
    result={};title=None;lines=[];fence=None
    for line in text.replace('\r\n','\n').splitlines()[1:]:
        m=re.match(r'^(`{3,}|~{3,})',line)
        if m:
            if fence is None:fence=m[1][0]
            elif fence==m[1][0]:fence=None
        if line.startswith('## ') and fence is None:
            if title is not None:result[title]='\n'.join(lines).strip()
            title=line[3:].strip();lines=[]
            if not title or title in result:raise ValueError('章节名称为空或重复')
        elif line.startswith('# '):raise ValueError('只能有一个主标题')
        else:lines.append(line)
    if fence:raise ValueError('代码块尚未闭合')
    if title is not None:result[title]='\n'.join(lines).strip()
    return result


def render(note,bid):
    import player_branches as branches
    from lineup_layout import _render_generic,_render_markdown,PROFILE_ID
    selected=branches.project(note,bid)
    text=_render_markdown(selected) if note['id']==PROFILE_ID else _render_generic(selected)
    text=text.replace('# '+note['title']+'\n','# '+note['title']+'-'+branches.player_name(note,branches.branch(note,bid))+'\n',1)
    # Evaluation and selection are content inside the existing overview chapter.
    # They do not introduce a new level of chapter hierarchy.
    sections=split_chapters(text);overview=next(iter(sections))
    rows=selected['meta'].get('assessment',[])
    b=branches.branch(note,bid);selection=b.get('selection',{})
    extra=[]
    if rows:extra+=['**打法评价**','',branches.assessment_markdown(rows),'']
    if selection:
        extra+=['**采用条件**：'+selection.get('adopt',''),'','**放弃或转向**：'+selection.get('avoid',''),'']
        for label,value in selection.get('signals',{}).items():extra+=['**'+label+'**：'+value,'']
    if extra:
        opening='## '+overview+'\n\n'
        text=text.replace(opening,opening+'\n'.join(extra)+'\n',1)
    return text


def clean(block):
    return re.sub(r'^- ', '', block.strip()).removeprefix('推测：').strip()


def claim_scope(note,bid):
    import player_branches as branches
    common=set(note['meta']['common_claim_refs']);private=set(branches.branch(note,bid)['claim_refs'])
    return {c['id']:('common' if c['id'] in common else 'branch') for c in note['claims'] if c['id'] in common|private}


def initial_sections(note,bid):
    import player_branches as branches
    b=branches.branch(note,bid)
    result={'common':branches.sections_for(note,'common'),'branch':branches.sections_for(note,bid)}
    for scope,key in [('common','共同成员与依赖'),('branch','成员与替换')]:
        actual='common' if scope=='common' else bid
        result[scope][key]=branches.configuration(note,actual)
        owner=note['meta'] if scope=='common' else b
        if owner.get('assessment'):result[scope]['打法评价']=branches.assessment_markdown(owner['assessment'])
    if b.get('selection'):result['branch']['采用与转向信号']=branches.selection_markdown(b['selection'])
    from tactical_edit import sections
    result['common'].update(sections(note,'common'));result['branch'].update(sections(note,bid))
    return result


def parse(text,note,bid):
    import player_branches as branches
    expected='# '+note['title']+'-'+branches.player_name(note,branches.branch(note,bid))
    if not text.splitlines() or text.splitlines()[0]!=expected:raise ValueError('Markdown标题与棋手文件不一致')
    base=split_chapters(render(note,bid));current=split_chapters(text)
    if list(current)!=list(base):raise ValueError('请保留原笔记的章节名称、顺序和标题层级')
    for title in base:
        if re.findall(r'^#{3,} .+$',current[title],re.M)!=re.findall(r'^#{3,} .+$',base[title],re.M):raise ValueError('请保留原笔记的子章节名称和标题层级')
    result=initial_sections(note,bid);owners=claim_scope(note,bid);claims={c['id']:c for c in note['claims'] if c['id'] in owners}
    for title,body in current.items():
        if body==base[title]:continue
        if title=='运营路线与后期组合':
            from tactical_edit import parse_changed
            parse_changed(note,bid,base[title],body,result);continue
        if title in ('阵容信息','阵容概览与成员清单'):
            parse_meta(body,base[title],note,bid,result);continue
        old_blocks=re.split(r'\n\s*\n',base[title]);new_blocks=re.split(r'\n\s*\n',body)
        def owner(block):
            value=clean(block)
            matches=[cid for cid,c in claims.items() if value and value in c['text']]
            return matches[0] if len(matches)==1 else None
        tags=[owner(block) for block in old_blocks]
        changes=[]
        for op,a0,a1,b0,b1 in SequenceMatcher(None,old_blocks,new_blocks,autojunk=False).get_opcodes():
            if op=='equal':changes += [(tags[a0+i],clean(block),True) for i,block in enumerate(new_blocks[b0:b1])];continue
            scoped={owners[cid] for cid in tags[a0:a1] if cid}
            if len(scoped)>1:raise ValueError('同一次修改跨越通用和专属段落，请分别修改')
            old_ids={cid for cid in tags[a0:a1] if cid}
            if not old_ids and any(x.strip() and not x.startswith('暂无') and not x.startswith('###') for x in old_blocks[a0:a1]):
                raise ValueError('结构化区块修改请保持成员及路线字段格式')
            scope=next(iter(scoped),'branch');cid=next(iter(old_ids)) if len(old_ids)==1 else scope+':new'
            changes += [(cid,clean(block),False) for block in new_blocks[b0:b1] if block.strip() and not block.startswith('暂无')]
        grouped=[]
        for cid,value,unchanged in changes:
            if cid is None:continue
            scope=owners.get(cid,cid.split(':')[0] if ':' in cid else 'branch')
            if grouped and grouped[-1][0]==cid:grouped[-1][2].append(value);grouped[-1][3] &= unchanged
            else:grouped.append([cid,scope,[value],unchanged])
        found_sections={claims[cid]['section'] for cid in tags if cid}
        if not found_sections:found_sections={title}
        for section in found_sections:
            for scope in ('common','branch'):
                original=[c for c in claims.values() if c['section']==section and owners[c['id']]==scope]
                paragraphs=[]
                for cid,group,parts,unchanged in grouped:
                    if group!=scope or (cid in claims and claims[cid]['section']!=section):continue
                    paragraphs.append(claims[cid]['text'] if unchanged and cid in claims else '\n\n'.join(parts))
                if original or paragraphs:result[scope][section]='\n\n'.join(paragraphs)
    return result


def parse_meta(body,baseline,note,bid,result):
    """Read the existing name lists and stage bullets, keeping scope in JSON."""
    import player_branches as branches
    projected=branches.project(note,bid);new=deepcopy(projected['meta']);names=dict(note.get('entity_names',{}))
    from tactics import references
    for ref in references(note['meta']):
        if ref.startswith('pending:'):names.setdefault(ref,ref.removeprefix('pending:'))
    def resolve(name,kind='card'):
        hits=[ref for ref,label in names.items() if label==name and (ref.startswith(kind+':') or ref.startswith('pending:'))]
        if len(hits)!=1:raise ValueError('名称未知或不唯一：'+name)
        return hits[0]
    for field,label in [('players','适用棋手'),('core_heroes','核心英雄'),('required_factions','必须阵营')]:
        match=re.search(r'^'+label+'：(.+)$',body,re.M)
        old=re.search(r'^'+label+'：(.+)$',baseline,re.M)
        if match and old and match[1]!=old[1]:
            values=[resolve(x.strip(),'faction' if field=='required_factions' else 'card') for x in match[1].split('、') if x.strip() and x.strip()!='待确认']
            if field=='players':raise ValueError('棋手归属不能通过改名删除，请在网页维护分支')
            new[field]=values
    for stage,label in [('early','前期'),('middle','中期'),('late','后期')]:
        pattern=r'^### '+label+r'英雄组成\n(.*?)(?=^### |\Z)'
        match=re.search(pattern,body,re.M|re.S);old=re.search(pattern,baseline,re.M|re.S)
        if not match or not old or match[1]==old[1]:continue
        members=[]
        for line in match[1].splitlines():
            if not line.strip():continue
            m=re.fullmatch(r'- (.+?)（(必需|可选)）：(.*)',line)
            if not m:raise ValueError('成员请保持“英雄（必需/可选）：作用”的原格式')
            role=m[3];replaces='';condition=''
            if '；替换' in role:
                role,replacement=role.split('；替换',1)
                target,_,condition=replacement.partition('；');replaces=resolve(target)
            members.append(dict(hero=resolve(m[1]),necessity='required' if m[2]=='必需' else 'optional',role=role,replaces=replaces,replacement_note=condition))
        new['compositions'][stage]=members
    # Resolve only fields actually changed; do not freeze inherited data into a
    # branch simply because the selected view displayed it.
    temp=deepcopy(note);b=branches.branch(temp,bid);changed=False
    for field in ('core_heroes','required_factions'):
        if new[field]!=projected['meta'][field]:
            (b.setdefault('overrides',{}) if field in b.get('overrides',{}) else temp['meta'])[field]=new[field];changed=True
    for stage in ('early','middle','late'):
        if new['compositions'][stage]!=projected['meta']['compositions'][stage]:
            dest=b.setdefault('overrides',{}).setdefault('compositions',{}) if stage in b.get('overrides',{}).get('compositions',{}) else temp['meta']['compositions']
            dest[stage]=new['compositions'][stage];changed=True
    # Qualitative evaluation and adoption conditions remain paragraphs within
    # the original overview, while their ownership stays explicit internally.
    row_pattern=r'^- \*\*(.+?)\*\*：(.+)$'
    old_rows=dict(re.findall(row_pattern,baseline,re.M));new_rows=dict(re.findall(row_pattern,body,re.M))
    if old_rows!=new_rows:
        common_dimensions={branches.DIMENSIONS[a['dimension']] for a in temp['meta'].get('assessment',[])}
        branch_dimensions={branches.DIMENSIONS[a['dimension']] for a in b.get('assessment',[])}
        collected={'common':[],'branch':[]}
        for label,value in new_rows.items():
            if label=='前三率／吃鸡率':continue
            group='common' if label in common_dimensions and label not in branch_dimensions else 'branch'
            collected[group].append('- **'+label+'**：'+value)
        for group in collected:
            result[group]['打法评价']='\n'.join(collected[group]);changed=True
    selection=deepcopy(b.get('selection',{}))
    for key,label in [('adopt','采用条件'),('avoid','放弃或转向')]:
        m=re.search(r'^\*\*'+label+r'\*\*：(.+)$',body,re.M)
        old=re.search(r'^\*\*'+label+r'\*\*：(.+)$',baseline,re.M)
        if m and old and m[1]!=old[1]:selection[key]=m[1];changed=True
    for label in selection.get('signals',{}):
        m=re.search(r'^\*\*'+re.escape(label)+r'\*\*：(.+)$',body,re.M)
        old=re.search(r'^\*\*'+re.escape(label)+r'\*\*：(.+)$',baseline,re.M)
        if m and old and m[1]!=old[1]:selection['signals'][label]=m[1];changed=True
    if selection!=b.get('selection',{}):result['branch']['采用与转向信号']=branches.selection_markdown(selection)
    if not changed:raise ValueError('阵容信息的修改未能解析，请保持原字段格式')
    result['common']['共同成员与依赖']=branches.configuration(temp,'common')
    result['branch']['成员与替换']=branches.configuration(temp,bid)
