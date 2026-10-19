"""Reviewed, replayable migration to semantic guide chapters (no acquisition)."""
from copy import deepcopy
from pathlib import Path
import json,re
import guide_layout as guide
import player_branches as branches

HELUO_LOCATIONS={
 'first-auction':['第一轮拍卖'],'ming-six-dispute':['阵容组成与运营节奏',guide.STAGES['middle']],
 'zhuang-opening-dispute':['阵容组成与运营节奏',guide.STAGES['early']],
 'zhuang-delayed-dispute':['阵容组成与运营节奏',guide.STAGES['middle']],
 'ming-five':['阵容组成与运营节奏',guide.STAGES['middle']],
 'zhuang-three-five':['阵容组成与运营节奏',guide.STAGES['middle']],
 'n-opening':['阵容组成与运营节奏',guide.STAGES['early']],
 'q-start':['定阵条件'],'ying-resource':['棋手技能推荐'],
 'ying-first-second-skill':['棋手技能推荐'],'ying-capital-timing':['阵容组成与运营节奏',guide.STAGES['early']],
 'ying-outcome-decisions':['棋手技能推荐'],'ying-combat-decisions':['棋手技能推荐'],
 'ying-avoid-decisions':['棋手技能推荐'],'revive-cap-pending':['附录','版本差异'],
 'luna-awakening-context':['阵容组成与运营节奏',guide.STAGES['middle']],
 'libai-awaken-before-coins':['阵容组成与运营节奏','后期提升思路'],
 'find-luna-alternatives':['阵容组成与运营节奏',guide.STAGES['late']],
 'zhuang-dream-luna':['阵容组成与运营节奏',guide.STAGES['late']],
 'ying-first-purchase':['阵容组成与运营节奏',guide.STAGES['late']],
 'ying-contract-bottle':['关键效果牌'],'zhuang-high-talent':['关键效果牌'],
 'wake-targets':['关键效果牌'],'hold-coin-effect':['关键效果牌'],
 'enter-before-prep':['关键效果牌'],
}

def derive(note,cid,text,parents,location,owners=None):
    old={c['id']:c for c in note['claims']}
    if cid in old:return
    sources=[old[x] for x in parents];evidence=[]
    for c in sources:
        for e in c.get('evidence',[]):
            if e not in evidence:evidence.append(deepcopy(e))
    c=deepcopy(sources[0]);c.update(id=cid,text=text,section=location[0],derived_from=parents,evidence=evidence)
    note['claims'].append(c);note['reading_layout']['claim_locations'][cid]=location
    if owners is None:
        common=set(note['meta']['common_claim_refs'])
        if set(parents)<=common:note['meta']['common_claim_refs'].append(cid);return
        owners=[b['id'] for b in note['meta']['player_branches'] if set(parents)<=common|set(b['claim_refs'])]
    for b in note['meta']['player_branches']:
        if b['id'] in owners:b['claim_refs'].append(cid)

def standardize(value):
    if isinstance(value,str):
        return value.replace('能量卦象','卦象·节').replace('刷新卦象','卦象·丰').replace('卦象优先选能量','卦象优先选卦象·节')
    if isinstance(value,list):return [standardize(x) for x in value]
    if isinstance(value,dict):return {k:standardize(v) for k,v in value.items()}
    return value

def migrate(items,entities):
    items=deepcopy(items);names={e['name']:e['id'] for e in entities};byid={n['id']:n for n in items};audit={}
    for n in items:
        if not branches.enabled(n) or guide.enabled(n):continue
        before=deepcopy(n);layout={'version':2,'claim_locations':{},'coverage':{}}
        n['reading_layout']=layout
        for c in n['claims']:
            layout['claim_locations'][c['id']]=guide.location(n,c)
            if c['section'].startswith('针对对手'):layout['claim_locations'][c['id']]=['制敌手段']
            if c['section']=='条件与待裁决':layout['claim_locations'][c['id']]=['推荐装备'] if c['id']=='equipment-ailin-pending' else ['阵容组成与运营节奏',guide.STAGES['middle']]
        if n['id']=='heluo-huamulan':
            layout['claim_locations'].update(HELUO_LOCATIONS)
            # Explicit card names established by existing player-skill entities.
            for field in ('claims','meta'):n[field]=standardize(n[field])
            c=next(c for c in n['claims'] if c['id']=='ming-five')
            c['text']=c['text'].split('；留五本持续刷新')[0]+'；五本持续刷新时集中补花木兰、上官婉儿及过渡战力。若考虑升六本改善后续高阶牌机会，先确认升本后仍有买牌与保血预算，不能只有刷新而没有当轮战力。'
            derive(n,'guide-effect-wake','唤醒用于已在场的露娜，临阵磨枪用于上官婉儿：前者借露娜再次触发整备，后者直接触发婉儿整备。使用前确认目标、河洛产币成员和露娜打出位置已经就绪。',['wake-targets','luna-slot'],['关键效果牌'])
            derive(n,'guide-counter-lixin','已成型的瑶妹牺牲李信可以借小鹿嘲讽和承伤，让缺少免控的花木兰难以接近李信，并消耗其复生次数。成立条件是小鹿能承压、李信已有战力且花木兰免控不足；不能泛化成任何花木兰配置都被克制。',['mulan-vs-yaomei-lixin'],['克制手段'])
            derive(n,'guide-skills-ming','明先生前期优先卦象·节积累升本资源；进入找花木兰、上官婉儿的阶段后比较卦象·丰。切换时看是否已经需要集中找牌，并保留过渡战力；第7回合是材料中的找牌节奏，不是所有对局的固定切换回合。',['ming-economy','ming-five'],['棋手技能推荐'])
            derive(n,'guide-skills-zhuang','庄小鱼五本、六本各用一次如梦似幻补体系和觉醒。第一次如梦按有用河洛成员选择3名或5名方案；等待更多成员会失去当轮战力时先保血。第二次体系齐备可按7名结算，仍缺关键组件时可用6名继续补牌；后续梦幻引擎需满足低血量且当轮失败条件，不能当成无条件资源。',['zhuang-dream-trigger','zhuang-three-five','zhuang-second-cast'],['棋手技能推荐'])
            derive(n,'guide-skills-naonao','闹闹先保留升本资源，升级后用派对牌找对应等阶英雄。材料参考第8回合五本使用朋友多多；用后仍缺花木兰时，可在五本多留一回合用免费刷新补核心，稳定后再升六拿专属强化。五本启动要提前留出处理手牌和转瞬古币的时间。',['n-opening','n-five-missing','n-time'],['棋手技能推荐'])
            derive(n,'guide-skills-zhaojun','昭君需较早取得花木兰及适合的冻结强化，再以冻结补高阶体系；同阵营向上变化不保证得到花木兰。已有持续冻结成长的司空震时可保留第二输出；冻结露娜补露娜仍受强化与公共牌库限制，不把单次成功当成必成循环。',['q-start','q-double','q-luna'],['棋手技能推荐'])
            derive(n,'guide-middle-awakening','中期优先补上官婉儿觉醒，提高每次整备覆盖的河洛人数；完整产币时保留6名河洛，避免为工具位挤掉产币成员。只有程咬金和婉儿两名整备英雄时，普通露娜随机触发两名已能覆盖两者，露娜觉醒不是循环启动前提。',['wanner-awaken','luna-awakening-context'],['阵容组成与运营节奏',guide.STAGES['middle']])
            # Late members inherit the reviewed common skeleton; tool is conditional.
            n['meta']['compositions']['late']=deepcopy(n['meta']['late_variants'][0]['members'])
            for m in n['meta']['compositions']['late']:
                if m['hero']==names.get('钟馗'):m['necessity']='optional';m['role']='决赛需要牺牲降级时补入，并检查花木兰覆盖'
        elif n['id']=='yaomei-sacrifice-lixin':
            c=next(c for c in n['claims'] if c['id']=='growth-ming')
            conflict=next(c for c in n['claims'] if c['id']=='ming-wakeup-conflict')
            c['text']=c['text'].split('未觉醒时是否立即使用')[0]+conflict['text']
            c=next(c for c in n['claims'] if c['id']=='equipment-current-default')
            c['text']=c['text'].replace('具体敌方英雄的换装见“对局威胁与应对”。','面对爆发、控制或风筝时，分别检查减伤、免控与追击缺口，再替换第三件防护；不要把基础三件当作所有对局固定搭配。')
            derive(n,'guide-effects-level','简易协作、精密协作、八方来援、武装之力用于补李信等级。购买前比较李信能获得的确定等级与剩余金币；八方来援看实际阵营数量，武装之力看装备数量，随机增加等级不保证命中李信。李信临近100级时，少量等级也可能补出自身复生。',['level-effect-cards'],['关键效果牌'])
            derive(n,'guide-effects-wake','唤醒可让已上场的武则天或蒙犽再次触发登场，补精致古币、登场特训和锦囊。领先且不急需战力时可批量打出；大幅掉血时直接兑现，先腾打出位置，操作后补回所需牺牲成员。',['level-play-batch'],['关键效果牌'])
            derive(n,'guide-counter-barrier','班叔二级等离子屏障限制单次承伤，杨玉环补屏障回复，诸葛亮借连续施法回蓝并提高临时等级，三者同时到位可拖住李信的高额单次伤害。三级屏障和太乙真人复生可延长消耗；不能把缺少配套的单张英雄当作完整反制体系。',['counter-barrier'],['克制手段'])
            layout['claim_locations']['growth-deer-timeline']=['棋手技能推荐']
            layout['claim_locations']['order-six-before-double']=['棋手技能推荐']
            for cid,stage in [('middle-ming-choice','middle'),('ming-first-lixin','middle'),('level-effect-cards','late')]:layout['claim_locations'][cid]=['阵容组成与运营节奏',guide.STAGES[stage]]
        elif n['id']=='zhaojun-high-tier-dahe':
            derive(n,'guide-effect-transfer','传承、遗志用于转移张良积累的永久等级，随后按来牌换入后续输出或太乙真人；使用太乙真人时确认附身东皇太一。众星拱月按对手选择强化对象，图腾容易被快速清除时可比较东皇太一或司空震，不固定把等级集中给敖隐。',['claim-bf3ad0a0c80d84f2d6d4','claim-29c3973e29784ed330cf'],['关键效果牌'])
            derive(n,'guide-skills-freezing','第5回合按获取高品阶核心的需要，选择霜寒进化或冰封结晶；霜寒进化路线可冻结刘邦、韩信定向寻找东皇太一或敖隐。第8回合选择冰心领域补全队永久等级；六阶比较不朽坚冰的全队增益，适合多个重要英雄共同受益。',['claim-01efb21eac616296f20c','claim-163e42c476a496c5bbe8','claim-26b1737815308a1c1579'],['棋手技能推荐'])
            derive(n,'guide-counter-totem','带解控的嬴政会增加本阵容控制难度；姜子牙能快速清除图腾，削弱敖隐输出。针对图腾体系时，应看是否能及时解除关键控制或清除图腾，不能仅凭持有英雄名就认定稳定克制。',['claim-22b460bd4a7bae574bc0'],['克制手段'])
        elif n['id']=='angela-liubang-totems':
            derive(n,'guide-effect-growth','唤醒配合明世隐再次触发登场，把飞行器提供的临时等级转为永久等级；明世隐与唤醒来得多时使用该成长路线，来得少或晚时可用云中君替代。夺取之术可在后期把工具英雄的等级集中给刘邦，投入前确认当前还需要哪些成长位置。',['claim-9393479509a53e516912','claim-41e5ef7849bdfc174252'],['关键效果牌'])
            derive(n,'guide-skills-connect','飞行器前期连接干将莫邪，刘邦到场后改连刘邦。将飞行器与目标重合以避免连接最近的其他英雄。五阶久刷不来刘邦觉醒时，停止耗尽金币，考虑升六用超级连接的临时等级与额外模块稳住，再继续找觉醒。',['claim-3157c19df415c25c6e44','claim-34ce45f76864349fb218'],['棋手技能推荐'])
        # No inferred entity-overlap relationships in these guides.
        n['explicit_relationships']=True;n['related']=[];n['guide_related']=[]
        # A player's branch must not inherit another player's opening list.
        # Shared late skeleton is reused; the double-output variant remains explicit.
        for b in n['meta']['player_branches']:
            if '来牌' in b.get('selection',{}).get('signals',{}):
                b['selection']['signals']['来牌']={
                    'zhaojun-high-tier-dahe':'先找东皇太一与敖隐；虞姬迟迟不来时可先用司空震或海月承担输出，继续保留图腾组件。',
                    'angela-liubang-totems':'首张刘邦到场前工具英雄各留一张；先补刘邦觉醒，明世隐来得少或晚时可用云中君替代。',
                    'yaomei-sacrifice-lixin':'先拿第一张李信启动成长，再追觉醒；缺李信时用狄仁杰或百里守约带装备保血，不刷空金币。',
                }.get(n['id'],b['selection']['signals']['来牌'])
            playernote=next((p for p in items if p['type']=='player' and b['player'] in p.get('entities',[])),None)
            if playernote:
                n['related'].append({'id':playernote['id'],'type':'player','title':playernote['title'],'relation':'applicable_player','player':b['player']})
                n['guide_related'].append({'title':playernote['title'],'href':'../players/'+Path(playernote['path']).name,'note':playernote['id'],'branch':b['id'],'relation':'applicable_player'})
            n['guide_related'].append({'title':n['title']+'-'+branches.player_name(n,b),'href':Path(branches.document_path(n,b)).name,'note':n['id'],'player':b['player'],'exclude_branch':b['id'],'relation':'same_lineup_player'})
            populate_coverage(n,b)
            # The restored overview is derived from this branch's verified text.
            # Ambiguous names are left out rather than guessing an entity ID.
            selected=branches.project(n,b['id']);from overview import default_overview
            overview=default_overview(selected['meta'])
            categories={category:{} for category in ('talents','effect-cards','player-skills')}
            for entity in entities:
                if entity.get('category') in categories:categories[entity['category']].setdefault(entity['name'],[]).append(entity['id'])
            section_text=lambda title:'\n'.join(c['text'] for c in selected['claims'] if title in guide.location(n,c))
            for preset in overview['presets']:
                for field,category,title in [('talents','talents','推荐天赋'),('effect_cards','effect-cards','关键效果牌')]:
                    text=section_text(title)
                    preset[field]=[ids[0] for name,ids in categories[category].items() if len(ids)==1 and name in text]
                skilltext=section_text('棋手技能推荐')
                for player in preset['players']:
                    player['skills']=[ids[0] for name,ids in categories['player-skills'].items() if len(ids)==1 and name in skilltext]
                preset['talent_note']='按当轮保血、成长和资源缺口选择，不要求全部取得。'
                preset['effect_note']='按目标、打出位置和本轮资源需求使用；各牌不能互相替代全部作用。'
            b.setdefault('overrides',{})['overview']=overview
        n.setdefault('history',[]).append({'at':__import__('wxq').now(),'origin':'editorial','reason':'统一阶段章节与完整阅读','previous':before})
        audit[n['id']]={'claims_before':[c['id'] for c in before['claims']],'claims_after':[c['id'] for c in n['claims']],'locations':deepcopy(layout['claim_locations'])}
    for p in items:
        if p['type']!='player' or not p.get('lineup_adaptations'):continue
        p['explicit_relationships']=True
        p['related']=[{'id':n['id'],'type':'lineup','title':n['title'],'relation':'recommended_lineup'} for n in items if any(b['player'] in p.get('entities',[]) for b in n.get('meta',{}).get('player_branches',[]))]
    for n in items:
        if not guide.enabled(n):continue
        guide.project_matchups(n)
        claims={c['id']:c for c in n['claims']}
        for rows in n['reading_layout'].get('coverage',{}).values():
            for value in rows.values():
                if isinstance(value,dict):value.setdefault('claim_hashes',{cid:guide.claim_hash(claims[cid]) for cid in value.get('claim_refs',[]) if cid in claims})
    return items,audit

def populate_coverage(note,b):
    """Reviewed category checks. Budgets are partial unless an actual bound exists."""
    selected=branches.project(note,b['id']);cs=selected['claims'];rows={}
    def put(key,ids,status='covered',detail=''):
        ids=[x for x in ids if any(c['id']==x for c in cs)]
        if ids:rows[key]={'claim_refs':ids,'status':status,'detail':detail}
    for stage,label in guide.STAGES.items():
        relevant=[c for c in cs if guide.location(note,c)==['阵容组成与运营节奏',label]]
        put(stage+'.operation',[c['id'] for c in relevant])
        put(stage+'.awakening',[c['id'] for c in relevant if '觉醒' in c['text']], 'partial','部分英雄有觉醒说明，尚缺该阶段逐成员要求。')
        put(stage+'.budget',[c['id'] for c in relevant if any(x in c['text'] for x in ('预算','金币','能量','留钱','存钱','耗尽','免费刷新'))],'partial','有资源取舍，未建立该阶段完整投入上限。')
        put(stage+'.missing',[c['id'] for c in relevant if any(x in c['text'] for x in ('未到','没有','不来','替代','替换','缺','未取得','迟迟'))])
    for key,title in [('improvement','后期提升思路'),('equipment','推荐装备'),('talents','推荐天赋'),('skills','棋手技能推荐'),('effect_cards','关键效果牌')]:
        put(key,[c['id'] for c in cs if title in guide.location(note,c)])
    effects=[e['name'] for e in __import__('wxq').entities(Path(__file__).resolve().parents[4]) if e.get('category')=='effect-cards']
    heroes=[e['name'] for e in __import__('wxq').entities(Path(__file__).resolve().parents[4]) if e.get('category')=='heroes']
    for i,title in enumerate(('第一轮拍卖','第二轮拍卖','第三轮拍卖'),1):
        candidates=[c for c in cs if guide.location(note,c)==[title]]
        put(f'auction{i}.heroes',[c['id'] for c in candidates if any(x in c['text'] for x in heroes)])
        put(f'auction{i}.effects',[c['id'] for c in candidates if any(x in c['text'] for x in effects)])
        put(f'auction{i}.priority',[c['id'] for c in candidates if any(x in c['text'] for x in ('优先','再考虑','按缺口','按库存'))])
        put(f'auction{i}.budget',[c['id'] for c in candidates if any(x in c['text'] for x in ('预算','金币','出价','竞价','低价','能量','价格'))],'partial','仅适用条件或留资源原则已确认，缺少完整竞拍上限。')
    note['reading_layout']['coverage'][b['id']]=rows

if __name__=='__main__':
    import sys,wxq,workspace,markdown_sync
    root=Path(__file__).resolve().parents[4]
    with workspace.store_lock(root,wait=True):
        workspace.recover(root);markdown_sync.scan(root,_locked=True);markdown_sync.assert_clean(root)
        updated,audit=migrate(workspace.notes(root),wxq.entities(root))
        report=root/'raw/reports/guide-reading';report.mkdir(parents=True,exist_ok=True)
        if audit:wxq.atomic_json(report/'migration-map.json',audit)
        if '--apply' in sys.argv:workspace.persist(root,updated,_sync=False)
        else:
            workspace.prepare(root,updated)
            for n in updated:
                if guide.enabled(n):
                    for path,text in branches.documents(n).items():
                        (report/Path(path).name).write_text(text,encoding='utf-8');branches.parse_document(text,n,branches.branch(n,next(b['player'] for b in n['meta']['player_branches'] if branches.document_path(n,b)==path))['id'])
            print('preview ready',len(audit))
