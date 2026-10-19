"""Version 2 reader: semantic chapter positions, reversible unmarked Markdown."""
from copy import deepcopy
from difflib import SequenceMatcher
import re,json,hashlib
import player_branches as branches

BASE = ['打法评价','定阵条件','核心机制','阵容组成与运营节奏','第一轮拍卖','第二轮拍卖','第三轮拍卖','推荐装备','推荐天赋','棋手技能推荐','关键效果牌','站位技巧','制敌手段','克制手段']
EXTRA = ['主要变阵','关键操作顺序','终局技巧','战后复盘','操作时间不足','关键牌判断']
STAGES = {'early':'前期英雄组成与运营','middle':'中期英雄组成与运营','late':'后期英雄组成与运营'}
ALIASES = {'阵容信息':'打法评价','阵容概览与成员清单':'阵容组成与运营节奏','阵容组成':'阵容组成与运营节奏','运营路线与后期组合':'阵容组成与运营节奏','运营路线选择':'阵容组成与运营节奏','前中后期共通流程':'阵容组成与运营节奏','前期运营及应变':'阵容组成与运营节奏','中期运营及应变':'阵容组成与运营节奏','后期运营及应变':'阵容组成与运营节奏','成型后提升思路':'阵容组成与运营节奏','推荐天赋及原因':'推荐天赋','路线与装备取舍':'推荐装备','棋手决策选择':'棋手技能推荐','版本差异':'附录','尚待裁决':'附录','禁用阵营适用情况':'定阵条件','对局威胁与应对':'制敌手段','装备与站位':'推荐装备','三轮拍卖与天赋选择':'第一轮拍卖'}

def enabled(note):return note.get('reading_layout',{}).get('version')==2

def claim_hash(claim):
    return hashlib.sha256(json.dumps({k:claim.get(k) for k in ('text','condition','inference')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def claim_text(claim):
    prefix=('推测：' if claim.get('inference') else '')
    condition=claim.get('condition','')
    return prefix+('适用前提：'+condition+'。\n\n' if condition and condition not in claim['text'] else '')+claim['text']

MATCHUP_REFS={'card:1671':['anti-burst'],'card:3551':['ailin-chase'],'card:1101':['ying-equipment-dispute'],'card:5071':['mulan-vs-yaomei-lixin']}
def project_matchups(note):
    if note['id']!='heluo-huamulan':return
    by_id={c['id']:c for c in note['claims']}
    for row in note['meta'].get('matchups',[]):
        ids=MATCHUP_REFS.get(row['target'],[])
        if ids:row['text']='\n\n'.join(claim_text(by_id[x]) for x in ids if x in by_id) or '当前棋手尚缺已确认的应对策略。'

def location(note,c):
    explicit=note.get('reading_layout',{}).get('claim_locations',{}).get(c['id'])
    if explicit:return explicit
    s=c['section']
    if s.startswith('前期'):return ['阵容组成与运营节奏',STAGES['early']]
    if s.startswith('中期'):return ['阵容组成与运营节奏',STAGES['middle']]
    if s.startswith('后期'):return ['阵容组成与运营节奏',STAGES['late']]
    if s=='成型后提升思路':return ['阵容组成与运营节奏','后期提升思路']
    if s=='阵容组成':return ['阵容组成与运营节奏',STAGES['middle']]
    if s=='前期运营':return ['阵容组成与运营节奏',STAGES['early']]
    if s in ('版本差异','尚待裁决'):return ['附录','版本差异' if s=='版本差异' else '待核实事项']
    if s=='克制手段':return ['制敌手段'] # legacy field meant own counterplay
    return [ALIASES.get(s,s)]

def initial_sections(note,bid):
    from original_layout import initial_sections as legacy
    return legacy(note,bid)

def coverage(note,bid):
    selected=branches.project(note,bid);claims={c['id']:c for c in selected['claims']}
    reviewed=note.get('reading_layout',{}).get('coverage',{}).get(branches.branch(note,bid)['id'],{})
    result={}
    for stage in STAGES:
        result[stage+'.members']={'status':'covered' if selected['meta']['compositions'][stage] else 'missing','claim_refs':[]}
        for field in ('operation','awakening','budget','missing'):
            value=reviewed.get(stage+'.'+field,[]);ids=value.get('claim_refs',[]) if isinstance(value,dict) else value
            refs=[x for x in ids if x in claims]
            result[stage+'.'+field]={'status':value.get('status','covered') if isinstance(value,dict) and refs else 'covered' if refs else 'missing','claim_refs':refs,'detail':value.get('detail','') if isinstance(value,dict) else ''}
    for field in ('improvement','equipment','talents','skills','effect_cards'):
        value=reviewed.get(field,[]);refs=[x for x in (value.get('claim_refs',[]) if isinstance(value,dict) else value) if x in claims]
        result[field]={'status':'covered' if refs else 'missing','claim_refs':refs}
    for i in range(1,4):
        for field in ('heroes','effects','priority','budget'):
            value=reviewed.get(f'auction{i}.{field}',[]);refs=[x for x in (value.get('claim_refs',[]) if isinstance(value,dict) else value) if x in claims]
            result[f'auction{i}.{field}']={'status':value.get('status','covered') if isinstance(value,dict) and refs else 'covered' if refs else 'missing','claim_refs':refs,'detail':value.get('detail','') if isinstance(value,dict) else ''}
    for key,row in result.items():
        record=reviewed.get(key,{})
        hashes=record.get('claim_hashes',{}) if isinstance(record,dict) else {}
        if any(hashes.get(cid) and hashes[cid]!=claim_hash(claims[cid]) for cid in row['claim_refs']):
            row.update(status='needs_review',detail='关联内容已改写，需要重新审核覆盖范围。')
    return result

def blocks(note,bid):
    selected=branches.project(note,bid);b=branches.branch(note,bid);meta=selected['meta'];names=note.get('entity_names',{})
    name=lambda x:names.get(x,x.removeprefix('pending:'))
    out=[]
    def add(text,**kw):out.append({'text':text,**kw})
    add('# '+note['title']+'-'+branches.player_name(note,b))
    info='\n\n'.join(label+'：'+('、'.join(map(name,meta[field])) or '待确认') for field,label in [('players','适用棋手'),('core_heroes','核心英雄'),('required_factions','必须阵营')])
    add(info,kind='meta',key='opening')
    claims={};locs={}
    for c in selected['claims']:
        loc=tuple(location(note,c));claims.setdefault(loc,[]).append(c);locs[c['id']]=loc
    def emit(loc):
        for c in claims.get(tuple(loc),[]):
            routes=[r['name'] for r in meta.get('operation_routes',[]) if c['id'] in sum(r.get('phases',{}).values(),[])]
            if routes and len(meta.get('operation_routes',[]))>1:add('**适用路线：'+'、'.join(routes)+'**')
            add(claim_text(c),kind='claim',claim=c['id'])
    def head(title,level=2):add('#'*level+' '+title)
    def empty():add('暂无已确认的策略。')
    def render_routes():
        for r in meta.get('operation_routes',[]):
            head(r['name']+'：适用与转向',4)
            body='\n\n'.join(label+'：'+r.get(k,'') for k,label in [('condition','适用条件'),('advantages','优势'),('risks','风险'),('transition','转向条件')])
            add(body,kind='tactical',key='运营路线：'+r['name'],row=r['id'],field='operation_route_ids')
    known={location(note,c)[0] for c in note['claims']}
    chapters=[*BASE,*[x for x in EXTRA if x in known or (x=='主要变阵' and meta.get('major_variants'))],*[x for x in known if x not in BASE+EXTRA+['附录','关联知识']], '附录','关联知识']
    for title in dict.fromkeys(chapters):
        head(title);start=len(out)
        if title=='打法评价':add(branches.assessment_markdown(meta.get('assessment',[])),kind='meta',key='assessment')
        elif title=='定阵条件':
            selection=b.get('selection',{})
            if selection:
                add('\n\n'.join(['**采用条件**：'+selection.get('adopt',''),'**放弃或转向**：'+selection.get('avoid',''),*['**'+k+'**：'+v for k,v in selection.get('signals',{}).items()]]),kind='meta',key='selection')
            for row in meta.get('ban_conditions',[]):add(name(row['faction'])+'被禁：'+{'playable':'可玩','unplayable':'不可玩','unknown':'待确认'}[row['status']]+'。'+row.get('reason',''),kind='ban',faction=row['faction'])
        elif title=='阵容组成与运营节奏':
            for stage,label in STAGES.items():
                head(label,3)
                members=meta['compositions'][stage]
                if members:
                    add('\n\n'.join('- '+name(m['hero'])+('（必需）' if m['necessity']=='required' else '（可选）')+'：'+m.get('role','')+('；替换'+name(m['replaces']) if m.get('replaces') else '')+('；'+m['replacement_note'] if m.get('replacement_note') else '') for m in members),kind='meta',key='members',stage=stage)
                else:add('阶段成员尚缺已核实的完整清单。')
                if stage=='early':render_routes()
                if stage=='late':
                    from tactical_edit import sections as tactical_sections
                    for v in meta.get('late_variants',[]):
                        head('后期组合：'+v['name'],4)
                        key='后期组合：'+v['name'];body=next((tactical_sections(note,s)[key] for s in ('common',bid) if key in tactical_sections(note,s)),None)
                        if body:add(body,kind='tactical',key=key,row=v['id'],field='late_variant_ids')
                emit([title,label])
                missing=[k.rsplit('.',1)[1] for k,v in coverage(note,bid).items() if k.startswith(stage+'.') and v['status']=='missing']
                labels={'operation':'具体运营','awakening':'逐成员觉醒要求','budget':'找牌投入边界','missing':'缺牌应变'}
                missing=[labels[x] for x in missing if x in labels]
                if missing:add('待补充：'+'、'.join(missing)+'尚缺可靠说明。')
                for r in meta.get('operation_routes',[]):
                    refs=[x for x in r['phases'].get(stage,[]) if x in locs]
                    # Route names are attached to the actual paragraphs, never links.
                    for item in out:
                        if item.get('claim') in refs and not item.get('route_names'):item['route_names']=[r['name']]
            head('后期提升思路',3);emit([title,'后期提升思路'])
            if not claims.get((title,'后期提升思路')):add('后期提升的完整优先级尚缺已核实说明。')
        elif title=='主要变阵':
            for variant in meta.get('major_variants',[]):
                head(variant['name'],3)
                for key in ('condition','summary'):
                    if variant.get(key):add(variant[key])
                for dim,value in variant.get('differences',{}).items():
                    if value.get('summary'):add(value['summary'])
        elif title=='附录':
            for sub in ('版本差异','待核实事项'):
                head(sub,3);emit([title,sub])
                if not claims.get((title,sub)):add('暂无已确认的'+sub+'。')
        elif title=='关联知识':
            for link in selected.get('guide_related',[]):add('- ['+link['title']+']('+link['href']+')')
        emit([title])
        if len(out)==start:empty()
    return out

def render(note,bid):return '\n\n'.join(b['text'] for b in blocks(note,bid))+'\n'

def parse(text,note,bid):
    """Map edits back to known source blocks; never guess a cross-scope edit."""
    source=blocks(note,bid);base=render(note,bid);text=text.replace('\r\n','\n').rstrip()+'\n'
    if re.findall(r'^#{1,6} .+$',base,re.M)!=re.findall(r'^#{1,6} .+$',text,re.M):raise ValueError('请保留当前章节名称、顺序和标题层级')
    result=initial_sections(note,bid)
    if text==base:return result
    spans=[];cursor=0
    for block in source:
        spans.append((cursor,cursor+len(block['text']),block));cursor+=len(block['text'])+2
    edits={}
    for op,a0,a1,b0,b1 in SequenceMatcher(None,base,text,autojunk=False).get_opcodes():
        if op=='equal':continue
        hits=[(i,start,end,b) for i,(start,end,b) in enumerate(spans) if start<=a0 and a1<=end and b.get('kind')]
        if len(hits)!=1:raise ValueError('修改跨越独立段落或只读生成信息，请分段修改；新增策略请用网页编辑')
        i,start,end,b=hits[0];edits.setdefault(i,[]).append((a0-start,a1-start,text[b0:b1]))
    updated={}
    for i,changes in edits.items():
        body=source[i]['text']
        for a,z,value in sorted(changes,reverse=True):body=body[:a]+value+body[z:]
        updated[i]=body
    claim_text={c['id']:c['text'] for c in note['claims']};changed_sections=set()
    meta_base=[];meta_new=[]
    for i,body in updated.items():
        block=source[i]
        if block['kind']=='claim':claim_text[block['claim']]=body;changed_sections.add(next(c['section'] for c in note['claims'] if c['id']==block['claim']))
        elif block['kind']=='meta':pass
        elif block['kind']=='tactical':
            scope='common' if all(block['row'] in b.get(block['field'],[]) for b in note['meta']['player_branches']) else 'branch'
            result[scope][block['key']]=body
        elif block['kind']=='ban':raise ValueError('请通过网页成员配置编辑禁用条件')
    for i,block in enumerate(source):
        if block.get('kind')!='meta':continue
        prefix='### '+{'early':'前期','middle':'中期','late':'后期'}.get(block.get('stage'),'')+'英雄组成\n' if block.get('key')=='members' else ''
        meta_base.append(prefix+block['text']);meta_new.append(prefix+updated.get(i,block['text']))
    if meta_base!=meta_new:
        from original_layout import parse_meta
        parse_meta('\n\n'.join(meta_new),'\n\n'.join(meta_base),note,bid,result)
    common=set(note['meta']['common_claim_refs']);private=set(branches.branch(note,bid)['claim_refs'])
    for section in changed_sections:
        for group,ids in [('common',common),('branch',private)]:
            result[group][section]='\n\n'.join(claim_text[c['id']] for c in note['claims'] if c['section']==section and c['id'] in ids)
    return result
