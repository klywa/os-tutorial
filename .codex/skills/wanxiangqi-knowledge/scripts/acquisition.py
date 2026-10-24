"""Reviewed special acquisition rules applied to real official card definitions.

Only named, reviewed mechanisms participate. A name hit in a strategy note is
never used to infer a recommendation. Raw official entities remain unchanged.
"""
import hashlib
import json
from pathlib import Path
import re


FACTIONS={321:'大河流域',309:'三分',320:'逐鹿',319:'河洛',314:'日落海',307:'无阵营'}


def build(rows):
    by_name={}
    for row in rows:by_name.setdefault(row['name'],[]).append(row)
    heroes=[r for r in rows if r['category']=='heroes']
    normal=[r for r in heroes if r.get('properties',{}).get('type')==1]
    result={r['id']:{'routes':[],'other_uses':''} for r in heroes}

    def ids(*names):
        return sorted({r['id'] for name in names for r in by_name.get(name,[])})

    for hero in heroes:
        p=hero.get('properties',{});tier=p.get('quality');faction=FACTIONS.get(p.get('relationID'))
        name=hero['name'];effect=hero.get('description','');out=result[hero['id']]
        if p.get('type') not in (1,9) or not tier:continue
        def add(sources,text,kind='pool',requires=()):
            if not sources or sources[0] not in by_name:return
            sources=[s for s in sources if s in by_name]
            if not sources:return
            out['routes'].append(dict(text=text,evidence_ids=sorted(set([hero['id'],*ids(*sources)])),
                                      kind=kind,requires_names=list(requires)))
        if p.get('type')==9:
            base=next((h for h in normal if h['name']==name),None)
            if base:
                add([name],f'先取得{name}普通英雄牌，再通过同名牌合成积累觉醒进度；普通英雄随机获取渠道不等于直接获得觉醒卡。','awakening')
            if tier==5:
                add(['化铁为金'],f'化铁为金：指定1名1—3阶英雄，随机变为不在场的5阶英雄并觉醒；{name}不在场时有机会变为觉醒{name}。','transform')
            continue
        from official import plain
        for source in p.get('sourceCards',[]):
            description=plain(source.get('desc'))
            if not re.search(r'获得[^。；]*?\d+张(?:【[^】]+】)?(?:英雄)?'+re.escape(name),description):continue
            text=f"{source['name']}：取得该天赋时可获得1张{name}英雄牌。"
            if source['name']=='红豆之托':text+='备战阶段场上英雄总等级分别达到100、200、400级时，再获得1张王维。'
            out['routes'].append(dict(text=text,evidence_ids=sorted(set([hero['id'],*ids(source['name'])])),kind='fixed',requires_names=[]))
        add([f'{tier}阶英雄兑换券'],f'{tier}阶英雄兑换券：从对应品阶的3张候选英雄牌中选1张，有机会选到{name}。')
        # Editorial scope excludes Mengqi as a source, including via vouchers.
        # The voucher's independent route and Mengqi's own effect remain valid.
        add([f'{tier}阶英雄'],f'{tier}阶英雄：获得2张对应品阶英雄牌，有机会获得{name}。')
        if faction:
            channel=faction+'征召令'
            add([channel],f'{channel}：获得2张{faction}英雄牌，有机会获得{name}。')
        for keyword,channel in [('登场','登场人物'),('整备','整备高手'),('牺牲','牺牲品'),('闪现','闪现突击者'),('开团','开团号令')]:
            # Match actual card keywords, not a sentence referring to another hero's trigger.
            keyword_present=bool(re.search(r'(?:^|\n)'+keyword+r'(?:[：，,]|\n|$)',effect))
            if keyword=='牺牲':keyword_present=bool(re.search(r'(?:^|\n)牺牲：',effect))
            if keyword=='牺牲' and name=='钟馗':keyword_present=True
            if not keyword_present:continue
            add([channel],f'{channel}：获得2张具有{keyword}效果的英雄牌，有机会获得{name}。')
            if keyword=='登场':
                add(['乱世'],f'乱世：从3张登场英雄候选中选1张，有机会选到{name}。')
                if name!='甄姬':
                    triggers=[x for x in ['唤醒','集体唤醒'] if x in by_name]
                    preparations=[x for x in ['临阵磨枪','全军动员'] if x in by_name]
                    text=f'甄姬登场：普通甄姬获得1张其他登场英雄牌，觉醒甄姬从3张其他登场英雄中选1张，有机会获得{name}。'
                    if triggers:text+='甄姬在场时，可用'+'或'.join(triggers)+'再次触发她的登场。'
                    if '曹操' in by_name:
                        text+='曹操与甄姬在场时，'+('用'+'或'.join(preparations)+'触发曹操整备，' if preparations else '触发曹操整备后，')+'随机命中甄姬的登场后再争取获得'+name+'；两步都不保证命中目标。'
                    add(['甄姬','曹操',*triggers,*preparations],text,'hero',['甄姬'])
            supply='补给线：'+keyword
            add([supply],f'{supply}：'+('获得3张开团效果英雄牌，' if keyword=='开团' else f'获得1张{keyword}效果英雄牌，并在回合开始时再获得1张，')+f'有机会获得{name}。','talent')
        if faction=='逐鹿':
            add(['招募战术','高阶招募战术','庄周','老夫子','鲁班七号'],f'庄周登场或老夫子每回合首次合成可提供招募战术，觉醒后提供高阶招募战术；前者随机获得1张逐鹿英雄牌，后者从逐鹿英雄牌中3选1，有机会获得{name}。鲁班七号在场时每合成3次也会随机提供战术，普通卡有机会提供招募战术，觉醒卡有机会提供高阶招募战术。','hero',['庄周','老夫子'])
            add(['贤士登门','春风化雨'],f'贤士登门或春风化雨可在回合开始时提供逐鹿英雄牌，有机会获得{name}；春风化雨获胜后还可补1张场上逐鹿英雄的同名牌。','talent')
        if tier==5:
            add(['神兵天降','5阶英雄兑换券'],f'神兵天降提供4张5阶英雄兑换券，再逐张从3张候选中选1张，有机会取得{name}。')
        if tier>=2:add(['高级人才'],f'高级人才：棋手等级+1与{name}的{tier}阶相符时，有机会随机获得{name}。')
        add(['吸纳人才','广纳良才'],f'吸纳人才（英雄牌4选1）、广纳良才（英雄牌5选2）的候选中有机会出现{name}。')
        add(['呼朋唤友','求贤'],f'以同阵营英雄为目标使用呼朋唤友（随机1张）或求贤（3选1），有机会获得{name}。')
        add(['照影','超级复印机'],f'{name}已在场时，照影随机获得1张场上英雄牌，超级复印机随机获得3张相同的场上英雄牌，均有机会补充{name}同名牌。','copy',[name])
        if faction=='逐鹿':add(['久经沙场'],f'{name}已觉醒并在场时，对其使用久经沙场可获得1张{name}英雄牌；不能作为首张获取渠道。','copy',[name])
        for source,valid in [('双人游',tier in (2,3)),('三人游',tier in (4,5)),('天兵',tier==5),('五福临门',True),('慕名而来',True),('契约瓶',True)]:
            if valid:
                desc=next((r.get('description','') for r in by_name.get(source,[]) if r.get('description')), '')
                add([source],source+'：'+desc.replace('\n','')+f'其英雄牌候选有机会包含{name}。','talent')
        if faction:
            for suffix,tiers in [('新援',(2,3)),('增援',(3,4)),('强援',(4,5))]:
                channel=('大河' if faction=='大河流域' else faction)+suffix
                if tier in tiers:add([channel],f'{channel}：从{faction}的对应品阶英雄中随机供牌，有机会获得{name}。','talent')
        if tier in (3,4):add(['限制性进化'],f'限制性进化：移除{tier-2}阶英雄，获得高2阶的随机英雄牌，有机会获得{name}，上阵时等级为原等级+10。','transform')
        add(['终极复印机','点兵点将','站这别动'],f'{name}已在场时，可用终极复印机指定复制，或用点兵点将取得场上各英雄同名牌；站这别动需要先指定阵位，再每过2回合取得该格英雄牌。','copy',[name])
        if tier<=3:add(['复印机'],f'{name}已在场时，可用复印机指定取得其同名牌。','copy',[name])
        add(['镜像','即兴创作','灵感爆发','奇才'],f'对应棋手的镜像可复制上一张真实打出的{name}；即兴创作从场上随机复制；灵感爆发复制手中非觉醒英雄；奇才指定英雄取得4张同名牌。均需先有可复制的{name}，不是首张来源。','player-copy',[name])
        if tier>=2:
            add(['冰之心','霜寒进化','寒冰王座'],f'昭君的冰之心可冻结低1阶英雄，战斗结束后随机变为高1阶并继承等级，有机会得到{name}；霜寒进化将候选限制为同阵营高1阶'+('，寒冰王座则随机变为5阶英雄。' if tier==5 else '。'),'player-transform')

    # Concrete output cards are read from the actual hero's effect, not guessed
    # from lineup membership. These roles remain useful outside that lineup.
    products={'庄周':['招募战术','高阶招募战术'],'老夫子':['招募战术','高阶招募战术'],
              '武则天':['精致古币'],'程咬金':['古币','精致古币'],'盾山':['古币','精致古币'],
              '西施':['推演战术','高阶推演战术'],'蒙犽':['特训战术','高阶特训战术'],
              '白起':['援护战术','高阶援护战术'],'杨玉环':['弦音','妙音'],
              '梦奇':['1阶英雄兑换券']}
    for hero in heroes:
        effect=hero.get('description','');name=hero['name'];out=result[hero['id']]
        if name=='甄姬':
            targets=[h['name'] for h in normal if h['name']!='甄姬' and re.search(r'(?:^|\n)登场：',h.get('description',''))]
            out['other_uses']='登场能提供其他登场英雄牌，供牌目标包括'+'、'.join(targets)+'；普通卡随机获得1张，觉醒卡3选1。用唤醒、集体唤醒重触发，或由曹操整备随机命中她，可帮助其他阵容寻找这些英雄。'
        elif name=='曹操':
            out['other_uses']='曹操与甄姬在场时，整备随机命中甄姬可触发其登场供牌，争取露娜、周瑜、武则天、蒙犽等其他登场英雄；可用临阵磨枪或全军动员再次触发曹操整备，普通卡触发1名三分英雄，觉醒卡触发2名，不能保证命中甄姬。'
        elif name=='露娜':
            out['other_uses']='登场随机触发英雄整备，可在程咬金在场时争取古币供给、在西施在场时争取推演战术，或在曹操与甄姬在场时争取登场英雄供牌；分别服务河洛用币、逐鹿战术与其他阵容找牌，随机触发不保证命中指定英雄。'
        elif name=='李元芳':
            out['other_uses']='整备对最近的河洛英雄使用古币，普通卡使用1张，觉醒卡使用2张；可为花木兰累计用币次数，并给李信、李白等河洛成员补等级，先调整最近目标，不会把古币加入手牌。'
        elif name=='王维':
            out['other_uses']='开团获得空山人语和水穷云起各1张，可为采用王维的其他阵容补充这两张效果牌；王维需在场并实际触发开团。两张效果牌的完整效果尚缺卡面核对，不据此推荐具体加级或转移操作。'
        elif name=='鲁班七号':
            out['other_uses']='每合成3次随机获得战术牌，觉醒后改为高阶战术牌；有机会取得招募战术或高阶招募战术，继续寻找嬴政、庄周、蒙犽等逐鹿英雄。其他结果可补盾或等级，不能把随机战术视为必定供给指定英雄。'
        elif name in products:
            actual=[n for n in products[name] if n in effect]
            if actual:
                out['other_uses']=effect.replace('\n','')+'可提供'+'、'.join(actual)+'，供其他阵容使用。'
                if name in ('庄周','老夫子'):out['other_uses']+='招募战术可随机取得逐鹿英雄，高阶招募战术可3选1，包括嬴政、鲁班七号、庄周、蒙犽等；不保证取得指定英雄。'
                if name=='梦奇':out['other_uses']+='败阵可提升兑换券品阶，退场前核对实际品阶，再用对应兑换券寻找其他阵容的同阶英雄。'
                uses={
                    '武则天':'登场提供精致古币，可为花木兰增加用币次数，并给花木兰、李信、李白等河洛英雄补等级；打古币时保留武则天在场才能继续享受等级加成。',
                    '程咬金':'整备取得古币供花木兰累计用币、供李信或李白补等级；整备对自身使用的那张古币不进入手牌，手中取得的古币再指定实际受益河洛英雄。',
                    '盾山':'牺牲后提供古币，觉醒后改为精致古币，可为花木兰累计用币、为李信或李白补等级；需要实际触发牺牲后才能领取。',
                    '西施':'整备提供推演战术，觉醒后为高阶推演战术；可对嬴政、扁鹊等逐鹿施法英雄缩短本回合法力条，供高阶逐鹿嬴政、逐鹿炸盾等阵容加快施法。',
                    '蒙犽':'登场提供特训战术，觉醒后为高阶特训战术，可指定花木兰、敖隐、孙悟空等其他阵容英雄补永久等级；重复打出或重触发蒙犽登场前先留出实际打牌空间。',
                    '白起':'每回合首次使用效果牌后提供援护战术，觉醒后为高阶援护战术；给廉颇、曜、扁鹊等逐鹿成员补当轮护盾，可服务逐鹿炸盾阵容，不能在同一回合无限领取。',
                    '杨玉环':'在场每过3回合及退场时提供弦音，觉醒后为妙音；弦音补曹操、程咬金等1—3阶英雄觉醒进度，妙音可补李信、花木兰、露娜等高阶英雄。单纯为退场领牌而卖出前，先确认本轮不再依赖她的治疗。'}
                if name in uses:out['other_uses']=uses[name]
    return result


def register_snapshot(root,rows,locked=False):
    """Register a JSON document and verbatim card paragraphs, with no fake ASR."""
    import wxq
    from workspace import store_lock
    root=Path(root);rows=sorted(rows,key=lambda r:r['id'])
    content=(json.dumps(rows,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    digest=hashlib.sha256(content).hexdigest();sid='doc-'+digest
    paragraphs=[{'id':i+1,'text':json.dumps({k:r.get(k) for k in ('id','name','category','description','properties','sources','retrieved_at')},ensure_ascii=False,sort_keys=True)} for i,r in enumerate(rows)]
    from contextlib import nullcontext
    with nullcontext() if locked else store_lock(root,wait=True):
        registry=wxq.read_json(root/'knowledge/document-sources.json',{'documents':[]})
        if not any(r['id']==sid for r in registry['documents']):
            folder=root/'raw/documents'/sid;folder.mkdir(parents=True,exist_ok=True)
            artifact=folder/'official-cards.json';artifact.write_bytes(content)
            wxq.atomic_json(folder/'paragraphs.json',paragraphs)
            registry['documents'].append(dict(id=sid,type='document',title='官方卡牌机制JSON快照',sha256=digest,
                original_path='entities/*.json',artifact=artifact.relative_to(root).as_posix(),
                paragraphs=(folder/'paragraphs.json').relative_to(root).as_posix(),
                paragraph_sha256=hashlib.sha256((folder/'paragraphs.json').read_bytes()).hexdigest(),
                imported_at=wxq.now(),version=None))
            wxq.atomic_json(root/'knowledge/document-sources.json',registry)
    return {r['id']:dict(type='document',source=sid,paragraph_start=i+1,paragraph_end=i+1) for i,r in enumerate(rows)}
