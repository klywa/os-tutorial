"""Evidence-preserving player chapters and qualitative combination stage notes."""
from copy import deepcopy
from pathlib import Path
import re
import wxq,workspace,player_branches as branches
from tactics import claim_id

PLAYERS={'player-zhaojun','player-angela','player-yaomei','player-ming','player-zhuang','player-naonao','player-ying'}
ALIASES={'使用技巧':'适用技巧','适配阵容':'适用打法与选择'}


def stage(text,*refs,inference=True):
    return {'text':text,'claim_refs':list(refs),'inference':inference}


STRENGTH={
('zhaojun-high-tier-dahe','zhaojun'):{
 'early':stage('前期主要靠弈星及被冻结的过渡英雄支撑。对手质量低、补干将莫邪有机会取胜时可保血；对手明显更强时精简场面升本，不能把冻结的后续收益当成本轮战力。','claim-6e5677597b91d6042038'),
 'middle':stage('五本取得东皇太一、敖隐和图腾后，控制、回复与输出才逐步衔接。核心或虞姬未到时有过渡空窗，可按来牌用司空震、海月承担输出；第8回合冰心领域提供后续成长，不保证当轮压制所有对手。','claim-01efb21eac616296f20c','claim-163e42c476a496c5bbe8'),
 'late':stage('核心与图腾齐备后，可依靠全队等级、人口和不朽坚冰继续提升；等级转移及保护图腾是兑现成长的条件。图腾被范围伤害快速清除时，后期潜力不能自动转为胜势。','claim-bf3ad0a0c80d84f2d6d4','claim-4bfc796afce05484f9b4','guide-counter-totem')},
('angela-liubang-totems','angela'):{
 'early':stage('干将莫邪配牛魔、飞行器连接干将莫邪的开局，在前几轮有争胜能力；遇到更强速攻仍可能掉血。需要及时升本找刘邦，不能因开局赢过就长时间停留低本。','claim-c4c4113df9b0d149d5f9'),
 'middle':stage('首张刘邦到场后开始承接图腾等级与飞行器收益，五本补扁鹊可进一步稳血；刘邦未到或迟迟不觉醒时是明显风险窗口。连续刷新无进展时，应保留升六资源，而非耗尽金币追质量。','claim-36a64baf419544118526','claim-34ce45f76864349fb218'),
 'late':stage('刘邦觉醒、图腾等级积累及六阶超级连接齐备后，持续输出和临时等级收益更完整；终局可用太乙真人或等级集中继续提升。成长工具替换过早、被风筝或连接英雄难以存活，都会妨碍兑现后期战力。','claim-422443c0323fc3e782b9','claim-4047c5c02ecf461d3be8','claim-41e5ef7849bdfc174252','claim-9393479509a53e516912')},
('yaomei-sacrifice-lixin','yaomei'):{
 'early':stage('小鹿配过渡英雄有争取前期胜场的能力，胜场同时帮助保血和养小鹿；面对强势孙尚香或同行仍需补即时战力，不能只凭棋手认定必胜。','opening-four','opening-wins'),
 'middle':stage('没有李信、等级和复生配套未成时，是需要重点防守的空窗；不能将小鹿前期优势延续理解为中期也强。取得李信后才开始兑现成长，缺牌时靠装备承接者保血并避免刷空金币。','middle-no-lixin','middle-fast-five','middle-item-holder'),
 'late':stage('李信达到关键等级、牺牲与复生衔接后可持续输出；共鸣前安全升六可进一步放大收益。是否形成优势取决于等级、死亡顺序、复生形式及对手，不能忽略共鸣前被淘汰的风险。','growth-hundred','growth-zhongkui','taiyi-by-target','six-budget-pressure','order-six-before-double')},
('heluo-huamulan','ming'):{
 'early':stage('卦象·节主要提供升本资源，单挂弈星节约开销的同时会压低场上战力；只有补牛魔有机会取胜时才兼顾其产币。这个阶段的重点是控制掉血和升本成本，不能视为默认强势期。','ming-economy','ming-opening-yixing'),
 'middle':stage('五本转卦象·丰集中找花木兰、上官婉儿后，取得核心与觉醒进度才逐步补起战力；找牌不顺而只有刷新时存在空窗。李信、李白和现有装备可承担过渡，升六需保留本轮买牌与保血预算。','ming-five','ming-economy','missing-mulan'),
 'late':stage('产币成员、婉儿觉醒与露娜整备循环齐备后，复生和等级收益逐步完整；卦象带来的资源仍需转成有效战力。对手控制、风筝及本轮复生预算会限制上限，不能只凭已经成型判断强弱。','coin-loop','wanner-awaken','revive-budget','anti-burst','ailin-chase')},
('heluo-huamulan','zhuang'):{
 'early':stage('保血过渡与精简速五有不同代价：有把握取胜时补苏烈、牛魔保血；补牌也难赢时节约开销，但要承受掉血。尚未开如梦前，不宜把后续补牌能力当作现有战力。','zhuang-opening-dispute','opening-fighters'),
 'middle':stage('五本第一次如梦能集中补体系，是启动窗口；收益取决于场上有用河洛成员、核心来牌和合成安排。技能未补到核心、婉儿未觉醒或为凑人数塞无用牌时，仍有明显空窗。','zhuang-three-five','zhuang-delayed-dispute','save-search','guide-middle-awakening'),
 'late':stage('六本第二次如梦和满足条件的梦幻商店可继续补觉醒、露娜，支持后续循环；低血量失败触发资源的同时也意味着淘汰风险。强敌前仍需预留整备与复生预算，不为追求后续商店主动丢掉关键血量。','zhuang-second-cast','zhuang-dream-trigger','zhuang-dream-luna','revive-budget')},
('heluo-huamulan','naonao'):{
 'early':stage('前期围绕苏烈、李元芳等经济过渡，少花能量刷新并保留升本资源；这一阶段对不同对手的实际相对强度尚待确认，不能仅凭升本节奏认定占优。','n-opening',inference=False),
 'middle':stage('五本使用朋友多多是集中启动窗口，但随机牌不保证得到花木兰；缺核心时继续升本会延长空窗。启动回合还要及时处理手牌与转瞬古币，技能收益只有转为场上质量才算战力。','n-opening','n-five-missing','n-time'),
 'late':stage('核心稳住后再升六取得专属强化，配合觉醒和整备资源继续提升；不能把技能参考升本回合当作固定强势期。最终强弱仍取决于核心质量、复生预算及对手威胁。','guide-skills-naonao','wanner-awaken','revive-budget')},
('heluo-huamulan','zhaojun'):{
 'early':stage('',inference=False),
 'middle':stage('需要较早取得花木兰及适合的冻结强化才有启动条件；同阵营进化不保证出核心，因此有条件未满足的空窗。已有持续成长司空震时可保留双输出，不应为照搬双核硬追缺牌。','q-start','q-double'),
 'late':stage('古币复生体系与已有司空震的持续冻结成长可以并行，冻结露娜还可能补循环资源；这些收益受强化与公共牌库限制。双输出也不能代替婉儿觉醒、露娜位置和本轮复生准备。','q-double','q-luna','wanner-awaken','revive-budget')},
('heluo-huamulan','ying'):{
 'early':stage('低压运营需要保血争胜维持等级收益，风险对冲的精简连败开局则承担更高掉血风险；两者不能混用。沉淀收益配资本杠杆偏向积累资源，并不直接代表场上占优，仍要买必要战力。','ying-lowpressure','ying-first-second-skill','ying-capital-timing'),
 'middle':stage('从过渡输出换到花木兰、补婉儿觉醒时有战力衔接风险。空降人才、首购激励等需要匹配来牌与决策条件；逐步替换原有输出，不能为换阵或等复制一次卖空战力。','ying-early-auction','ying-first-second-skill','ying-first-purchase','ying-contract-bottle'),
 'late':stage('体系齐备后，古币出牌循环更容易兑现投资回报，首购可补关键资源；等待淘汰收益或升六仍要先保证自己能存活。决策可能同时帮助对手，资源更多不等于本轮战力必然更强。','ying-return-timing','ying-six-redistribution','ying-resource','revive-budget')}
}


def derive(player,cid,section,text,sources,inference=False):
    evidence=[]
    for source in sources:
        for e in source.get('evidence',[]):
            if e not in evidence:evidence.append(deepcopy(e))
    player['claims'].append({'id':cid,'section':section,'text':text,'condition':'','inference':inference,
        'kind':'general_strategy','version':None,'origin':'editorial','evidence':evidence,
        'derived_from':[claim_id(c) for c in sources]})


def migrate(items):
    items=deepcopy(items);by_id={n['id']:n for n in items};audit={}
    for (nid,bid),stages in STRENGTH.items():
        note=by_id[nid];b=branches.branch(note,bid)
        if 'stage_strength' in b.get('selection',{}):continue
        if note.get('conflicts'):raise ValueError('未解决冲突，暂不覆盖：'+nid)
        before=deepcopy(b.get('selection',{}));b.setdefault('selection',{})['stage_strength']=deepcopy(stages)
        note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'棋手选阵阶段强度整理','previous':{'branch':bid,'selection':before,'revision':note.get('revision')}})
        audit.setdefault(nid,{})[bid]={'stage_strength':deepcopy(stages)}
    for pid in PLAYERS:
        note=by_id[pid]
        if note.get('player_reading_layout',{}).get('version')==1:continue
        if note.get('conflicts'):raise ValueError('未解决冲突，暂不覆盖：'+pid)
        before={k:deepcopy(note.get(k)) for k in ('claims','manual_sections','revision')}
        for c in note['claims']:
            c.setdefault('id',claim_id(c));c['section']=ALIASES.get(c['section'],c['section'])
        note['manual_sections']=list(dict.fromkeys(ALIASES.get(s,s) for s in note.get('manual_sections',[])))
        if pid=='player-zhaojun':
            opening=next(c for c in note['claims'] if c['text'].startswith('开局持续冻结'))
            old=deepcopy(opening)
            opening.update(section='前期思路',text='开局尚未确定最终阵容时，可围绕能够提供经济或保留成长等级的过渡英雄进行冻结；检查冻结转换后的英雄是否仍能承担本轮战力。不同体系采用精简场面或升本的具体时机尚待确认。',inference=True)
            opening['evidence']=[{'source':'BV1aThi6AEAC:p1','start':753.54,'end':834.81}]
            derive(note,opening['id']+'-transfer','适用技巧','需要换下积累等级的过渡英雄时，先保留并使用遗志、传承，将其永久等级转给后续英雄，避免成长留在即将被替换的单位上；高阶大河核心齐备后，无需仅为寻找核心继续冻结。',[old])
            other=next(c for c in note['claims'] if '“七五”' in c['text'])
            other['text']='### 其他已知方向\n\n升华也可用于“七五”阵容，即以七个五品阶英雄为目标的阵容；其完整组成和运营方法尚未整理。'
        elif pid=='player-angela':
            skill=next(c for c in note['claims'] if c['text'].startswith('特制灵异追踪器'))
            derive(note,'player-opening-aircraft','前期思路','尚未定阵时，可先按当前英雄的存活能力和持续作战需要选择飞行器连接对象，让飞行器与目标重合以避免连错。连接英雄存活是持续输出的前提；暂未定阵时无需提前固定最终核心。',[skill],inference=True)
            # The existing full conditional advice remains together; no universal talent ranking.
            next(c for c in note['claims'] if c['text'].startswith('按实际阵容选择奇想'))['section']='前期思路'
        elif pid=='player-yaomei':
            lineup=by_id['yaomei-sacrifice-lixin'];cs={c['id']:c for c in lineup['claims']}
            derive(note,'player-opening-deer-wins','前期思路','需要靠小鹿胜场发育时，前期应同时争取保血和累计胜利，利用已有过渡战力为后续定阵留容错。小鹿的额外等级收益与胜场条件有关，不要在未定阵时就把主动连败当作默认选择；这不代表任何对手都能打赢。',[cs['opening-wins']],inference=True)
            derive(note,'player-opening-deer-opponent','前期思路','需要争取前期胜场时，按对手质量选择过渡英雄：对手较弱、牛魔能够取胜时可补经济；面对同行瑶妹或强势孙尚香时，比较用干将莫邪替代牛魔补即时战力。保留用于后续升本和购买核心的预算，不为凑齐过渡名单刷空金币。',[cs['opening-four'],cs['opening-missing']],inference=True)
        elif pid=='player-ying':
            cs={c['id']:c for c in by_id['heluo-huamulan']['claims']}
            derive(note,'player-opening-lowpressure','前期思路','已经选择低压运营时，优先用现有过渡战力争胜、保住血量，以维持全体等级收益；不要把风险对冲的连败起手套入低压运营。先根据已选战略判断本轮目标，再观察来牌决定最终阵容。',[cs['ying-lowpressure']],inference=True)
            derive(note,'player-opening-capital','前期思路','选择沉淀收益且早期能量充足、能兼顾必要战力时，可比较资本杠杆的存量收益；决策影响全场，可等其他玩家花掉能量后再生效。不能为保利息而不补保命战力，也不能把这一早期条件推广成中后期通用选择。',[cs['ying-capital-timing']],inference=True)
        # Other three players have no independently established undetermined-lineup opening.
        note['player_reading_layout']={'version':1}
        note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'棋手五章节与未定阵开局整理','previous':before})
        audit[pid]={'before_claim_ids':[claim_id(c) for c in before['claims']], 'after_claim_ids':[c['id'] for c in note['claims']]}
    return items,audit


if __name__=='__main__':
    import sys,markdown_sync
    root=Path(__file__).resolve().parents[4];report=root/'raw/reports/player-notes-stages'
    with workspace.store_lock(root,wait=True):
        workspace.recover(root);markdown_sync.scan(root,_locked=True);markdown_sync.assert_clean(root)
        items,audit=migrate(workspace.notes(root));workspace.prepare(root,items)
        report.mkdir(parents=True,exist_ok=True)
        if audit:wxq.atomic_json(report/'migration-map.json',audit)
        if '--apply' in sys.argv:workspace.persist(root,items,_sync=False)
        else:
            for n in items:
                if n['id'] in PLAYERS:wxq.atomic_text(report/'preview'/Path(n['path']).name,wxq.render_note(n,{}))
        print('migrated',len(audit))
