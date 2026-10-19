"""Reversible edits of route/combination fields without visible machine IDs."""
from copy import deepcopy
from difflib import SequenceMatcher
import re,uuid

FIELDS={'运营路线':('operation_routes','operation_route_ids'),'后期组合':('late_variants','late_variant_ids')}

def sections(note,scope):
    import player_branches as branches
    result={};b=None if scope=='common' else branches.branch(note,scope)
    names=note.get('entity_names',{})
    for label,(field,key) in FIELDS.items():
        for row in note['meta'].get(field,[]):
            owners=[x for x in note['meta']['player_branches'] if row['id'] in x.get(key,[])]
            if b is None and len(owners)!=len(note['meta']['player_branches']):continue
            if b is not None and row['id'] not in b.get(key,[]):continue
            if b is not None and len(owners)==len(note['meta']['player_branches']):continue
            lines=['适用条件：'+row.get('condition','')]
            if label=='运营路线':
                lines += [title+'：'+row.get(k,'') for k,title in [('advantages','优势'),('risks','风险'),('transition','转向条件')]]
            else:
                lines += ['组合核心：'+'、'.join(names.get(x,x) for x in row['core_heroes'])]
                for m in row['members']:
                    lines+=['- '+names.get(m['hero'],m['hero'])+('（必需）' if m['necessity']=='required' else '（可选）')+'：'+m.get('role','')+('；替换 '+names.get(m['replaces'],m['replaces']) if m.get('replaces') else '')+('；'+m['replacement_note'] if m.get('replacement_note') else '')]
                lines+=['必须阵营：'+'、'.join(names.get(x,x) for x in row['required_factions'])]
            result[label+'：'+row['name']]='\n\n'.join(lines)
    return result

def apply(note,scope,section,text):
    import player_branches as branches
    label,_,name=section.partition('：')
    if label not in FIELDS:return False
    field,key=FIELDS[label];b=None if scope=='common' else branches.branch(note,scope)
    row=next((r for r in note['meta'].get(field,[]) if r['name']==name and (b is None or r['id'] in b.get(key,[]))),None)
    if row is None:raise ValueError('未知运营路线或后期组合')
    updated=deepcopy(row);names=note.get('entity_names',{})
    def ref(name,kind):
        hits=[r for r,v in names.items() if v==name.strip() and r.startswith(kind+':')]
        if len(hits)!=1:raise ValueError('名称未知或不唯一：'+name)
        return hits[0]
    for k,title in [('condition','适用条件'),('advantages','优势'),('risks','风险'),('transition','转向条件')]:
        m=re.search(r'^'+title+'：(.*)$',text,re.M)
        if m:updated[k]=m[1]
    if label=='后期组合':
        for k,title,kind in [('core_heroes','组合核心','card'),('required_factions','必须阵营','faction')]:
            m=re.search(r'^'+title+'：(.*)$',text,re.M)
            if m:updated[k]=[ref(x,kind) for x in m[1].split('、') if x.strip() and x.strip()!='待确认']
        members=[]
        for name,requirement,role in re.findall(r'^- (.+?)（(必需|可选)）：(.*)$',text,re.M):
            replaces='';replacement_note=''
            if '；替换 ' in role:
                role,replacement=role.split('；替换 ',1);replaced,_,replacement_note=replacement.partition('；');replaces=ref(replaced,'card')
            members.append(dict(hero=ref(name,'card'),necessity='required' if requirement=='必需' else 'optional',role=role,replaces=replaces,replacement_note=replacement_note))
        if members:updated['members']=members
    if updated==row:return True
    if b is not None and any(x is not b and row['id'] in x.get(key,[]) for x in note['meta']['player_branches']):
        old=row['id'];updated['id']=row['id']+'-'+uuid.uuid4().hex[:8]
        b[key]=[updated['id'] if x==old else x for x in b[key]]
        note['meta'][field].append(updated)
        if field=='late_variants':
            for route in note['meta'].get('operation_routes',[]):
                if route['id'] in b.get('operation_route_ids',[]):route['variant_ids']=[updated['id'] if x==old else x for x in route['variant_ids']]
    else:row.clear();row.update(updated);updated=row
    updated['origin']='manual';updated['claim_refs']=[]
    note.setdefault('manual_scopes',{}).setdefault(scope,[]).append(section)
    return True

def parse_changed(note,bid,old,new,result):
    """Consume only changed editable fields, never ignore edited references."""
    import player_branches as branches
    def blocks(text):
        heads=list(re.finditer(r'^#### (.+)$',text,re.M));return {h[1]:text[h.end():heads[i+1].start() if i+1<len(heads) else len(text)].strip() for i,h in enumerate(heads)}
    old_blocks=blocks(old);new_blocks=blocks(new);b=branches.branch(note,bid)
    for name,body in new_blocks.items():
        if body==old_blocks.get(name):continue
        for op,a0,a1,b0,b1 in SequenceMatcher(None,old_blocks.get(name,'').splitlines(),body.splitlines(),autojunk=False).get_opcodes():
            if op=='equal':continue
            for line in old_blocks.get(name,'').splitlines()[a0:a1]+body.splitlines()[b0:b1]:
                if line.strip() and not re.match(r'^(适用条件|优势|风险|转向条件|组合核心|必须阵营)：|^- .+（(?:必需|可选)）：',line):raise ValueError('请在对应运营章节修改操作正文，保留这里的章节引用')
        matched=False
        for label,(field,key) in FIELDS.items():
            row=next((r for r in note['meta'].get(field,[]) if r['name']==name and r['id'] in b.get(key,[])),None)
            if row:
                group='common' if all(row['id'] in x.get(key,[]) for x in note['meta']['player_branches']) else 'branch'
                result[group][label+'：'+name]=body;matched=True
        if not matched:raise ValueError('无法识别修改的运营路线或后期组合')
