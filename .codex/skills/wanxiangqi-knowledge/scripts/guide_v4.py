"""Compact teaching layout; source blocks retain their editable ownership."""
from copy import deepcopy
import re

ALIASES = {'第一轮拍卖':'拍卖', '第二轮拍卖':'拍卖', '第三轮拍卖':'拍卖',
           '推荐装备':'关键装备', '阵容组成':'英雄', '阵容概览与成员清单':'英雄',
           '关键操作顺序':'关键操作'}


def validate_principles(note):
    """Validate supplied principles, without inventing prose for legacy notes."""
    import guide_layout as guide
    import player_branches as branches
    if note.get('reading_layout',{}).get('version')!=4:return
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
        chapters[current].append(block)
    if note['reading_layout'].get('purchase_lists_first'):
        rows=chapters.get('阵容组成与运营节奏',[])
        starts=[i for i,b in enumerate(rows) if b['text'].startswith('### ')]+[len(rows)]
        for start,end in reversed(list(zip(starts,starts[1:]))):
            body=rows[start+1:end]
            rows[start+1:end]=[b for b in body if b.get('kind')=='member']+[b for b in body if b.get('kind')!='member']
    order = (['核心原理'] if '核心原理' in chapters else []) + ['打法评价','定阵条件','核心机制','英雄','阵容组成与运营节奏','拍卖','关键装备','推荐天赋','棋手技能推荐','关键效果牌','关键操作','站位技巧','制敌手段','克制手段']
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
            out.extend(chapters.get('推荐装备' if title=='关键装备' else title, []) or [{'text':'暂无已确认的策略。'}])
    return out
