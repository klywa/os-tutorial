"""Reviewed content update for five existing notes, separate from general reader rules.

Preview by default. --apply saves through the shared transaction after readback checks.
"""
from copy import deepcopy
from pathlib import Path
import json, re, sys, hashlib
import wxq, workspace, markdown_sync, guide_layout as guide, player_branches as branches

TARGET='heluo-huamulan'
REVISION='principle-purchase-2026-10-21'
PURCHASE={
 '花木兰':'首张出现即买以启动输出，未觉醒时继续留重复牌；觉醒后不再为合成专搜同名牌，后续优先把等级资源和古币给花木兰，买牌须留古币操作预算。',
 '上官婉儿':'看到首张即买并保留重复牌，优先追觉醒以覆盖6名河洛英雄；觉醒后停止为合成继续买同名牌，保留露娜和整备牌预算。',
 '李白':'顺路先买一张，花木兰到场且上官婉儿觉醒预算有保障后再补重复牌；觉醒后停止为合成继续买，已有零钱兑换、古币本身不再加永久等级时更重视李白的临时等级加成。',
 '武则天':'首张顺路买以补产币和永久等级，预算允许再追觉醒；觉醒后不为合成专搜，但仍可在有打出位置且需要精致古币时购买重复牌触发登场，缺位置或本轮古币已够则停。',
 '程咬金':'顺路先买一张，通常不追觉醒；已选零钱兑换、需要把精致古币换为更多破损古币时才增加重复牌投入，觉醒后停止为合成购买。',
 '露娜':'程咬金、上官婉儿整备体系就位时购买，预算充足可提前留一张；不以觉醒为买牌目标，需要更多古币和花木兰复生时仍可反复买露娜触发登场，本轮资源够用或没有打出位置时停止投入。',
 '盾山':'缺手牌古币且有位置让盾山阵亡时买一张，不专搜；需要精致古币、又有零钱兑换或幸运硬币联动时才比较觉醒，产币已够或准备换钟馗时停止购买。',
 '钟馗':'出现高等级敌人、需要通过牺牲降级时才买一张，普通先用；降级收益确有不足且核心预算有余才补觉醒，觉醒或当前降级已够时停止购买。',
 '明世隐':'花木兰已有临时等级、还需转为永久等级且有位置时才买；有余裕再补觉醒，觉醒后仍可在需要提高本轮转化额度时买重复牌触发登场，接近终局或无法安排连线时停。',
 '太乙真人':'有额外人口且花木兰复生不足时顺路买一张，不专搜；不为尚未确认的完美复生差异追加购买，复生足够或没有人口则不继续买。',
 '苏烈':'开局看到且能改善保血时买一张，不付费搜、不专追觉醒；已有有效前排或花木兰能接管战斗时停止买。',
 '李元芳':'开局有苏烈等河洛承伤英雄时顺路买一张，不专搜、不追觉醒；过渡已稳或上官婉儿接管用币后停止买。',
 '弈星':'还需棋手升级、又能承受精简阵容的战力时顺路买一张，不专搜、不追觉醒；已达目标棋手等级或急需保血时停止买。',
 '牛魔':'补一张就有机会取胜、兑现凯旋能量时才买，不专搜、不追觉醒；补了仍难赢或体系已接管时停止买。',
 '李信':'花木兰未到、现有输出无法保血时顺路买；只有重复牌或等级投入能立即减少掉血时才追加，不培养完整李信体系，花木兰接管后停止买。',
 '司空震':'已有冻结成长条件且不影响花木兰体系时顺路买，不为双输出专搜；持续成长、预算足够时可补觉醒，觉醒后停止为合成买牌，无法继续成长时也停止投入。',
}
CORE='花木兰承担主要输出和前排承伤：全队本回合每使用5张古币，为花木兰增加1次复生；古币及李白、武则天的增级效果提高花木兰每条命的伤害和坦度。上官婉儿整备给多名河洛英雄使用古币，程咬金整备产币，露娜登场再次触发整备，把资源转成等级与复生次数；优势来自持续成长和反复输出。保留露娜打出位置，先补产币与整备成员，再用触发牌；复生够用时存牌，遇强敌再投入，装备同时解决伤害、控制和追击缺口。'
ADVANTAGE={
 'ming':'明先生用卦象·节积累升级能量，转卦象·丰免费刷新补核心，优势是把经济与找牌技能用于更快完成古币体系。',
 'zhuang':'庄小鱼依靠升级奖励和如梦似幻按场上河洛成员补手牌、觉醒；成员选择决定奖励价值，不能为凑人数塞无用英雄。',
 'naonao':'闹闹选择河洛后用派对泡泡补同阵营英雄，上阵6名所选阵营英雄取得朋友多多补手牌；奖励随机且受棋手等级影响，应先保证能拿到所需品阶。',
 'zhaojun':'昭君用冻结变化和深度冻结强化补高品阶英雄，命中花木兰可加快成型；已有持续成长的司空震时可兼任第二输出，变化仍随机且受强化和牌库条件限制。',
 'ying':'嬴律以战略建立经济或全队成长优势，再用至高决策补牌和资源；决策对全场生效，须比较同行收益，首购激励生效时先买真正需要复制的牌。',
}
LOOP='全队本回合每使用5张古币，为花木兰增加1次复生；上官婉儿整备给3名不同河洛英雄各使用1张古币，觉醒后为6名；程咬金整备产币，露娜登场随机触发2名英雄整备。'
EFFECTS={
 '唤醒':('已有露娜或能近期取得露娜、且准备补古币时顺路买并预留；本轮面临淘汰、露娜在场时可专门找，已有触发牌足够或暂时无法上露娜则停买。','使用时指定在场露娜，先确认程咬金、上官婉儿就位；只保留这两名整备英雄可避免露娜随机选到其他目标。'),
 '古币多多':('缺花木兰等级或复生用币时顺路买，战力够且已有用币储备时停买，不无条件专搜。','暂时不投入战力可保留此效果牌；打出后把古币用于花木兰，若古币带转瞬则当回合用完。'),
 '集体唤醒':('武则天或露娜已到场、需要追加产币和整备时顺路买并预留；即将被淘汰且有这些目标时可集中找，目标缺失或手牌已够则停买。','先上武则天与露娜，再触发全体登场：武则天产生精致古币，露娜触发整备；若还要用全军动员，先集体唤醒再全军动员。'),
 '临阵磨枪':('上官婉儿已到场或接近成型时顺路买并预留；本轮急缺复生、又没有露娜打出位置时可专门找，已有触发牌足够则停买。','需要当轮战力时指定上官婉儿触发整备，先确认河洛英雄人数足够；普通婉儿覆盖3名，觉醒婉儿覆盖6名。'),
 '全军动员':('程咬金与上官婉儿已就位、需要补用币时顺路买并预留；淘汰风险迫近且触发牌不足时可找，成员未就位或储备足够时停买。','触发程咬金产币和上官婉儿用币；同时持有集体唤醒（触发全体登场）时，先让武则天产币及露娜触发整备，再用全军动员。'),
 '天籁琴音':('花木兰、上官婉儿或李白等关键英雄有觉醒缺口时购买或竞拍，补齐所需妙音后停止投入；已全部觉醒则不为本阵容专门拿。','按缺口优先给上官婉儿补整备覆盖、给花木兰补牺牲临时等级、给李白提高古币临时等级收益；不耗尽当轮买牌及保血资源。'),
 '展翅腾飞':('本回合确需集中刷新找露娜、花木兰或上官婉儿重复牌，且有购买预算和操作时间时拿；关键牌已齐、预算不足或来不及操作则不买，不为囤积无条件竞价。','在能完成多次刷新与购买的回合使用，免费刷新不免除买牌费用。'),
 '高级人才':('还缺花木兰、露娜或武则天，且能留到适合棋手等级时顺路买；已补齐关键组件则不再专门搜，不能挤掉当前保血预算。','可留到棋手4级使用，随机取得5品阶英雄以争取核心；奖励不保证命中花木兰、露娜或武则天。'),
}
SKILLS={
 'ming':[('先知卦象','开局比较卦象·节的能量与额外刷新费用，集中找花木兰、上官婉儿时再转卦象·丰；保留买牌预算，不把免费刷新当免费购买。'),('天降鸿运','取得命运馈赠后，缺升级与买牌资源时比较阴的能量收益，需要保血时比较阳的全队等级；按当轮缺口选择。')],
 'zhuang':[('梦境游戏','升级时的效果牌随机，不为指定奖励反复升级；保留花木兰和上官婉儿买牌预算。'),('美梦成真','棋手5级、6级各获得如梦似幻；按场上有用河洛英雄选择第一次3名或5名、第二次6名或7名方案，不为人数卖掉保血战力。'),('引擎升级','取得梦幻引擎后，用梦幻商店补露娜；先补其他英雄觉醒，再放未觉醒露娜，并核对公共牌库库存，不能把未来失败触发当本轮保命。')],
 'naonao':[('派对泡泡','选择河洛后花能量补河洛英雄；先提高棋手等级让奖励品阶覆盖花木兰，再集中补牌，不能把随机英雄当指定花木兰。'),('快乐集结','需要上阵6名技能所选阵营英雄才获得朋友多多，奖励为随机5张该阵营英雄；使用前检查棋手等级覆盖所需品阶，并保留处理手牌及转瞬古币的时间。'),('狂欢时刻','棋手6级取得专属强化后，按当前古币与复生缺口选择阵营天赋，不因追强化挤掉本轮买牌与保血资源。')],
 'zhaojun':[('冰之心','有用河洛英雄可冻结尝试获得更高品阶英雄，继承等级帮助保留战力；结果随机，不保证花木兰，冻结露娜补牌也须核对公共牌库。'),('极寒冰冻','深度冻结提供随机强化选择；需要同阵营补牌时比较霜寒进化，需要让冻结目标保留原身份并补觉醒时比较寒冰觉醒，不把不同强化效果混算。')],
 'ying':[('最高决策者','先选战略再打英雄：低压运营保血争胜、固定收益稳定积累、沉淀收益比较停级收益、风险对冲容许精简过渡；不能把主动连败套到低压运营。'),('至高之主','每次颁布至高决策前比较自己与同行收益；首购激励生效时先买武则天、露娜或所需效果牌，投资回报只在满足出牌数条件后期待随机奖励，资源再分配需有人实际淘汰才兑现。')],
}
DEPENDENCIES={
 '凝渊':'达到100%暴击率后触发追击移速的装备凝渊',
 '暴君归来':'使复生英雄获得200%攻速、100%暴击率及1.5秒无敌的天赋暴君归来',
 '零钱兑换':'把古币换为2张、精致古币换为4张不加永久等级破损古币的天赋零钱兑换',
 '破妄之刃':'提供60%移速、免疫减速且将50%伤害转为真实伤害的破妄之刃',
}
HERO_DETAILS={
 '花木兰':'普通牺牲增加10临时等级，觉醒增加20；古币指定河洛英雄永久等级+2，精致古币+4，转瞬牌须本回合用完。',
 '上官婉儿':'古币指定河洛英雄永久等级+2；全队本回合每使用5张古币，花木兰增加1次复生，整备覆盖更多人就能更快补复生。',
 '李白':'古币本身给河洛英雄2永久等级，精致古币为4；李白的额外临时等级只影响本场战力，不能当成永久等级。',
 '武则天':'普通在场使古币提升的等级+1、登场获得1张精致古币，觉醒分别提高为+2和2张；古币给河洛英雄2永久等级，精致古币为4。露娜登场触发整备，集体唤醒触发全体登场；全队每回合用5张古币给花木兰1次复生。',
 '程咬金':'普通古币给河洛英雄2永久等级，精致古币为4；全队本回合每使用5张古币给花木兰1次复生。零钱兑换把古币换为2张、精致古币换为4张不加永久等级的破损古币。',
 '露娜':'程咬金整备获得1张古币并对自身用1张，上官婉儿整备给3名不同河洛英雄各用1张、觉醒覆盖6名；古币给河洛英雄2永久等级，全队本回合每用5张古币给花木兰1次复生。唤醒是指定英雄触发登场的效果牌，可指定留场露娜。',
 '盾山':'古币给河洛英雄2永久等级，精致古币为4；零钱兑换把它们换成2张或4张不加永久等级的破损古币，幸运硬币使手动打出古币有概率额外触发1—3次。全队本回合每用5张古币给花木兰1次复生。',
 '明世隐':'普通可转化最近英雄的2临时等级，登场再加2；觉醒分别为4和4。连接花木兰可把李白通过古币提供的临时等级转为永久等级。',
 '李信':'每当己方有牺牲效果的英雄阵亡，李信增加7临时等级；技能短暂免控后挥剑气造成物理伤害，承接物理装备保血。',
 '司空震':'其他英雄获得临时等级时，普通司空震继承一半、上限为自身真实等级1倍，觉醒继承全部、上限为自身真实等级2倍；花木兰通过古币和李白获得临时等级时可带动司空震。昭君的雪暴时刻使冻结英雄解冻后永久等级+20，寒冰觉醒使解冻英雄不变且觉醒进度+2；须已有能保留司空震身份的冻结配置才考虑持续成长，普通随机向上变化不能保证保留司空震。',
 '钟馗':'普通牺牲使击败者等级临时降低10%，觉醒为20%，每名受益英雄每场限1次；等级投入到10级时解锁的钩锁是额外控制用途，不是降级生效的前提。',
 '太乙真人':'普通复生与完美复生的具体状态恢复差别尚未确认，因此没有确定的觉醒追逐阈值，普通提供一次复生已经能承担此处保护用途。',
 '牛魔':'凯旋在己方获胜时提供能量，普通获得1能量，觉醒获得2能量。',
}

def effect_sentence(card):
    return card['effect'].replace('\n','；').rstrip('。；')+'。'

def order_hero(text,name):
    label='**'+name+'：** '
    purchase='购买：'+PURCHASE[name]
    if not text.startswith(label+purchase):return text
    body=text[len(label+purchase):]
    detail=HERO_DETAILS.get(name,'')
    if detail and body.endswith(detail):
        body=body[:-len(detail)]
        awakening=re.search(r'觉醒(?:及等级投入)?：',body)
        if not awakening:raise ValueError('英雄说明缺觉醒字段：'+name)
        body=body[:awakening.start()]+detail+body[awakening.start():]
    level=re.search(r'(?:觉醒及)?等级投入：[^。]*。',body)
    if not level:raise ValueError('英雄说明缺等级投入字段：'+name)
    return label+body[:level.end()]+purchase+'上阵：'+body[level.end():]

def complete_comparisons(note,cards):
    previous=[]
    for c in note['claims']:
        if not c['id'].startswith(('v4-equipment-','v4-talent-')):continue
        prior=deepcopy(c);name=re.match(r'^\*\*([^*]+)：',c['text'])[1]
        c['text']=c['text'].replace('比只增加物防的冥王更切合伤害需求','比依靠附近敌人提供物防及基础攻击加成的冥王更切合伤害需求')
        for dep in ('制裁之剑','反伤重甲','魂灭灵冠','炽热支配者','贤者的庇护','超速成长'):
            if name==dep or dep not in c['text']:continue
            card=next(x for x in cards if x['name']==dep and x['category'] in ('equipment','effect-cards','talents'))
            clause=dep+'的相关效果：'+effect_sentence(card)
            if clause not in c['text']:c['text']+=clause
        if name=='幸运硬币':
            clause='手牌来源包括程咬金整备获得古币、盾山阵亡获得古币、武则天登场获得精致古币；普通古币给河洛英雄2永久等级，精致古币给4。'
            if clause not in c['text']:c['text']+=clause
        if name=='暴君归来':
            clause='花木兰本回合每由全队使用5张古币增加1次复生，须先有复生次数才能兑现此天赋。'
            if clause not in c['text']:c['text']+=clause
        if c!=prior:
            if c.get('origin')=='manual':raise ValueError('人工结论需审查后单独处理：'+c['id'])
            c.setdefault('editorial_derivations',[]).append({'reason':'补足换装及收益比较的必要机制','inference':True,'previous_claim':prior,'card_snapshots':[deepcopy(x) for x in cards if x['name'] in c['text'] and x['category'] in ('equipment','effect-cards','talents')]})
            previous.append(prior)
    return previous

def migrate(items,root):
    items=deepcopy(items);note=next(n for n in items if n['id']==TARGET)
    cards=wxq.read_json(root/'knowledge/cards/index.json',{})['cards']
    if note['reading_layout'].get('content_revision')==REVISION:
        previous=complete_comparisons(note,cards);repaired=[c['id'] for c in previous]
        for c in note['claims']:
            phrase='仅需更高质量复生且预算宽裕时考虑觉醒'
            if c['id'].startswith('v4-hero-') and c['text'].startswith('**太乙真人：**') and phrase in c['text']:
                if c.get('origin')=='manual':raise ValueError('人工结论需审查后单独处理：'+c['id'])
                previous.append(deepcopy(c));c['text']=c['text'].replace(phrase,'不为尚未确认的完美复生差异追加购买');repaired.append(c['id'])
            if c['id'].startswith('v4-hero-'):
                name=re.match(r'^\*\*([^*]+)：',c['text'])[1]
                text=order_hero(c['text'],name)
                if text!=c['text']:
                    if c.get('origin')=='manual':raise ValueError('人工结论需审查后单独处理：'+c['id'])
                    previous.append(deepcopy(c));c['text']=text;repaired.append(c['id'])
        if repaired:note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'补齐独立阅读说明；英雄按作用、觉醒、等级、购买、上阵顺序组织','previous':{'claims':previous}})
        return items,{'changed_claims':repaired} if repaired else {}
    before=deepcopy(note);old={c['id']:deepcopy(c) for c in note['claims']}
    byname={c['name']:c for c in cards if c['category']!='heroes' or not c.get('awakened')}
    layout=note['reading_layout'];changed=[]
    layout['requires_principle']=True
    layout['compact_operation_refs']={b['id']:['v4-operation-'+b['id']+'-'+stage for stage in guide.STAGES] for b in note['meta']['player_branches']}
    def update(c,text,snapshots=()):
        if c.get('origin')=='manual':raise ValueError('人工结论需审查后单独处理：'+c['id'])
        if c['text']==text:return
        c['text']=text
        c.setdefault('editorial_derivations',[]).append({'reason':'购买条件及独立阅读机制说明','inference':True,'previous_claim':deepcopy(old[c['id']]),'card_snapshots':deepcopy(list(snapshots))})
        changed.append(c['id'])
    def add(bid,cid,section,text,refs,snapshots=()):
        evidence=list({json.dumps(e,sort_keys=True):deepcopy(e) for rid in refs for e in old[rid].get('evidence',[])}.values())
        note['claims'].append({'id':cid,'section':section,'text':text,'condition':'','version':None,'kind':'general_strategy','inference':True,'evidence':evidence,'derivation':{'claim_refs':refs,'card_snapshots':deepcopy(list(snapshots))}})
        next(b for b in note['meta']['player_branches'] if b['id']==bid)['claim_refs'].append(cid)
        layout['claim_locations'][cid]=[section];changed.append(cid)
    for c in list(note['claims']):
        label=re.match(r'^\*\*([^*]+)：\*\*\s*',c['text'])
        name=label[1] if label else None
        if c['id'].startswith('v4-hero-'):
            body=c['text'][label.end():]
            if name=='太乙真人':body=body.replace('需要完美复生提高重新上场的质量且预算允许时再追','觉醒会把开团复生改为完美复生，但恢复状态的具体差别尚未确认，不据此强追觉醒')
            update(c,order_hero('**'+name+'：** 购买：'+PURCHASE[name]+body+HERO_DETAILS.get(name,''),name),[card for card in cards if card['category']=='heroes' and card['name']==name])
        elif guide.location(note,c)==['关键效果牌'] and name in EFFECTS:
            buy,use=EFFECTS[name];card=byname[name]
            if name=='天籁琴音':use+='上官婉儿觉醒把整备覆盖从3名河洛英雄提高到6名；花木兰牺牲临时等级从10提高到20；李白使古币额外提供的临时等级从4提高到8。'
            recap=LOOP if name in ('唤醒','古币多多','集体唤醒','临阵磨枪','全军动员') else ''
            update(c,'**'+name+'：** '+effect_sentence(card)+' '+recap+'购买：'+buy+'使用：'+use+' 没有已确认的固定购买价格或竞价上限。',[card])
        elif c['id'].startswith(('v4-equipment-','v4-talent-')):
            text=c['text']
            for dep,explanation in DEPENDENCIES.items():
                if dep!=name and dep in text:text=text.replace(dep,explanation)
            if name=='零钱兑换':text+='李白在场使古币额外提供4临时等级，觉醒为8；破损古币也计入全队每5张古币给花木兰1次复生的次数。'
            if name=='幸运硬币':text+='额外触发增加古币结算收益；全队本回合每使用5张古币为花木兰增加1次复生，不把一次额外触发直接当成独立手动打牌。'
            update(c,text)
        elif guide.location(note,c)==['棋手技能推荐']:
            text=c['text'];snap=[]
            for card in cards:
                if card['category'] not in ('player-skills','skills'):continue
                if card['name'] in text and card['effect'] not in ('未提供',''):
                    snap.append(card)
            # Actual categories vary by entity import; selected player skill ids are stable.
            if not snap:
                snap=[card for card in cards if card['id'].startswith(('card:939','card:931','card:934','card:940','card:943','card:663108')) and card['name'] in text]
            if any(card['name']=='人才储备' for card in snap):snap.append(byname['人才搜寻'])
            if '低压' in text and not any(card['name']=='低压运营' for card in snap):snap.append(byname['低压运营'])
            effects=' '.join(card['name']+'：'+effect_sentence(card) for card in snap)
            update(c,effects+text,snap)
    # Add full player skill explanations; old strategy IDs and conditions remain visible.
    for b in note['meta']['player_branches']:
        bid=b['id'];projection=branches.project(before,bid)
        refs=[c['id'] for c in projection['claims'] if guide.location(before,c) in (['核心机制'],['棋手技能推荐'])]
        refs=list(dict.fromkeys(refs+['coin-loop','wanner-awaken']))
        refs=[r for r in refs if r in old]
        add(bid,'principle-'+bid,'核心原理',CORE+ADVANTAGE[bid],refs)
        for name,reason in SKILLS[bid]:
            card=byname[name];deps={'先知卦象':['卦象·节','卦象·丰'],'天降鸿运':['命运馈赠','命运馈赠·阴','命运馈赠·阳'],'美梦成真':['如梦似幻'],'引擎升级':['梦幻引擎'],'快乐集结':['朋友多多'],'狂欢时刻':['打成一片'],'极寒冰冻':['深度冻结','霜寒进化','寒冰觉醒'],'最高决策者':['战略决策','低压运营','固定收益','沉淀收益','风险对冲'],'至高之主':['至高决策','首购激励','投资回报','资源再分配']}.get(name,[])
            snap=[card]+[byname[n] for n in deps]
            text='**'+name+'：** '+' '.join((x['name']+'：' if x!=card else '')+effect_sentence(x) for x in snap)+reason
            add(bid,'skill-profile-'+bid+'-'+card['id'].split(':')[1],'棋手技能推荐',text,refs,snap)
    changed.extend(c['id'] for c in complete_comparisons(note,cards))
    layout['content_revision']=REVISION
    # Re-review hashes for changed conclusions, leaving partial/missing coverage unchanged.
    byid={c['id']:c for c in note['claims']}
    for rows in layout.get('coverage',{}).values():
        for row in rows.values():
            if isinstance(row,dict):row['claim_hashes']={rid:guide.claim_hash(byid[rid]) for rid in row.get('claim_refs',[]) if rid in byid}
    note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':REVISION,'previous':before})
    return items,{'changed_claims':changed,'original_claims':len(old)}

def main():
    root=Path(__file__).resolve().parents[4];report=root/'raw/reports/principle-purchase'
    with workspace.store_lock(root,wait=True):
        workspace.recover(root);markdown_sync.scan(root,_locked=True);markdown_sync.assert_clean(root)
        original=workspace.notes(root);items,audit=migrate(original,root)
        report.mkdir(parents=True,exist_ok=True)
        if not (report/'before.json').exists():wxq.atomic_json(report/'before.json',{'notes':original})
        workspace.prepare(root,items)
        note=next(n for n in items if n['id']==TARGET)
        for path,text in branches.documents(note).items():
            (report/Path(path).name).write_text(text,encoding='utf8')
            b=next(b for b in note['meta']['player_branches'] if branches.document_path(note,b)==path)
            assert branches.parse_document(text,note,b['id'])==guide.initial_sections(note,b['id'])
            core=text.split('## 核心原理\n\n')[1].split('\n\n## ')[0]
            assert '\n\n' not in core.strip() and len(re.sub(r'[*\s]','',core))<=500
        wxq.atomic_json(report/'audit.json',audit)
        if '--apply' in sys.argv:
            changed={n['id']:n for n in items if next(o for o in original if o['id']==n['id'])!=n}
            changed.setdefault(TARGET,note)
            updates={}
            for path in (root/'knowledge/replays').glob('*.json'):
                data=wxq.read_json(path,{})
                if not isinstance(data,dict) or not isinstance(data.get('notes'),list):continue
                prior=deepcopy(data);data['notes']=[deepcopy(changed.get(n['id'],n)) for n in data['notes']]
                if data!=prior:updates[str(path.relative_to(root))]=data
            replay='knowledge/replays/核心原理与购买条件-2026-10-21.json'
            if audit or not (root/replay).exists():updates[replay]={'notes':list(changed.values())}
            if items!=original or updates:workspace.persist(root,items,_sync=False,_replay_updates=updates)
        print('applied' if '--apply' in sys.argv else 'preview',len(note['claims']),'claims',len(audit.get('changed_claims',[])),'changed')

if __name__=='__main__':main()
