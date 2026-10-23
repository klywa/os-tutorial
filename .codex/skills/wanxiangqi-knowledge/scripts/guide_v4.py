"""Compact teaching layout; source blocks retain their editable ownership."""
from copy import deepcopy
import re

ALIASES = {'第一轮拍卖':'拍卖', '第二轮拍卖':'拍卖', '第三轮拍卖':'拍卖',
           '推荐装备':'关键装备', '阵容组成':'英雄', '阵容概览与成员清单':'英雄',
           '关键操作顺序':'关键操作', '棋手技能推荐':'棋手技能选择'}

HERO_FIELDS = ('觉醒需求', '等级投入', '购买策略', '上阵时机', '出售时机')


def hero_field_errors(text):
    """Validate shape only: missing evidence remains an editorial audit result."""
    plain=re.sub(r'\*\*|`','',text)
    errors=[]
    matches=list(re.finditer('|'.join(re.escape(f)+'：' for f in HERO_FIELDS),plain))
    if [m.group()[:-1] for m in matches]!=list(HERO_FIELDS):
        errors.append('英雄五字段必须按序各出现一次')
    if '\n' in text or '\r' in text:errors.append('英雄五字段必须保持一个自然段')
    if matches:
        role=plain[:matches[0].start()].partition('：')[2].strip()
        if not role:errors.append('英雄五字段前必须说明定位及战力作用')
    for i,m in enumerate(matches):
        value=plain[m.end():matches[i+1].start() if i+1<len(matches) else len(plain)].strip()
        if not value.endswith('；') or not value[:-1].strip():
            errors.append(m.group()[:-1]+'必须有内容并以全角分号收尾')
    return errors


def paragraph_errors(note, bid):
    """Check explicitly reviewed prose; never rewrite or infer an entity."""
    layout=note.get('reading_layout',{})
    if not (layout.get('entity_paragraphs') or layout.get('hero_fields_required')):return []
    entity_chapters={'英雄','关键装备','推荐天赋','棋手技能选择','关键效果牌'}
    stage_prefixes={'前期英雄组成与运营':'【前期运营思路：】','中期英雄组成与运营':'【中期运营思路：】','后期英雄组成与运营':'【后期运营思路：】','后期提升思路':'【后期提升思路：】'}
    names=set(note.get('entity_names',{}).values())
    errors=[];chapter=None;stage=None;stage_rows={};entity_seen={};talent_intro=False
    for b in blocks(note,bid):
        text=b['text'].strip()
        if text.startswith('## '):chapter=text[3:];stage=None;continue
        if text.startswith('### '):stage=text[4:];continue
        if chapter=='英雄' and layout.get('hero_fields_required'):
            if text.startswith('暂无已确认'):errors.append('英雄五字段尚未完成来源复核')
            else:errors.extend(hero_field_errors(text))
        if not layout.get('entity_paragraphs') and chapter!='英雄':continue
        if chapter in entity_chapters:
            if text.startswith('暂无已确认'):continue
            plain=re.sub(r'\*\*|`','',text)
            plain=re.sub(r'^[-*] +','',plain)
            name,sep,_=plain.partition('：')
            if chapter=='推荐天赋' and not sep and not entity_seen.get(chapter) and not talent_intro:
                if '\n' in text:errors.append(chapter+'总述必须为一个自然段')
                talent_intro=True;continue
            if '\n' in text or not sep or name not in names:
                errors.append(chapter+'必须逐实体单段并以实体名和全角冒号开头：'+text[:65])
            elif any(other!=name and other+'：' in plain.partition('：')[2] for other in names):
                errors.append(chapter+'一个段落不得合并多个实体讲解：'+text[:65])
            elif name in entity_seen.get(chapter,set()):
                errors.append(chapter+'同一实体重复分段：'+name)
            if not isinstance(entity_seen.get(chapter),set):entity_seen[chapter]=set()
            entity_seen[chapter].add(name)
        if chapter=='阵容组成与运营节奏' and stage in stage_prefixes and b.get('kind')!='member' and not text.startswith('- '):
            stage_rows.setdefault(stage,[]).append(text)
    for stage,prefix in (stage_prefixes.items() if layout.get('entity_paragraphs') else []):
        rows=stage_rows.get(stage,[])
        if len(rows)!=1 or not rows[0].startswith(prefix) or '\n' in rows[0]:
            errors.append(stage+'必须恰好一个无换行自然段并以'+prefix+'开头')
    return errors


def validate_principles(note):
    """Validate supplied principles, without inventing prose for legacy notes."""
    import guide_layout as guide
    import player_branches as branches
    if note.get('reading_layout',{}).get('version')!=4:return
    for b in note['meta']['player_branches']:
        errors=paragraph_errors(note,b['id'])
        if errors:raise ValueError('；'.join(errors))
    if not note.get('reading_layout',{}).get('requires_principle') and not any(guide.location(note,c)==['核心原理'] for c in note.get('claims',[])):return
    for b in note['meta']['player_branches']:
        rows=[c for c in branches.project(note,b['id'])['claims'] if guide.location(note,c)==['核心原理']]
        if len(rows)!=1:raise ValueError('每个棋手分支的核心原理必须恰好一段')
        text=guide.claim_text(rows[0],4).strip()
        if not text or re.search(r'\n\s*\n|^\s*(?:#{1,6}\s|[-*]\s|\d+\.\s)',text,re.M):
            raise ValueError('核心原理必须为单段正文')
        if len(re.sub(r'[*_`\s]','',text))>500:raise ValueError('核心原理不得超过500字')


def blocks(note, bid):
    import guide_layout as guide
    import player_branches as branches
    selected = branches.project(note, bid)
    available = {c['id'] for c in selected['claims']}
    operation_refs=note['reading_layout'].get('compact_operation_refs',{}).get(branches.branch(note,bid)['id'],[])
    compact=bool(operation_refs) and set(operation_refs)<=available
    supporting = note['reading_layout'].get('supporting_claim_refs', {})
    hidden = {cid for cid, summary in supporting.items() if available.intersection([summary] if isinstance(summary,str) else summary)}
    legacy = deepcopy(note)
    legacy['reading_layout']['version'] = 3
    legacy['claims'] = [c for c in legacy['claims'] if c['id'] not in hidden]
    old = guide.blocks(legacy, bid)
    claims = {c['id']:c for c in selected['claims']}
    opening, chapters = [], {}
    current = None
    skip_route = False
    for block in old:
        text = block['text']
        if text.startswith('## '):
            current = text[3:]
            if current == '关键操作顺序':current = '关键操作'
            if current == '棋手技能推荐':current = '棋手技能选择'
            chapters.setdefault(current, [])
            skip_route = False
            continue
        if current is None:
            opening.append(block); continue
        if compact and re.match(r'^#### .*：适用与转向$', text):
            skip_route = True; continue
        if skip_route and block.get('kind') in ('route_v3','tactical'):
            skip_route = False; continue
        if text.startswith('待补充：') or (compact and block.get('kind') == 'variant_condition'):continue
        if text=='阶段成员尚缺已核实的完整清单。':
            block={**block,'text':'- 暂无已确认的完整购买清单，按下述条件处理实际来牌。'}
        if block.get('claim'):
            block = {**block, 'text':guide.claim_text(claims[block['claim']],4)}
        if note['reading_layout'].get('entity_paragraphs') and current=='阵容组成与运营节奏' and text.startswith('**适用路线：'):
            continue
        if note['reading_layout'].get('entity_paragraphs') and current=='阵容组成与运营节奏' and '组合调整为' in text and '\n\n- ' in text:
            chapters.setdefault('后期组合',[]).append(block)
            continue
        chapters[current].append(block)
    if note['reading_layout'].get('purchase_lists_first'):
        rows=chapters.get('阵容组成与运营节奏',[])
        starts=[i for i,b in enumerate(rows) if b['text'].startswith('### ')]+[len(rows)]
        for start,end in reversed(list(zip(starts,starts[1:]))):
            body=rows[start+1:end]
            rows[start+1:end]=[b for b in body if b.get('kind')=='member']+[b for b in body if b.get('kind')!='member']
    order = (['核心原理'] if '核心原理' in chapters else []) + ['打法评价','定阵条件','核心机制','英雄','阵容组成与运营节奏','拍卖','关键装备','推荐天赋','棋手技能选择','关键效果牌','关键操作','站位技巧','制敌手段','克制手段']
    extras = [x for x in chapters if x not in order+['第一轮拍卖','第二轮拍卖','第三轮拍卖','推荐装备','附录','关联知识']]
    out = opening
    for title in [*order,*extras,'附录','关联知识']:
        out.append({'text':'## '+title})
        if title == '拍卖':
            for i, old_title in enumerate(('第一轮拍卖','第二轮拍卖','第三轮拍卖')):
                out.append({'text':'### '+old_title})
                rows = chapters.get(old_title, [])
                if i<2 and not any(r.get('claim') for r in rows):rows=[{'text':'优先拿阵容英雄。'}]
                out.extend(rows or [{'text':'暂无已确认的策略。'}])
        else:
            rows=chapters.get(title,[])+(chapters.get('推荐装备',[]) if title=='关键装备' else [])
            if any(row.get('claim') for row in rows):
                rows=[row for row in rows if not (row['text'].startswith('暂无已确认') and not row.get('claim'))]
            out.extend(rows or [{'text':'暂无已确认的策略。'}])
    return out
