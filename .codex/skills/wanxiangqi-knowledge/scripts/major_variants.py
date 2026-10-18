"""Evidence-backed strategic branches; member lists and route compatibility live elsewhere."""
import re

DIMENSIONS={'heroes':'英雄组成','mechanism':'成长／输出机制','tempo':'运营节奏','equipment':'装备','talents':'天赋','skills':'技能'}

def containers(row):
    yield row
    yield from row.get('differences',{}).values()

def validate(meta,claims=None):
    rows=meta.get('major_variants',[])
    if not isinstance(rows,list):raise ValueError('主要变阵须为列表')
    if not rows:return
    from tactics import claim_id
    known={claim_id(c) for c in claims} if claims is not None else None
    ids=set()
    def refs(values):
        if not isinstance(values,list) or any(not isinstance(x,str) or not x for x in values) or len(set(values))!=len(values):raise ValueError('主要变阵引用须为不重复ID列表')
        if known is not None and set(values)-known:raise ValueError('主要变阵引用了不存在的结论')
    for row in rows:
        required={'id','name','condition_refs','baseline_refs','claim_refs','late_variant_ids','operation_route_ids','differences'}
        if not isinstance(row,dict) or set(row)!=required:raise ValueError('主要变阵字段不完整或包含未知字段')
        if not isinstance(row['id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',row['id']) or row['id'] in ids:raise ValueError('主要变阵ID无效或重复')
        ids.add(row['id'])
        if not isinstance(row['name'],str) or not row['name'].strip():raise ValueError('主要变阵名称不能为空')
        for key in ('condition_refs','baseline_refs','claim_refs'):refs(row[key])
        for key,source in [('late_variant_ids','late_variants'),('operation_route_ids','operation_routes')]:
            values=row[key]
            if not isinstance(values,list) or any(not isinstance(v,str) for v in values) or len(set(values))!=len(values) or set(values)-{r['id'] for r in meta.get(source,[])}:raise ValueError('主要变阵引用的组合或路线已不存在，请先解除关联')
        differences=row['differences']
        if not isinstance(differences,dict) or set(differences)!=set(DIMENSIONS):raise ValueError('主要变阵须比较全部六个维度')
        for value in differences.values():
            if not isinstance(value,dict) or set(value)!={'status','claim_refs'} or value['status'] not in ('different','same','unknown'):raise ValueError('变阵比较状态无效')
            refs(value['claim_refs'])
            if value['status']!='unknown' and not value['claim_refs']:raise ValueError('差异与沿用主干均须有结论依据')

def remap(meta,old_ids,new_id):
    for row in meta.get('major_variants',[]):
        for container in containers(row):
            for key in ('condition_refs','baseline_refs','claim_refs'):
                if key in container:container[key]=list(dict.fromkeys(new_id if x in old_ids else x for x in container[key] if x not in old_ids or new_id))
            if 'status' in container and not container['claim_refs']:container['status']='unknown'

def render(meta,emit,link):
    """Call the shared claim placer; never print a reference's full text twice."""
    lines=['## 主要变阵','']
    rows=meta.get('major_variants',[])
    if not rows:return lines+['暂无已确认的主要变阵','']
    for row in rows:
        local=set()
        def take(ids):
            fresh=[cid for cid in ids if cid not in local]
            local.update(ids)
            return emit(fresh) if fresh else ['见本变阵上文。'] if ids else ['待确认']
        ready=all(row[k] for k in ('condition_refs','baseline_refs','claim_refs')) and any(v['status']=='different' for v in row['differences'].values())
        lines+=['### '+row['name']+('' if ready else '（依据待确认）'),'']
        for key,title in [('baseline_refs','比较主干'),('condition_refs','采用条件与转入限制'),('claim_refs','变阵依据')]:
            lines += [f'**{title}**','']+(take(row[key]) if key!='baseline_refs' else link(row[key]))+['']
        for key,title in DIMENSIONS.items():
            value=row['differences'][key];status={'different':'有差异','same':'沿用主干','unknown':'待确认'}[value['status']]
            lines += [f'**{title} · {status}**','']+take(value['claim_refs'])+['']
        for key,source,title in [('late_variant_ids','late_variants','关联后期组合'),('operation_route_ids','operation_routes','关联运营路线')]:
            selected=[r['name'] for r in meta.get(source,[]) if r['id'] in row[key]]
            if selected:lines += [title+'：'+'、'.join(selected),'']
        if row['late_variant_ids'] and row['operation_route_ids']:lines+=['组合与路线仅按原有已确认适配关系使用，不代表可任意搭配。','']
    return lines
