"""Reviewed editorial migration. Preview by default; --apply uses the shared save transaction."""
from copy import deepcopy
from pathlib import Path
import json, re, sys, hashlib
import wxq, workspace, markdown_sync, player_branches as branches, guide_layout as guide

TARGET = 'heluo-huamulan'

HEROES = {
'花木兰': '主C，兼顾前排承伤。全队本回合每使用5张古币为花木兰增加1次复生；花木兰阵亡又通过牺牲提高临时等级，因此古币数量决定能重新作战几次，等级与装备决定每条命能打多少伤害。觉醒：优先，提高牺牲的临时等级；普通花木兰也能启动古币复生。等级投入：优先集中培养，40级轻剑可持续斩击当前目标，100级击败目标后回满法力并继续冲锋，达到节点后仍可继续提高输出与承伤。中期拿到即上场，成型后保留，不把复生次数与英雄等级混为一项投入。',
'上官婉儿': '复生与等级成长的关键挂件。整备给3名不同河洛英雄各使用1张古币，觉醒后覆盖6名；增加全队古币使用张数，为花木兰增加本回合复生次数，也让李白、武则天的古币增级效果多次结算。觉醒：优先；要让一次整备覆盖6名河洛英雄必须觉醒且场上人数足够。等级投入：只作整备工具时无需专门提高，整备人数不随自身等级增长；花木兰装备已齐且有多余法术装备时才考虑补婉儿输出。中期起保留；一般不卖，不为放入其他辅助减少整备覆盖。',
'李白': '古币临时等级挂件，缺花木兰时兼任过渡输出。普通李白让古币额外提供4临时等级，觉醒后为8；把古币交给花木兰可提高她本场的输出和承伤。觉醒：优先，但先确保花木兰到场和上官婉儿覆盖；已经凑齐觉醒时先合成再打古币，不为等重复牌让转瞬古币过期。等级投入：只提高古币收益时无需专门培养李白，自身等级不改变这项加成；暂代输出时再按保血需要投入。顺路拿到即可用于过渡，花木兰到场后仍保留增级功能。',
'武则天': '永久等级成长与产币挂件。在场时增加古币提供的等级，登场取得精致古币；露娜、集体唤醒等让产币与整备继续结算，帮助花木兰积累真实等级并准备复生。觉醒：优先，提高古币增级和登场产币收益，但不能挤占婉儿觉醒与本轮保血资源。等级投入：作为成长工具无需专门提高，古币增益不依赖武则天自身等级。中期取得后保留在循环中；确认最后一轮且全部产币操作结束，才考虑为集中等级收益卖掉，平时不提前拆掉成长体系。',
'程咬金': '整备产币挂件。整备获得古币并对自己使用古币，手中获得的古币再交给花木兰，可补等级与全队用币次数；只获得而未使用的古币不能算入复生次数。觉醒：通常不强求，普通卡可启动；精致古币提高等级收益，有零钱兑换时还会换成更多破损古币，额外用币需求大时提高觉醒优先级。等级投入：自然吃币即可，不分走花木兰的专用等级资源。前期顺路拿一张，中后期保留；不要把他当作钟馗效果必定最快阵亡的承载者，等级高时应另选低等级工具英雄。',
'露娜': '登场触发工具。普通露娜登场随机触发2名英雄整备；场上只有程咬金、上官婉儿两名整备英雄时，可同时补产币与用币，从而增加花木兰的等级和复生次数。觉醒：上述两名目标配置无需强求，不为合成消耗关键打出次数；增加整备目标后再核对覆盖。等级投入：只作登场工具无需专门提高。中期体系就位后再打出，始终预留打出位置；用完按是否还需要唤醒目标决定留场或卖出，手中尽量保留一张可用露娜。缺购买预算时不先卖回公共牌库，避免被同行买走。',
'盾山': '成长阶段的牺牲产币位。阵亡取得古币，手动给花木兰使用后补等级和复生计数。觉醒：通常不强求，普通古币已经有用；有零钱兑换、幸运硬币且需要更多手牌古币时，可比较觉醒取得精致古币的收益。等级投入：不专门培养，需让盾山按计划阵亡取得古币。缺产币组件时上，后期需要对付高等级敌人时可换钟馗；换掉前先确认剩余产币足以支持花木兰，不因到了后期就无条件卖。',
'钟馗': '降级对策位。让自己及左右1格英雄获得降级牺牲，受益英雄阵亡时削减击败者等级，降低花木兰随后要处理的敌人战力；每名受益者每场只触发1次，花木兰反复复生不会无限触发同一份降级。觉醒：不强求，普通卡已有覆盖；对手等级高、核心质量已满足时再考虑更高降级收益。等级投入：主要作用不依赖自身等级，若需要开局钩锁可到10级，不继续抢等级资源。中后期需要降级时上，检查花木兰位于覆盖内；没有降级需求且更缺产币、打出位置时可换下。',
'明世隐': '可选的永久等级成长工具。连最近的花木兰，把她一部分临时等级转为永久等级，登场增加可转化额度，让本轮古币提供的临时战力有一部分能留到以后。觉醒：有足够成长回合和临时等级来源时优先，提高额度与登场增量；不能挤占婉儿和露娜资源。等级投入：只作等级转化工具时不专门培养，转化额度主要看卡牌状态与登场次数。花木兰已有临时等级且有额外位置时上；确认连线，接近终局或位置不足时可以卖，不能挤掉露娜打出位。',
'太乙真人': '可选的复生保护位。开团让最近英雄获得复生，摆在花木兰旁为她增加一次重新输出的机会。觉醒：不强求；需要完美复生提高重新上场的质量且预算允许时再追，不把他当古币循环必需成员。等级投入：只提供开团复生时无需专门提高。后期有额外人口、花木兰仍缺复生时上；挤掉6名河洛覆盖或露娜打出位置时先不用，复生已经充足时可换下。',
'苏烈': '前期主坦和保血过渡。承伤并通过牺牲积累永久等级，40级强化多一次复生，给己方输出争取时间，减少找到花木兰前的棋手掉血。觉醒：不强求，前期普通卡能完成承伤，不为重复牌耽误棋手5级启动。等级投入：自然成长为主，不专门追40级而挤占花木兰预算。开局拿到且能改善战力时上；花木兰和体系英雄能接管战斗、需要腾人口时卖，不一次卖空仍有作用的前排。',
'李元芳': '前期古币成长挂件。整备给最近河洛英雄使用古币，建议靠近苏烈，用古币提升苏烈坦度，降低过渡掉血；每次调整站位后检查实际目标。觉醒：不强求，普通古币足以过渡，精致古币收益不应耽误棋手5级买核心。等级投入：只作整备工具无需专门提高。开局与苏烈配合，有花木兰、上官婉儿等体系英雄接管后可卖，释放人口和资源。',
'弈星': '棋手升级的经验挂件。棋手升级时普通卡补2经验，觉醒补4经验，加快取得高品阶英雄与技能的节奏，间接让花木兰体系更早成型。觉醒：无需专门追，重复牌成本应与升级收益比较。等级投入：不为经验功能投入英雄等级。精简开局可上场，升到目标棋手等级或需要补保血战力、腾人口时卖；不能长期只上弈星承受连续大幅掉血。',
'牛魔': '前排和胜场经济过渡位。承伤并通过凯旋取得能量，能取胜时把当轮战力转成寻找花木兰、棋手升级的资源。觉醒：不强求，普通卡已能取得凯旋收益，不为追收益强补重复牌。等级投入：前期自然成长为主，不抢核心培养资源。补一张就有机会取胜时上；明显打不过时不为凯旋继续买牌，体系接管或人口紧张时可卖。',
'李信': '缺花木兰时的过渡输出。用已有牺牲成员和可承接的装备提供当轮战力，减少持续刷新却没有有效输出造成的掉血。觉醒及等级投入：以能否立即保血为准，不为培养完整李信体系耗尽花木兰启动预算；该用途没有统一等级停点。中期花木兰迟迟不来时上，花木兰已能接管输出后逐步换下并转移可用装备。',
'司空震': '昭君有条件保留的第二输出。冻结及同名变化提高其真实等级，其他英雄获得临时等级时还能继承一定收益；100级强化可在开战时进入雷霆之王，增加全场伤害与持续输出。觉醒：已有持续成长且不影响花木兰体系时优先，提高临时等级继承比例和上限。等级投入：作为第二输出可继续提高真实等级，突破继承上限与技能节点，不作低等级工具处理。已有花木兰和持续冻结成长条件时上，不额外硬追；不能继续成长或挤占古币循环时重新比较去留。',
}

PROCUREMENT = {
'花木兰':'拿到首张即买，后续核心觉醒和等级资源优先投入；同时保留本轮古币操作预算。',
'上官婉儿':'顺路即买并留重复牌，优先补觉醒，不为其他挂件重复牌耗尽预算。',
'李白':'先拿一张，花木兰与婉儿需求满足后再追觉醒；已有零钱兑换时提高重复牌优先级。',
'武则天':'拿首张补体系，预算允许再补觉醒；不挤占婉儿及本轮保血资源。',
'程咬金':'顺路先拿一张，通常不专搜觉醒；有零钱兑换且需要手牌古币时再提高投入。',
'露娜':'体系就位后按本轮需要买并预留后续用量，保留购买、打出位置；两名整备目标时不强追觉醒。',
'盾山':'缺产币时拿一张，不挤占花木兰与婉儿预算；精致古币联动齐备后再比较觉醒。',
'钟馗':'需要降级时买一张，普通先用；觉醒投入服从核心质量与对手等级。',
'明世隐':'仅有成长空间和额外位置时购买；不为专搜明世隐影响核心和露娜投入。',
'苏烈':'能改善前期保血时买，不付费搜齐重复牌或专门追觉醒。',
'李元芳':'自然商店或技能顺路拿，用一张过渡，不专门搜觉醒。',
'弈星':'顺路拿一张帮助升级，不专搜、不追觉醒。',
'牛魔':'补一张有机会取胜时买，不为追凯旋收益专搜觉醒。',
'司空震':'已有冻结成长条件时保留，觉醒和等级投入不能挤掉花木兰体系。',
}

OPERATIONS = {
'ming':[
'开局至第一轮拍卖以弈星精简过渡，补牛魔后确有机会取胜才买；优先卦象·节，第一轮拍卖后再用一次，收益结算后争取在第6—7回合进入棋手5级。程咬金、李白顺路各拿一张，上官婉儿可留重复牌，不付费搜齐过渡阵容；若持续大幅掉血，就补能承接装备的李信或李白，不能只挂弈星继续升级。',
'进入棋手5级后改用卦象·丰集中找花木兰、上官婉儿，先让李信或李白保血再逐步换成古币体系；免费刷新与付费刷新都要保留买牌和本轮操作资源。优先婉儿觉醒，场上保留6名有效河洛英雄并给露娜留打出位置；可留5级继续补质量，升级到6级的方案须确认当轮能活、升级后仍买得起缺牌，不设统一等待回合或血量门槛。',
'体系启动后逐轮观察对手再投入露娜与整备牌，复生已经够用时存牌，可能被淘汰时立即补战力；不要为了省下轮资源输掉本轮。需要高品阶牌且升级后仍有买牌预算时才升棋手6级，否则在5级补花木兰、婉儿觉醒和露娜；决赛根据敌人等级考虑盾山换钟馗，换入工具位不能破坏河洛人数和露娜位置。',
],
'zhuang':[
'开局至棋手4级先比较保血和精简过渡：苏烈、李元芳能稳住时保留，补牛魔有机会取胜才买；补了也难赢时用李元芳、弈星节省资源。程咬金、李白顺路各拿一张，婉儿可留重复牌，不付费搜齐无用河洛英雄；优先保留棋手5级启动如梦似幻及后续买牌的钱，连续掉血接近淘汰时先补即时战力。',
'棋手5级第一次如梦似幻按实际有用河洛英雄选择3名或5名方案，不为人数塞无用牌；缺花木兰时可用李信或李白保血。有首张花木兰、李白与古币暂时能稳住后再存钱升6级。另有至少4名河洛、婉儿外延后合成、约第12—13回合到6级再如梦合成的路线，只在能承受等待并保留买牌预算时考虑，不把它混成3名／5名方案的共同门槛。',
'到棋手6级后按缺口使用第二次如梦似幻：体系齐时可按7名河洛补觉醒，缺李白、上官婉儿、武则天时可按6名继续补体系。准备梦幻商店找露娜时先补其他英雄觉醒，再放未觉醒露娜，并确认公共牌库仍有库存；后续梦幻引擎还要求低血量及当轮战败，不能把未来触发当本轮保命。局面稳定则存露娜和整备牌，遇强敌及时使用。',
],
'naonao':[
'第1—3回合用苏烈、李元芳配合保血，顺路补牛魔、弈星取得经济，不花能量刷新找齐；第4—7回合攒升级资源，先升棋手等级再用派对牌找相应品阶英雄。经济天赋须能实际兑现，战力不足时先保血；商店顺路出现唤醒、临阵磨枪、古币多多和全军动员可预留，但不能买到没有棋手5级启动的钱。',
'参考第8回合进入棋手5级使用朋友多多，先确认奖励品阶覆盖花木兰；开完仍缺花木兰时可多留一回合用免费刷新补核心。花木兰、上官婉儿、李白、武则天和露娜按缺口购买，优先婉儿觉醒，零钱兑换时再重视李白及程咬金、盾山的觉醒；用体系英雄逐步换掉低品阶过渡牌，提前留操作时间，转瞬古币当回合用完，不能把朋友多多当成必出花木兰。',
'核心能稳住后参考第10回合升棋手6级拿专属强化，不能为了赶回合让升级挤掉本轮战力。此后优先补花木兰永久等级、李白觉醒及露娜，零钱兑换产生的破损古币不直接提供等级；先把足够古币用于花木兰，余币才考虑古币机。第12回合以后按对手强度决定存牌或投入，囤露娜、唤醒、集体唤醒、临阵磨枪、全军动员，确认终局再集中使用。',
],
'zhaojun':[
'前期尚无足够依据给出统一的回合表或完整购买名单，以实际取得的英雄保血；若已有同阵营向上变化强化，可用有用河洛英雄冻结尝试较早获得花木兰，拍卖也可补核心，但变化并不保证命中。没有较早取得花木兰的条件时保留已有高品阶战力，不额外照搬其他棋手的固定开局。',
'棋手5级且花木兰、古币配套已到手后，围绕上官婉儿觉醒、李白、武则天和露娜补牌，给露娜预留打出位置；已有持续冻结成长的司空震可保留第二输出，不为照搬双输出额外硬追。付费刷新投入、5级停留回合和准确升级边界尚缺可靠说明，先保证当前阵容能保血，不挪用其他棋手时间表。',
'后期逐轮按对手战力配置花木兰复生，稳定时存露娜与整备牌，遇淘汰风险先投入当轮；升棋手6级前检查现有高品阶战力和升级后的买牌预算，没有统一6级时点或必选技能。冻结露娜补牌仍受强化与公共牌库限制；司空震保留时继续检查其真实等级与输出，不能把双输出成员和基础古币成员合并为无条件必带名单。',
],
'ying':[
'开局先选战略再打英雄，按低压运营、固定收益、沉淀收益或风险对冲分别执行。棋手1—4级的低压路线用苏烈、李元芳等保血争胜，可配乘胜追击；风险对冲可选精简弈星开局，不能把主动连败套到低压路线。沉淀收益配资本杠杆只在早期能量充足时考虑，并观察其他玩家是否已花掉能量；过渡购买服从棋手5级找核心预算，没有各级固定停留回合。',
'棋手5级围绕花木兰、上官婉儿和露娜补缺，空降人才优先补婉儿，再按来牌补花木兰或李白；决策会影响全场，开放找牌与资源前先看同行和公共牌库。首购复制已可用时，每回合先买武则天、露娜或关键效果牌；首购用过可在能承受等待时锁店留到下回合。找牌与升级仍须保留当轮购买和保血资源，不为了复制或利息等到被淘汰。',
'准备升棋手6级选择资源再分配时，检查是否有人接近淘汰以及自己能否活过本轮，不能把他人未来淘汰当即时保命资源。取得收益后补花木兰、婉儿质量和露娜循环；投资回报须满足真实出牌条件且奖励随机。对手可能一轮内完成大幅成长时，等其关键操作后再判断复生投入，稳定时存牌，确认终局才拆成长工具集中花木兰等级。',
],
}

EQUIPMENT = {
'无尽巨剑': ('crit-basic','给花木兰提高暴击伤害，与凝渊一起补输出；先保证能够行动和接近目标，再增加伤害，不为第二件重复计算不可叠加的暴击效果。'),
'凝渊': ('crit-basic','给花木兰叠暴击并在达到100%暴击率后追击远程敌人；没有达到触发条件时不能当成常驻加速。面对治疗护盾可比较制裁之剑，已有破妄之刃时再重新比较是否需要保留凝渊。'),
'炽热支配者': ('crit-basic','给花木兰应对开局控制，争取轻剑启动；对手控制少时可比较反伤重甲等输出或对策装。15秒免控不等于全场免控，也不覆盖压制。'),
'反伤重甲': ('ying-equipment-dispute','给花木兰对付嬴政等持续攻击者；控制少且仍需凝渊追击时换第三件装备，仍需解控而追击压力小时可换凝渊。对方强吸血时重新比较收益，没有固定替换位置。'),
'极寒风暴': ('ailin-chase','给花木兰对付艾琳的远程普攻减速和风筝，与凝渊配合冻结后追击；对手带炽热支配者时等实际免控结束，不能把其他免控一律当15秒。'),
'制裁之剑': ('antiheal','敌方治疗或护盾收益明显时给花木兰，可替换凝渊；换装前检查失去追击是否会更难接近敌人，不无条件当基础装备。'),
'魂灭灵冠': ('artifact-choice','优先给花木兰，把她反复阵亡转成敌人最大生命值伤害；适合能保证多次复生并进入敌群的局面，仍要保留足够复生资源。'),
'机器头': ('machine-tyrant-tradeoff','可给花木兰解决负面效果并提高伤害；已有暴君归来时慎选，固定攻速会限制复生后的攻速收益，不能把两者加成都完整计入。'),
'百锻刀': ('late-scaling-equipment','花木兰较早取得且能不断击败英雄时可养成；无法拆卸，决赛才拿不能假设已有击败积累，临近终局先看即时收益。'),
'捕能手套': ('capture-glove-resource','给能稳定完成击败的花木兰补后续买牌资源；单回合击败至少5名英雄取得能量转换后，转换仍花3能量，锦囊不保证给露娜或唤醒。缺即时战力时先比较魂灭灵冠等装备。'),
'磐石之心': ('anti-burst','面对高爆发孙悟空等可能瞬间击败花木兰的敌人时考虑，限制单次受伤以增加行动时间；占装备位会少输出，应同时检查能否击败敌方核心。'),
'红魔': ('red-demon-underworld-choice','花木兰独自进入敌群、需要提高伤害时考虑；敌方以法术伤害为主时，比只增加物防的冥王更切合伤害需求，周围有友军则不能计入独处加成。'),
'冥王': ('red-demon-underworld-choice','花木兰进入多个物理敌人附近时可同时补物防与攻击；按周围1格实际敌人数计算，不固定认定50或60物防，法术威胁不能靠这部分物防解决。'),
'破妄之刃': ('sword-replaces-chase','给花木兰补追击和真实伤害；已经取得后，可按敌人威胁重新比较凝渊位置，不能在没有替代追击手段时先卖凝渊。'),
'名刀·司命': ('sword-replaces-chase','已有破妄之刃承担追击、又需防止花木兰首次被瞬间击败时，可比较替换凝渊；它只保护首次致命伤，不能按每次复生重复计算。'),
'青莲剑谱': ('avoid-qinglian-replacement','不推荐用于依赖轻剑持续斩击的花木兰，它会替换原技能，两套技能收益不能同时获得；不要只看暴击率就替换。'),
}

TALENT_REASONS = {
'暴君归来': ('talent-core','花木兰每次复生后可在短窗口内继续输出，核心已启动并能保血时优先；它不负责生成复生次数。'),
'零钱兑换': ('n-small-change','需要更多古币使用张数时选，尤其适合闹闹；破损古币不提供原本的永久等级，要有李白补临时战力，并另补花木兰真实等级。'),
'幸运硬币': ('n-coins-manual','手里有可打出的古币时放大收益，配合程咬金、盾山或武则天产出的手牌使用；自动整备使用古币不能一律按额外触发计算。'),
'古币机': ('coin-machine','有余币才投入，优先比较前两次固定收益；花木兰本轮战力不足时先给花木兰用币，不能把随机超速成长或能量当保证。'),
'泉水': ('ming-survival-talents','找花木兰期间需要恢复棋手生命值、增加继续找牌的回合时考虑；满血改为经验，不能把它当英雄回复。'),
'防御领域': ('ming-survival-talents','预计过渡要输、需要减少棋手掉血时考虑；不能代替补李信、李白等当轮战力。'),
'存款利息': ('ming-survival-talents','能保血且确有能量结余时选经济收益；为了利息不买必要战力，会减少找到花木兰的容错。'),
'群星璀璨': ('transition-talents','可用兑换券补高品阶英雄并帮助保血；总共至少5名4—5品阶英雄才有全体临时等级收益，不能只凭花木兰一名满足条件。'),
'虚构武装': ('transition-wuzhuang','过渡战力不足时用装备与生命上限保血；随机目标不保证命中花木兰，阵容接管前不立刻卖掉仍在承接收益的英雄。'),
'三十而达': ('zhuang-talent-speed','能在备战阶段达到总等级30的门槛时，经验可加快棋手升级；差得很远又急需保血时不只看后续收益。'),
'崛起': ('zhuang-talent-speed','需要马可波罗、百里守约提供当轮过渡输出时比较，并检查共战和胜场条件；不要为了养过渡英雄拖慢花木兰体系启动。'),
'钱生战力': ('zhuang-talent-speed','后续会大量使用古币时，给河洛英雄补临时战力；从选中后开始计数，不能把之前用币全算进去，随机4名也不保证花木兰每次获益。'),
'王牌部队': ('zhuang-ace-army','场上至少3名4—5品阶英雄时可持续补高品阶锦囊，缓解露娜与整备资源缺口；锦囊随机，不保证集体唤醒或全军动员。'),
}

def clean(text):
    text=text.replace('以上投入取舍按当前职责与普通／觉醒机制推导。','').replace('按古币使用张数与卡面增益推导：','').replace('这是资源取舍推导，','')
    for a,b in [('棋手等阶','棋手等级'),('目标等阶','目标品阶'),('对应等阶英雄','对应品阶英雄'),('对应的等阶','对应的品阶')]:text=text.replace(a,b)
    text=re.sub(r'([一二三四五六])阶',lambda m:m[1]+'级',text)
    return text.replace('升阶','升级').replace('本数','棋手等级').replace('本分支没有已核实的','没有已确认的').replace(' 原条件说明：',' ').replace('本批完整体系','完整体系').replace('材料参考','参考节奏为').replace('第7回合是材料中的找牌节奏','可参考第7回合开始找牌').replace('现有材料缺少同等配置的定量比较','同等配置下两种选择的收益尚无明确比较').replace('材料中的普通装备','普通装备').replace('尤其适合闹闹；','在古币张数不足时价值更高；')

def migrate(items, root):
    items=deepcopy(items); note=next(n for n in items if n['id']==TARGET)
    if note.get('reading_layout',{}).get('version')==4:return items,{}
    before=deepcopy(note)
    cards=json.loads((root/'knowledge/cards/index.json').read_text('utf8'))['cards']
    entities=wxq.entities(root)
    byname={}
    for c in cards:byname.setdefault(c['name'],[]).append(c)
    old={c['id']:deepcopy(c) for c in note['claims']}
    layout=note['reading_layout'];layout.update(version=4,supporting_claim_refs={})
    old_projections={b['id']:branches.project(before,b['id']) for b in before['meta']['player_branches']}
    def support(ref,summary):
        values=layout['supporting_claim_refs'].setdefault(ref,[])
        if summary not in values:values.append(summary)
    def add(cid,section,text,refs,owner='common',snapshots=(),loc=None,hide=True):
        refs=list(dict.fromkeys(x for x in refs if x in old))
        evidence=list({json.dumps(e,sort_keys=True):deepcopy(e) for r in refs for e in old[r].get('evidence',[])}.values())
        c={'id':cid,'section':section,'text':clean(text),'condition':'','version':None,'kind':'general_strategy','inference':True,'evidence':evidence,
           'derivation':{'claim_refs':refs,'card_snapshots':deepcopy(list(snapshots)),'reason':'基于已有教学与本地卡面整理具体机制及操作，不作为来源直接引文'}}
        note['claims'].append(c)
        target=note['meta'] if owner=='common' else next(b for b in note['meta']['player_branches'] if b['id']==owner)
        target['common_claim_refs' if owner=='common' else 'claim_refs'].append(cid)
        layout['claim_locations'][cid]=loc or [section]
        if hide:
            for ref in refs:support(ref,cid)
        return cid
    def card(name,category):return next(c for c in byname[name] if c['category']==category)
    # Preserve source text and source IDs. Active wording is normalized, never the raw transcript.
    for c in note['claims']:
        c['text']=clean(c['text']);c['condition']=clean(c.get('condition',''))
    for field in ('assessment','selection','operation_routes','matchups','ban_conditions'):
        def normalize(value):
            if isinstance(value,str):return clean(value)
            if isinstance(value,list):return [normalize(x) for x in value]
            if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
            return value
        if field in note['meta']:note['meta'][field]=normalize(note['meta'][field])
        for b in note['meta']['player_branches']:
            if field in b:b[field]=normalize(b[field])
    # Complete hero profiles use actual member sets, not all heroes mentioned in source text.
    for b in note['meta']['player_branches']:
        projection=old_projections[b['id']]; names=note['entity_names']
        members={m['hero'] for rows in projection['meta']['compositions'].values() for m in rows}
        for v in projection['meta'].get('late_variants',[]):members.update(m['hero'] for m in v['members'])
        nameset={names.get(h,h) for h in members}|{'太乙真人'}
        if b['id'] in ('ming','zhuang'):nameset.add('李信')
        if b['id']=='zhaojun':nameset.add('司空震')
        refs=['hero-quality-'+b['id'],'coin-loop','wanner-awaken','shared-late-tools','mingshiyin-optional','mulan-skill-breakpoints']
        for name in HEROES:
            if name not in nameset:continue
            snapshots=[c for c in byname.get(name,[]) if c['category']=='heroes']
            add('v4-hero-'+b['id']+'-'+hashlib.sha256(name.encode()).hexdigest()[:8],'英雄','**'+name+'：** '+HEROES[name],refs,b['id'],snapshots,hide=False)
        support('hero-quality-'+b['id'],next(c['id'] for c in note['claims'] if c['id'].startswith('v4-hero-'+b['id'])))
    # Stage member metadata becomes the purchase list; full mechanisms live in hero claims.
    def purchase(rows):
        for m in rows:
            name=note['entity_names'].get(m['hero'],m['hero'])
            m['role']=PROCUREMENT.get(name,'按当前缺口顺路购买，不挤占花木兰与上官婉儿预算。')
            m['replacement_note']=''
    for rows in note['meta']['compositions'].values():purchase(rows)
    for b in note['meta']['player_branches']:
        for rows in b.get('overrides',{}).get('compositions',{}).values():purchase(rows)
    for v in note['meta'].get('late_variants',[]):purchase(v['members'])
    for b in note['meta']['player_branches']:
        bid=b['id'];projection=old_projections[bid]
        for i,(stage,title) in enumerate(guide.STAGES.items()):
            refs=[c['id'] for c in projection['claims'] if guide.location(before,c)==['阵容组成与运营节奏',title]]
            # Route prose lives inside the compact stage rather than a second route block.
            if stage=='early':refs += [c['id'] for c in projection['claims'] if c['section']=='运营路线选择']
            summary=add('v4-operation-'+bid+'-'+stage,'前中后期运营',OPERATIONS[bid][i],refs,bid,loc=['阵容组成与运营节奏',title])
            for route in note['meta'].get('operation_routes',[]):
                if route['id'] in b.get('operation_route_ids',[]):route['phases'][stage]=[summary]
        from overview import default_overview
        overview=deepcopy(projection['meta'].get('overview') or default_overview(projection['meta']))
        for preset in overview['presets']:
            for stage in guide.STAGES:
                preset['stages'][stage].update(description='',claim_refs=['v4-operation-'+bid+'-'+stage])
        b.setdefault('overrides',{})['overview']=overview
        refs=[c['id'] for c in projection['claims'] if guide.location(before,c)==['阵容组成与运营节奏','后期提升思路']]
        text='成型后先检查上官婉儿觉醒与河洛人数，再把等级资源集中给花木兰，争取40级、100级轻剑节点；补李白、武则天觉醒分别提高临时和永久等级收益。已经能赢当轮时存露娜与唤醒、整备牌，不把额外复生堆到用不完；需要降级再考虑钟馗，有额外人口才考虑太乙真人。'
        text += {'ming':'棋手6级只在不损失当轮保血和买牌能力时考虑，没有统一必选的6级技能。','zhuang':'第二次如梦和梦幻商店优先补真实缺口，不让无用过渡英雄分走机会。','naonao':'棋手6级专属强化按古币联动选择；零钱兑换时补花木兰真实等级，余币再投入古币机。','zhaojun':'已有持续冻结成长的司空震时继续提高其真实等级，强化第二输出；冻结露娜仍先核对牌库。','ying':'用首购复制武则天、露娜或关键效果牌，投资回报满足出牌要求后再期待随机资源，不能假定必回指定牌。'}[bid]
        add('v4-improvement-'+bid,'成型后提升思路',text,refs+['hero-quality-'+bid,'reserve-resources'],bid,loc=['阵容组成与运营节奏','后期提升思路'])
    # Explain every key equipment separately and use actual sourceCards for recipes.
    for name,(ref,reason) in EQUIPMENT.items():
        c=card(name,'equipment'); ent=next(e for e in entities if e['id']==c['id'])
        sources=ent.get('properties',{}).get('sourceCards',[])
        basic=[s['name'] for s in sources if (s.get('equipCard') or {}).get('atlasSubTypeName')=='基础装备']
        talent=[s['name'] for s in sources if s.get('type')==6]
        if basic:origin='来源：把基础装备'+ '、'.join(basic)+'穿戴给英雄后铸造获得。'
        elif name in ('魂灭灵冠','破妄之刃'):origin='来源：选择同名天赋取得，不由基础装备铸造。'
        else:
            channel=ent.get('properties',{}).get('cardGetDesc','')
            origin=('来源：'+re.sub(r'^来源[:：]\s*','',channel)+' 不由基础装备铸造。') if channel else '具体获取渠道尚未确认，不猜合成配方。'
        refs=[ref]
        if name in ('无尽巨剑','凝渊','炽热支配者'):refs+=['artifact-choice']
        owner='ming' if ref=='red-demon-underworld-choice' else 'common'
        add('v4-equipment-'+c['id'].split(':')[1],'推荐装备','**'+name+'：** '+c['effect']+' '+origin+reason,refs,owner,snapshots=[c,ent],hide=False)
    for ref in [c['id'] for c in before['claims'] if guide.location(before,c)==['推荐装备']]:
        # Variant-specific recommendations stay visible in their original section where appropriate.
        relevant=[name for name,(r,_) in EQUIPMENT.items() if r==ref]
        if relevant:
            for name in relevant:support(ref,'v4-equipment-'+card(name,'equipment')['id'].split(':')[1])
        elif ref in ('artifact-choice','crit-basic'):support(ref,'v4-equipment-644110')
    # Only inherit talent choices documented for this player; shared choices remain shared.
    for b in note['meta']['player_branches']:
        bid=b['id'];projection=old_projections[bid];available={c['id'] for c in projection['claims']}
        choices=['暴君归来','零钱兑换','幸运硬币']
        if bid=='ming':choices+=['泉水','防御领域','存款利息','群星璀璨','虚构武装']
        if bid=='zhuang':choices+=['三十而达','崛起','钱生战力','王牌部队','古币机']
        if bid=='naonao':choices+=['存款利息','钱生战力','王牌部队','古币机']
        refs=[c['id'] for c in projection['claims'] if guide.location(before,c)==['推荐天赋']]
        intro='没有所有对局都必须拿的单一天赋。过渡会大幅掉血时先选能立即保命或补战力的收益，核心已能稳住后优先暴君归来等复生输出，再比较零钱兑换、幸运硬币的古币收益；经济选择不能挤掉本轮买核心和操作的钱。'
        intro+={'ming':'例如泉水、防御领域增加找牌容错，虚构武装、群星璀璨补即时战力；有能量结余才看存款利息。','zhuang':'需要升级且能达到总等级门槛时看三十而达；需要保血时比较崛起，后期大量用币可看钱生战力，英雄品阶与人数够时看王牌部队补资源。','naonao':'前期能保血时可用存款利息加快升级，后期钱生战力补等级、王牌部队补锦囊；古币机排在花木兰即时用币之后。','zhaojun':'冻结双输出也先保证花木兰的复生与司空震的成长，不为某个天赋强行增加第二输出。','ying':'先与当前战略、至高决策带来的收益比较；全场资源可能同时强化同行，不把自己的额外资源视为独享。'}[bid]
        intro+='没有已确认的通用人口天赋必选项，不为多放辅助牺牲古币核心的当前战力。'
        add('v4-talents-'+bid,'推荐天赋',intro,refs,bid)
        for name in choices:
            c=card(name,'talents');ref,reason=TALENT_REASONS[name]
            supporting=[ref] if ref in available else refs or ['talent-core']
            add('v4-talent-'+bid+'-'+c['id'].split(':')[1],'推荐天赋','**'+name+'：** '+c['effect']+' '+reason,supporting,bid,[c],hide=False)
    # Existing effect claims retain IDs and acquire exact card effects with internal snapshots.
    for cid,name in [('wake-targets','唤醒'),('hold-coin-effect','古币多多'),('enter-before-prep','集体唤醒'),('wake-targets-card-2','临阵磨枪'),('enter-before-prep-card-2','全军动员'),('zhuang-high-talent','高级人才')]:
        claim=next(c for c in note['claims'] if c['id']==cid);c=card(name,'effect-cards')
        body=re.sub(r'^- \*\*[^*]+：\*\*\s*','',claim['text'])
        claim['text']='**'+name+'：** '+c['effect']+' '+body
        claim['card_snapshots']=[deepcopy(c)]
    for b in note['meta']['player_branches']:
        available={c['id'] for c in old_projections[b['id']]['claims']}
        if 'third-auction' in available or 'ying-auction-buy-budget' in available:
            for name,reason in [('天籁琴音','花木兰、婉儿等关键英雄还没觉醒时优先比较，按缺口分配妙音；不为拍下它耗尽当轮买牌和保命资源。'),('展翅腾飞','需要集中找露娜或核心重复牌时用；优先留到能量足够购买、也有操作时间的回合，免费刷新不能代替购买预算。')]:
                c=card(name,'effect-cards');ref='third-auction' if 'third-auction' in available else 'ying-auction-buy-budget'
                add('v4-effect-'+b['id']+'-'+c['id'].split(':')[1],'关键效果牌','**'+name+'：** '+c['effect']+' '+reason+' 没有固定竞价上限，按剩余资源取舍。',[ref],b['id'],[c],hide=False)
    # The old two version paragraphs state the same 4/5-coin distinction.
    support('newer-five','historical-four')
    # These decisions are not fully represented by compact stage/talent summaries.
    for cid in ('find-luna-alternatives','luna-recycle','luna-elimination-pool','luna-awakening-context'):
        layout['supporting_claim_refs'].pop(cid,None)
        layout['claim_locations'][cid]=['关键牌判断']
    for cid,name in [('ying-boming-tradeoff','搏命'),('ying-contract-bottle','契约瓶')]:
        layout['supporting_claim_refs'].pop(cid,None)
        layout['claim_locations'][cid]=['推荐天赋']
        claim=next(c for c in note['claims'] if c['id']==cid)
        choices=byname.get(name,[])
        effect=choices[0]['effect'] if choices else '具体效果尚待确认。'
        claim.update(text='**'+name+'：** '+effect+' '+claim['text'],card_snapshots=deepcopy(choices))
    # Coverage was reviewed against the new wording; explicit source gaps remain partial/missing.
    by_id={c['id']:c for c in note['claims']}
    for b in note['meta']['player_branches']:
        rows=layout.get('coverage',{}).get(b['id'],{})
        for stage in guide.STAGES:
            cid='v4-operation-'+b['id']+'-'+stage
            rows[stage+'.operation']={'status':'partial' if b['id']=='zhaojun' else 'covered','claim_refs':[cid], 'detail':'准确回合和预算未确认时按实际条件处理' if b['id']=='zhaojun' else ''}
        for row in rows.values():
            if isinstance(row,dict):row['claim_hashes']={cid:guide.claim_hash(by_id[cid]) for cid in row.get('claim_refs',[]) if cid in by_id}
    note.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'英雄独立、运营单段、逐卡机制与投入、拍卖合一；用户授权允许有据推导','previous':before})
    return items,{'before_claim_ids':list(old),'after_claim_ids':[c['id'] for c in note['claims']],'supporting_claim_refs':layout['supporting_claim_refs']}

def main():
    root=Path(__file__).resolve().parents[4];report=root/'raw/reports/heluo-teaching-v4'
    with workspace.store_lock(root,wait=True):
        workspace.recover(root);markdown_sync.scan(root,_locked=True);markdown_sync.assert_clean(root)
        original=workspace.notes(root)
        report.mkdir(parents=True,exist_ok=True)
        if not (report/'before.json').exists():wxq.atomic_json(report/'before.json',{'notes':original})
        items,audit=migrate(original,root)
        workspace.prepare(root,items)
        note=next(n for n in items if n['id']==TARGET)
        for path,text in branches.documents(note).items():
            dest=report/'preview'/Path(path).name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf8')
            b=next(b for b in note['meta']['player_branches'] if branches.document_path(note,b)==path)
            assert branches.parse_document(text,note,b['id'])==guide.initial_sections(note,b['id'])
        if audit:wxq.atomic_json(report/'audit.json',audit)
        wxq.atomic_json(report/'replay.json',{'notes':[note]})
        if '--apply' in sys.argv and audit:
            if items!=original:workspace.persist(root,items,_sync=False)
            changed={n['id']:n for n in items if next((o for o in original if o['id']==n['id']),None)!=n}
            changed.setdefault(TARGET,note)
            for path in (root/'knowledge/replays').glob('*.json'):
                data=wxq.read_json(path,{})
                if not isinstance(data,dict) or not isinstance(data.get('notes'),list):continue
                prior=deepcopy(data)
                data['notes']=[deepcopy(changed.get(n['id'],n)) for n in data['notes']]
                if data!=prior:wxq.atomic_json(path,data)
            wxq.atomic_json(root/'knowledge/replays/河洛花木兰教学提质-2026-10-20.json',{'notes':list(changed.values())})
        print('applied' if '--apply' in sys.argv else 'preview',len(note['claims']),'claims',len(note['meta']['player_branches']),'branches')

if __name__=='__main__':main()
