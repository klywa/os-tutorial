"""Reviewed, one-time schema4 to schema5 migration. Does not collect sources."""
from copy import deepcopy
from pathlib import Path
import argparse,re
import wxq,workspace,player_branches as branches

PLAYERS={'ming':('player:39','明先生'),'zhuang':('player:31','庄小鱼'),'naonao':('player:40','闹闹'),'zhaojun':('player:34','昭君'),'ying':('player:43','嬴律'),'yaomei':('player:11','瑶妹'),'angela':('player:51','安琪拉')}
COMMON=[0,1,2,3,4,21,22,23,24,25,26,27,28,29,30,31,32,34,35,37,38,39,52,53,54,55,56,63,70,75,77,78,79,80,81,83,86,87,89,90,91,93]
OWNERS={
 'ming':[7,33,42,58,59,62,69,84,85,88,92],
 'zhuang':[5,6,8,9,10,36,40,43,57,64,65,66,67,68,69,82],
 'naonao':[11,12,13,14,15,60,61,62],
 'zhaojun':[16,17,18],
 'ying':[19,20,41,44,45,46,47,48,49,50,51,71,72,73,74,76]}

def assessment(dimension,text,refs):return {'dimension':dimension,'text':text,'claim_refs':list(refs),'inference':True}

def new_branch(key,claims):
 player,name=PLAYERS[key]
 return {'id':key,'player':player,'name':name,'claim_refs':claims,'condition_refs':[],
         'operation_route_ids':[],'late_variant_ids':[],'major_variant_ids':[],'overrides':{},'assessment':[]}

def classify_section(c,common=False):
 s=c['section']
 if common:return '核心机制' if s in ('核心机制','版本差异','尚待裁决') else '共通操作与对局原则'
 if s in ('核心机制','运营路线选择','主要变阵','禁用阵营适用情况'):return '采用条件与优势短板'
 if s=='阵容组成':return '中期启动'
 if '前期' in s:return '前期运营'
 if '中期' in s or s in ('关键牌判断','关键操作顺序'):return '中期启动'
 if '拍卖' in s:return '三轮拍卖'
 if s in ('推荐天赋及原因','推荐装备','站位技巧'):return '天赋、装备与站位'
 if s in ('克制手段','战后复盘','操作时间不足') or s.startswith('针对对手'):return '对局应对与战后复盘'
 if s in ('路线与装备取舍','条件与待裁决'):return '中期启动' if c['id'] in ('ming-six-dispute','zhuang-opening-dispute','zhuang-delayed-dispute','ming-wakeup-conflict') else '天赋、装备与站位'
 return '后期提升'

def heluo(note):
 old=deepcopy(note['claims']);assert len(old)==94 and old[0]['id']=='coin-loop' and old[93]['id']=='enter-before-prep'
 ids=lambda numbers:[old[i]['id'] for i in numbers]
 meta=note['meta'];meta['common_claim_refs']=ids(COMMON)
 meta['player_branches']=[new_branch(k,ids(v)) for k,v in OWNERS.items()]
 byid={c['id']:c for c in note['claims']}
 byid['ming-six-dispute']['text']='明先生有留棋手五阶持续刷新与将棋手升至六阶两种方案。留棋手五阶时把资源投入花木兰、上官婉儿及过渡战力，适合希望集中买牌、继续补体系的局面；将棋手升至六阶可改善后续找高阶牌的机会，但会占用当轮购买战力的资源。核心迟迟不来时也有将棋手升至六阶继续寻找的路线。先检查当轮能否保血及棋手升级后是否仍有买牌预算；现有材料不足以给出统一的血量、能量或等待回合边界。'
 byid['ming-five']['text']=byid['ming-five']['text'].replace('默认棋手五阶持续刷新','棋手五阶持续刷新').replace('见“路线与装备取舍”','见本棋手中期启动中的两种方案')
 byid['third-auction']['text']=byid['third-auction']['text'].replace('闹闹与明先生材料中，','').replace('本批统一出价表','统一出价表')
 byid['missing-mulan']['text']=byid['missing-mulan']['text'].replace('明先生或庄小鱼在','在')
 byid['luna-recycle']['text']=byid['luna-recycle']['text'].replace('等准备刷新，或庄小鱼准备使用梦幻商店、且有足够买回预算时','等准备刷新且有足够买回预算时')
 byid['lifesteal-dispute']['text']='吸血与快速阵亡复生是两种装备取向。明先生路线可不优先吸血，通过较快阵亡复生重新选择攻击目标；需要延长每条命的有效输出时，再比较续战收益。判断对手伤害、当前复生预算和攻击目标是否需要重选，不把无吸血等同于所有局面更强。现有材料缺少同等配置的定量比较。'
 extra=deepcopy(byid['lifesteal-dispute']);extra['id']='ying-lifesteal-sustain';extra['text']='嬴律路线可用吸血补充半血复生后的持续作战。需要延长每条命的输出、且确实能有效吸回血量时考虑；若更需要快速阵亡触发牺牲和复生后重新选取目标，再比较其他装备。现有材料缺少同等配置的定量比较，无法给出统一优先级。';note['claims'].append(extra)
 extra=deepcopy(byid['coin-machine']);extra['id']='zhuang-coin-machine-choice';extra['text']='庄小鱼尽快将棋手升至五阶启动时，古币需要用于即时战力且余币不足，不优先投入古币机。先满足花木兰、李白的当轮战力与体系启动需求，再比较额外经济收益。';note['claims'].append(extra)
 byid['coin-machine']['text']=byid['coin-machine']['text'].split('庄小鱼尽快将棋手升至五阶材料')[0].strip()
 descriptions={
 'ming':('已有保血过渡战力、能量卦象支持到棋手五阶，并能保留购买核心的资源时考虑。','花木兰迟迟不来且掉血压力大时先补李信或李白过渡，不能只有刷新没有战力。','能量与刷新卦象支持找体系。','核心未到手时战力空窗；留五与将棋手升至六阶的收益边界尚不明确。'),
 'zhuang':('有启动如梦的金币、有用河洛人数和可承受的掉血空间时考虑。','凑入无用河洛牌、棋手升级后无预算买牌，或等待如梦会导致淘汰时先补当轮战力。','如梦与梦幻商店补组件、觉醒和露娜。','技能不保证命中核心；人数、合成和保血需要协同。'),
 'naonao':('可按派对牌和经济棋手升级、棋手五阶启动朋友多多找体系时考虑。','棋手五阶仍无花木兰时先补核心；古币数量多但等级不足时补李白或永久成长。','朋友多多找体系，零钱兑换放大古币使用张数。','破损古币不提供等级；集中启动回合操作密集。'),
 'zhaojun':('较早取得花木兰、有适合的冻结强化时考虑；已有持续冻结成长的司空震时可双输出。','无法较早取得花木兰时保留当前高阶战力，比较高阶大河；不为双输出硬追司空震。','冻结补高阶牌与成长，条件到位时保留第二输出。','变化不保证花木兰，露娜循环受强化与公共牌库限制。'),
 'ying':('能结合所选战略保血，并能观察全场资源与同行露娜需求时考虑。','开放决策会让同行先拿核心，或棋手升级会导致当轮淘汰时，先保质量和自身获取资源。','战略与决策提供资源、首购复制和体系补强。','全场决策也会帮助对手，操作与资源时机判断较复杂。')}
 meta['compositions']['early']=[]
 for b in meta['player_branches']:
  key=b['id'];adopt,avoid,adv,dis=descriptions[key];b['selection']={'adopt':adopt,'avoid':avoid,'signals':{'来牌与同行':'先检查花木兰、上官婉儿与露娜的获取和公共牌库；同行会争夺露娜。','对手与压力':'先能保住当轮血量，再为后续循环存资源；无统一血量阈值。'}}
  route=next(r for r in meta['operation_routes'] if r['id']==key);b['operation_route_ids']=[key]
  route['risks']=route['risks'].replace('默认棋手五阶持续刷新，将棋手升至六阶另按局势取舍','棋手五阶刷新与将棋手升至六阶分别看买牌和保血预算')
  b['condition_refs']=route['claim_refs'][:1]
  b['assessment']=[assessment('advantages',adv,b['condition_refs']),assessment('disadvantages',dis,route['claim_refs']),assessment('formation', '需要花木兰及古币体系启动，按当前来牌和技能资源判断；没有统一成型概率。',route['claim_refs']),assessment('operation','需要管理露娜打出位置、资源预算和本棋手技能时机。',route['claim_refs'])]
  if key in ('ming','zhuang','ying','naonao'):b['overrides']['compositions']={'early':deepcopy(note['history'][-1]['previous']['meta']['compositions']['early'])}
  if key=='zhuang':b['claim_refs'].append('zhuang-coin-machine-choice')
  if key=='ying':b['claim_refs'].append('ying-lifesteal-sustain')
  if key=='zhaojun':b['major_variant_ids']=['zhaojun-double'];b['overrides']['compositions']={'early':[]}
  b['late_variant_ids']=[r['id'] for r in meta.get('late_variants',[])]
 meta['assessment']=[assessment('ceiling','完整产币与复生循环可持续提高本轮输出；仍受复生上限、装备和对手控制限制。',['coin-loop','revive-cap-pending','mulan-vs-yaomei-lixin']),assessment('floor','核心与婉儿觉醒不足时，复生预算与保血能力会下降。',['review-short-revives','review-cost']),assessment('environment','同行持有露娜、强控制及风筝会改变资源与装备选择，缺少统一版本胜率统计。',['luna-elimination-pool','ailin-chase'])]

def single(note,key,common_indices):
 meta=note['meta'];claims=note['claims'];common={claims[i]['id'] for i in common_indices}
 meta['common_claim_refs']=[c['id'] for c in claims if c['id'] in common]
 b=new_branch(key,[c['id'] for c in claims if c['id'] not in common]);meta['player_branches']=[b]
 b['operation_route_ids']=[r['id'] for r in meta.get('operation_routes',[])];b['late_variant_ids']=[r['id'] for r in meta.get('late_variants',[])];b['major_variant_ids']=[r['id'] for r in meta.get('major_variants',[])]
 # All stage lists belong explicitly to this player's complete route.
 b['overrides']={'compositions':deepcopy(meta['compositions'])};meta['compositions']={s:[] for s in ('early','middle','late')}
 summaries={
 'yaomei':('能保前期胜场养小鹿，河洛开放，且能取得李信、钟馗和复生工具时考虑。','持续掉血或缺李信时先补过渡战力；共鸣前不能安全将棋手升至六阶时不硬升。','小鹿奉献集中等级，李信结合牺牲与复生继续输出。','依赖死亡顺序、连线与100级门槛；复生成员可能分走奉献收益。'),
 'zhaojun':('大河开放，有冻结进化技能和图腾组件时考虑，东皇太一、敖隐为主要核心。','核心不到场时保留元流之子等过渡战力；司空震是可选补强，不因河洛被禁就否定整套打法。','控制与回复为高阶英雄争取输出时间，多人口可提高合成品阶。','怕图腾被范围伤害清掉；等级转移、冻结和站位需要配合。'),
 'angela':('大河、逐鹿开放，能够取得刘邦及图腾、扁鹊时考虑。','刘邦未到手不追工具觉醒；持续不来时保留资源将棋手升至六阶，禁逐鹿无法照搬完整炸盾体系。','刘邦图腾永久成长，飞行器与明世隐支持等级转化。','近战易被风筝，缺扁鹊时炸盾路线受损；工具位与人口取舍影响成长。')}
 adopt,avoid,adv,dis=summaries[key];b['selection']={'adopt':adopt,'avoid':avoid,'signals':{'来牌':'先取得核心再追工具质量，具体替换见本打法运营。','同行与对手':'先观察同行是否占用关键牌及对手控制、爆发和回复；缺少统一数量阈值。','经济和掉血压力':'保留当轮必要战力与核心预算，能稳定过渡再棋手升级。'}}
 b['condition_refs']=b['claim_refs'][:2]
 b['assessment']=[assessment('advantages',adv,b['claim_refs'][:2]),assessment('disadvantages',dis,b['claim_refs'][:2]),assessment('formation','需要核心与对应成长组件，缺牌时按来牌和压力选择替代路线；无可靠成型概率统计。',b['claim_refs'][:2]),assessment('operation','需兼顾成长工具、棋手升级预算、站位与针对换装，操作时间不足时先保证关键步骤。',b['claim_refs'][:2])]
 meta['assessment']=[assessment('ceiling','等级成长与成型装备可提高后期战力，上限受对手控制、爆发和组件完整度影响。',list(common)[:2]),assessment('floor','核心缺失或成长未启动时依赖过渡质量，不能按顺风示范局估计下限。',list(common)[:2])]

def migrate(root):
 root=Path(root)
 with workspace.store_lock(root):
  workspace.recover(root);items=deepcopy(workspace.notes(root))
  if any(branches.enabled(n) for n in items):raise ValueError('已有schema5分支，请使用现有记录，不重复迁移')
  snapshot={'at':wxq.now(),'notes':deepcopy(items)};wxq.atomic_json(root/'knowledge/migrations/schema4-player-branches.json',snapshot)
  frozen=next(n for n in items if n['id']=='changxiaoe-general-play');frozen=deepcopy(frozen)
  for n in items:
   if n['id'] not in ('heluo-huamulan','yaomei-sacrifice-lixin','zhaojun-high-tier-dahe','angela-liubang-totems'):continue
   from lineup_layout import _render_generic,_render_markdown,PROFILE_ID
   original_text=_render_markdown(n) if n['id']==PROFILE_ID else _render_generic(n)
   n['reading_layout']={'preserve_original':True,'sections':re.findall(r'^## (.+)$',original_text,re.M)}
   n.setdefault('history',[]).append({'at':wxq.now(),'origin':'schema_migration','previous':{'claims':deepcopy(n['claims']),'meta':deepcopy(n['meta'])},'reason':'明确共通与棋手归属，保留原始证据及人工修订'})
   if n['id']=='heluo-huamulan':heluo(n)
   elif n['id']=='yaomei-sacrifice-lixin':single(n,'yaomei',[0,2,3,29])
   elif n['id']=='zhaojun-high-tier-dahe':single(n,'zhaojun',[])
   else:single(n,'angela',[])
   common=set(n['meta']['common_claim_refs'])
   for c in n['claims']:
    c['text']=c['text'].replace('见“尚待裁决”','见本棋手关于唤醒时机的两种方案').replace('见“路线与装备取舍”','见本棋手的装备与运营选择').replace('本批','现有').replace('暂不确定推荐其中一种','缺少可比较的等待回合和收益边界，需按即时转化与觉醒后收益取舍')
   # No source is relabelled: unchanged stable IDs and evidence are retained;
   # the full old wording and ownership are present in the migration snapshot.
   branches.validate(n)
   if len(n['meta']['player_branches'])==1:
    b=n['meta']['player_branches'][0]
    b['assessment'].extend(n['meta'].get('assessment',[]));n['meta']['assessment']=[]
   for b in n['meta']['player_branches']:
    for a in b.get('assessment',[]):
     if len(a['claim_refs'])<=2:a['claim_refs']=b['claim_refs']
  for key in ('yaomei','ming','zhuang','naonao','ying'):
   player,name=PLAYERS[key]
   if not any(n['type']=='player' and player in n.get('entities',[]) for n in items):
    items.append({'id':'player-'+key,'type':'player','title':name,'player_id':player,'aliases':[],'entities':[player],'core':[],'claims':[],'related':[]})
  # Existing frozen note participates in no automatic new relationship enrichment.
  workspace.prepare(root,items)
  items=[deepcopy(frozen) if n['id']==frozen['id'] else n for n in items]
  transaction=workspace.make_transaction(root,items)
  transaction['index']['notes']=[deepcopy(frozen) if n['id']==frozen['id'] else n for n in transaction['index']['notes']]
  transaction['blocked_notes']=list(set(transaction['blocked_notes'])|{frozen['id']})
  wxq.atomic_json(root/'knowledge/pending-save.json',transaction);workspace.apply_transaction(root,transaction)
  wxq.atomic_json(root/'knowledge/replays/schema5-player-branches.json',{'schema_version':5,'notes':[n for n in transaction['index']['notes'] if n['id']!=frozen['id']]})
  return {'notes':len(items),'player_documents':sum(len(branches.documents(n)) for n in items)}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);print(migrate(parser.parse_args().root))
