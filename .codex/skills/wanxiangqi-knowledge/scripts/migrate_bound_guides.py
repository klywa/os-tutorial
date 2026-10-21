"""Reviewed schema5 expression migration; reuses existing evidence and archives edits."""
from copy import deepcopy
from pathlib import Path
import re
import guide_layout as guide,player_branches as branches
from tactics import remap_claims

SOURCE='BV1p7Yv6WEt2:p1'
TARGETS={'heluo-huamulan','yaomei-sacrifice-lixin','zhaojun-high-tier-dahe','angela-liubang-totems'}

def claim(note,cid):return next(c for c in note['claims'] if c['id']==cid)

def add_derived(note,parent,cid,text,location=None,owners=None,evidence=None):
    source=claim(note,parent);c=deepcopy(source)
    c.update(id=cid,text=text,condition='',derived_from=[parent])
    if evidence is not None:c['evidence']=evidence
    note['claims'].append(c)
    note['reading_layout']['claim_locations'][cid]=location or ['关键效果牌']
    if owners is None:
        if parent in note['meta']['common_claim_refs']:note['meta']['common_claim_refs'].append(cid)
        else:
            for b in note['meta']['player_branches']:
                if parent in b['claim_refs']:b['claim_refs'].append(cid)
    else:
        for b in note['meta']['player_branches']:
            if b['id'] in owners:b['claim_refs'].append(cid)
    return c

def effects(note,parent,rows):
    # One evidence-backed card per claim; keep the existing ID on the first.
    for i,(name,text) in enumerate(rows):
        body='- **'+name+'：**'+text
        if i==0:
            c=claim(note,parent);c.update(text=body,condition='')
            note['reading_layout']['claim_locations'][parent]=['关键效果牌']
        else:add_derived(note,parent,parent+'-card-'+str(i+1),body)

def retire_duplicate(note,cid,canonical):
    old=deepcopy(claim(note,cid));note['claims']=[c for c in note['claims'] if c['id']!=cid]
    remap_claims(note['meta'],{cid},canonical)
    for rows in note['reading_layout'].get('coverage',{}).values():
        for row in rows.values():
            if isinstance(row,dict):row['claim_refs']=list(dict.fromkeys(canonical if x==cid else x for x in row.get('claim_refs',[])))
    note['reading_layout']['claim_locations'].pop(cid,None)
    return old

def clean_context(note):
    for c in note['claims']:
        owners=[b for b in note['meta']['player_branches'] if c['id'] in b['claim_refs']]
        if len(owners)==1 and c['id'] not in note['meta']['common_claim_refs']:
            player=branches.player_name(note,owners[0])
            if player in ('明先生','庄小鱼','闹闹','昭君','嬴律'):
                c['condition']=c.get('condition','').replace(player+'，','').replace(player,'').strip('，、 ')
                c['text']=re.sub(r'^'+re.escape(player)+r'(?:路线)?','',c['text']).lstrip('，、 ')
                c['text']=c['text'].replace(player+'路线','本路线').replace(player+'材料中的','').replace(player+'教学在','在')
        if c.get('condition') in ('路线','参考运营路线'):c['condition']=''
        condition=c.get('condition','').rstrip('。')
        if condition and c['text'].startswith(condition):
            c['text']=c['text'][len(condition):].lstrip('，、： ')
            if c['text'].startswith('时，'):c['text']=c['text'][2:]
        elif condition and condition in c['text']:
            # A later conditional sentence must not become the premise of an
            # earlier, unconditional instruction in the same retained claim.
            c['condition']=''
    for r in note['meta'].get('operation_routes',[]):
        r['name']=re.sub(r'^(明先生|庄小鱼|闹闹|昭君|嬴律)：','',r['name'])
        r['condition']=re.sub(r'^使用(?:明先生|庄小鱼|闹闹|昭君|嬴律)[，且]*','',r['condition'])
    for a in note['meta'].get('assessment',[]):a['text']=a['text'].replace('本棋手技能','技能')
    for b in note['meta']['player_branches']:
        for a in b.get('assessment',[]):a['text']=a['text'].replace('本棋手技能','技能')

def heluo(note):
    retired=retire_duplicate(note,'guide-effect-wake','wake-targets')
    c=claim(note,'ming-economy')
    c.update(condition='',text='开局以弈星过渡，优先使用卦象·节积累棋手升级资源；第一轮拍卖结束后再用一次卦象·节，第二次收益结算后争取将棋手升至五阶。到棋手五阶、需要集中寻找花木兰和上官婉儿时转用卦象·丰。能否按此节奏棋手升级仍受额外买牌开销影响；找牌不顺且掉血压力增大时，先补能承接装备的李信或李白保血。')
    c['evidence'].append({'source':SOURCE,'start':658.35,'end':710.13,'frame':'frames/700-0.jpg'})
    add_derived(note,'ming-economy','ming-opening-yixing','开局可以只上弈星，把资源优先用于棋手升级；对手质量低、补牛魔有机会取胜并触发产币时，可补牛魔兼顾经济与保血。对手已经补足战力、没有取胜机会时，不为追牛魔收益挤占棋手升级预算；进入找核心阶段后，不能继续单挂弈星承担持续掉血。',['阵容组成与运营节奏',guide.STAGES['early']],['ming'],[{'source':SOURCE,'start':658.35,'end':710.13,'frame':'frames/700-0.jpg'}])
    add_derived(note,'ming-economy','ming-first-auction','第一轮拍卖出现程咬金时，按棋手升级预算考虑拿一张补后续整备产币，不为前期堆重复程咬金耽误棋手升级。没有程咬金时，可以考虑盾山暂时代替产币位置；将棋手升至五阶后取得程咬金再调整。拍卖和升级途中商店的体系牌都要与棋手升级预算比较，现有证据没有统一出价上限；程咬金、盾山都没出现时，其他竞拍替代尚缺可靠说明。',['第一轮拍卖'],['ming'],[{'source':SOURCE,'start':710.81,'end':737.91,'frame':'frames/730-0.jpg'},{'source':SOURCE,'start':1580.3,'end':1626.69,'frame':'frames/1605-0.jpg'}])
    b=branches.branch(note,'ming')
    b['overrides']['compositions']['early']=[
        {'hero':'card:1971','necessity':'required','role':'尽快将棋手升至五阶开局可单挂；把主要资源用于棋手升级','replaces':'','replacement_note':''},
        {'hero':'card:1681','necessity':'optional','role':'对手质量低、补入后有机会取胜产币时使用','replaces':'','replacement_note':''}]
    # The prior record promoted a final-round tool to every late-game board.
    v=note['meta']['late_variants'][0];v['name']='古币复生基础组合';v['condition']='古币组件齐备，并预留露娜打出位置'
    for m in v['members']:
        if m['hero']=='card:1751':m.update(necessity='optional',role='决赛需要牺牲降级时补入；检查花木兰位于覆盖内，按成长工具缺口腾位置')
    note['meta']['compositions']['late']=deepcopy(v['members'])
    for b in note['meta']['player_branches']:
        if 'late' in b.get('overrides',{}).get('compositions',{}):b['overrides']['compositions']['late']=deepcopy(v['members'])
        for p in b.get('overrides',{}).get('overview',{}).get('presets',[]):
            if p['variant_id']==v['id']:p['name']=v['name']
    # Retain all choices, but remove redundant source/player narration.
    replacements={
        'red-demon-underworld-choice':('按敌方伤害类型补第三件装备','在凝渊和所需解控之外'),
        'ming-second-auction-stock':('第二轮按核心和露娜库存选择','第二轮'),
        'ming-survival-talents':('棋手升级找核心期间场上战力不足','尚未找到花木兰'),
    }
    for cid,(condition,_) in replacements.items():claim(note,cid)['condition']=condition
    c=claim(note,'red-demon-underworld-choice');c['text']=c['text'].replace('教学在','在')
    claim(note,'ming-second-auction-stock')['condition']=''
    c=claim(note,'mingshiyin-optional');c.update(condition='有额外功能位置，且花木兰已能获得临时等级',text='可让明世隐连线花木兰，将最近英雄的一部分临时等级转为永久等级；其登场还能增加可转化额度。先确认最近目标是花木兰，不能挤掉露娜打出位置。')
    c=claim(note,'luna-awakening-context');c.update(condition='场上只有程咬金和上官婉儿两名整备英雄',text='普通露娜随机触发两名整备英雄，已能覆盖两者，露娜觉醒不是循环启动前提。凑齐合成后觉醒牌回手再打出、或腾空公共牌库，是另一个资源决策；是否合成、重打、卖回仍看手牌和下一轮需要。')
    c=claim(note,'ming-first-auction');c['text']=c['text'].replace('没有程咬金时，可以考虑盾山暂时代替产币位置；','明世隐有助于后续固定临时等级，升级途中顺路出现时可以留重复牌，但仍须保留棋手升级预算。没有程咬金时，可以考虑盾山暂时代替产币位置；')
    c=claim(note,'zhuang-high-talent');c.update(text='- **高级人才：**可补高阶体系英雄。尽快将棋手升至五阶过程中取得时，可优先留到棋手四阶使用，争取随机获得花木兰、露娜或武则天；不保证命中目标，拿取价格边界尚缺依据。',condition='')
    note['reading_layout']['claim_locations']['ying-contract-bottle']=['推荐天赋']
    effects(note,'wake-targets',[
        ('唤醒','通过已上场的露娜再次触发整备，增加本轮古币与复生次数。需要为强敌准备资源时保留，投入本轮战力时指定露娜；先确认露娜在场和产币成员就位，拿取价格上限尚缺依据。'),
        ('临阵磨枪','直接触发上官婉儿整备，补本轮古币与复生。准备投入资源或暂时没有露娜打出位置时，可指定上官婉儿使用；先确认河洛产币成员就位，拿取价格上限尚缺依据。')])
    effects(note,'hold-coin-effect',[('古币多多','补充古币资源。已有但暂时不需要投入本轮战力时，可先保留效果牌；使用后生成的转瞬古币须本回合处理，不能为了留资源让古币过期。具体购买时机和价格边界尚缺依据。')])
    effects(note,'enter-before-prep',[
        ('集体唤醒','再次触发全体登场，可让武则天产币并由露娜触发整备。能稳住时提前保留，集中投入复生的回合先上露娜再使用；拿取价格边界尚缺依据。'),
        ('全军动员','触发整备英雄的整备效果，补充古币与复生资源。能稳住时保留给强敌，产币成员就位后使用；与集体唤醒配合时先触发登场，再触发整备，拿取价格边界尚缺依据。')])
    c=claim(note,'shared-core');c['text']='以花木兰、上官婉儿、李白、武则天和程咬金构成产币、成长与输出骨架，给露娜留出登场触发整备的位置，不要永久塞满人口。成长阶段可用盾山补古币。'
    add_derived(note,'shared-core','shared-late-tools','决赛需要压低对手等级时，可把成长阶段的盾山换成钟馗，调整后确认花木兰在其覆盖内；有额外人口且不会挤掉河洛产币成员或露娜打出位置时，再考虑太乙真人补复生。',['阵容组成与运营节奏',guide.STAGES['late']])
    return [retired]

def other_effects(note):
    if note['id']=='yaomei-sacrifice-lixin':
        effects(note,'guide-effects-level',[
            ('简易协作','可补李信等级，接近100级时少量等级也可能补出自身复生。需要补等级时比较确定收益与剩余金币，再决定购买和使用；具体出价边界尚缺依据。'),
            ('精密协作','可补李信等级，接近100级时比较是否能补出自身复生。需要补等级时，先确认等级作用对象和收益，再与剩余金币比较；具体出价边界尚缺依据。'),
            ('八方来援','按实际阵营数量提供等级收益。需要补李信等级时先核对当前阵营数量，再判断是否值得买入；随机增加等级不保证命中李信，具体出价边界尚缺依据。'),
            ('武装之力','收益取决于实际装备数量。需要补李信等级时先检查装备数量与等级作用对象，再比较购买成本；不把随机等级当作必定给李信，具体出价边界尚缺依据。')])
        effects(note,'guide-effects-wake',[('唤醒','让已上场的武则天或蒙犽再次触发登场，补精致古币、登场特训和锦囊。领先且不急需战力时可保留、批量兑现；大幅掉血时及时使用，先腾打出位置并在操作后补回牺牲成员。具体拿取价格尚缺依据。')])
        v=note['meta']['late_variants'][0]
        for m in v['members']:
            if m['hero']=='card:5011':m.update(necessity='optional',role='已有较高固定量且能继续成长时，连线李信固定临时等级；固定量不足时不必占位')
        note['meta']['compositions']['late']=deepcopy(v['members'])
        for b in note['meta']['player_branches']:
            if 'late' in b.get('overrides',{}).get('compositions',{}):b['overrides']['compositions']['late']=deepcopy(v['members'])
    elif note['id']=='zhaojun-high-tier-dahe':
        c=claim(note,'claim-4c5fb188552a343f023e');c['text']=c['text'].replace('选择昭君作为棋手，','')
        effects(note,'guide-effect-transfer',[
            ('传承','用于转移张良积累的永久等级。准备替换张良时保留并使用，再按来牌补后续输出或太乙真人；使用太乙真人时确认附身东皇太一。具体拿取时机与价格边界尚缺依据。'),
            ('遗志','用于转移张良积累的永久等级。准备换下张良时先完成等级转移，再补入后续英雄；若补太乙真人，确认附身东皇太一。具体拿取时机与价格边界尚缺依据。'),
            ('众星拱月','可集中等级强化重要英雄。按对手选择目标，图腾容易被快速清除时比较东皇太一或司空震，不固定交给敖隐；具体购买优先级与价格边界尚缺依据。')])
    elif note['id']=='angela-liubang-totems':
        effects(note,'guide-effect-growth',[
            ('唤醒','让明世隐再次触发登场，将飞行器提供的临时等级转为永久等级。明世隐和唤醒来得多时采用这条成长路线，来得少或晚时可用云中君替代；具体购买优先级与价格边界尚缺依据。'),
            ('夺取之术','后期可把工具英雄的等级集中给刘邦。准备集中终局输出时再比较是否使用，先确认仍需保留的成长位置；具体拿取时机与价格边界尚缺依据。')])

def migrate(items,entities):
    import wxq
    from migrate_guide_reading import populate_coverage
    items=deepcopy(items);audit={}
    for note in items:
        if note['id'] not in TARGETS or note.get('reading_layout',{}).get('version') in (3,4):continue
        before=deepcopy(note);retired=[]
        note['reading_layout']['version']=3
        clean_context(note)
        if note['id']=='heluo-huamulan':retired=heluo(note)
        else:other_effects(note)
        for b in note['meta']['player_branches']:
            populate_coverage(note,b)
            selected=branches.project(note,b['id']);ids={c['id']:c for c in selected['claims']}
            for value in note['reading_layout']['coverage'][b['id']].values():
                value['claim_hashes']={cid:guide.claim_hash(ids[cid]) for cid in value.get('claim_refs',[]) if cid in ids}
            if note['id']=='heluo-huamulan' and b['id']=='ming':
                for field,refs in [('early.operation',['ming-economy','ming-opening-yixing']),('auction1.heroes',['ming-first-auction']),('auction1.priority',['ming-first-auction'])]:
                    note['reading_layout']['coverage'][b['id']][field]={'status':'covered','claim_refs':refs,'claim_hashes':{cid:guide.claim_hash(ids[cid]) for cid in refs}}
        note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'条件同行、后期基础与条件调整、逐张效果牌及明先生补充','previous':before,'merged_duplicates':retired})
        audit[note['id']]={'before_ids':[c['id'] for c in before['claims']],'after_ids':[c['id'] for c in note['claims']],'retired':retired,'locations':deepcopy(note['reading_layout']['claim_locations'])}
    return items,audit

if __name__=='__main__':
    import sys,wxq,workspace,markdown_sync
    root=Path(__file__).resolve().parents[4];report=root/'raw/reports/bound-guide-expression'
    with workspace.store_lock(root,wait=True):
        workspace.recover(root);markdown_sync.scan(root,_locked=True);markdown_sync.assert_clean(root)
        items,audit=migrate(workspace.notes(root),wxq.entities(root))
        report.mkdir(parents=True,exist_ok=True);wxq.atomic_json(report/'migration-map.json',audit)
        if '--apply' in sys.argv:workspace.persist(root,items,_sync=False)
        else:
            workspace.prepare(root,items)
            for n in items:
                if n['id'] not in TARGETS:continue
                for path,text in branches.documents(n).items():
                    target=report/'preview'/Path(path).name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,'utf8')
                    b=next(b for b in n['meta']['player_branches'] if branches.document_path(n,b)==path)
                    assert branches.parse_document(text,n,b['id'])==guide.initial_sections(n,b['id'])
            print('preview',len(audit))
