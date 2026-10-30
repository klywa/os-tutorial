"""Public website transport and complete lineup/commander statistics."""
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import time
import urllib.request

SITE='https://www.datawxq.com'
API='https://api.datatft.com/wzwxq/lineups/'


def read_website(url,payload=None):
    headers={'User-Agent':'Mozilla/5.0','Origin':SITE,'Referer':SITE+'/lineups',
             'App-Platform':'wzwxq','Accept-Language':'CN','Browser-Language':'ZH-CN'}
    if payload is not None:
        stamp=str(int(time.time()*1000));nonce=secrets.token_hex(8);did='did'+secrets.token_hex(12)[:23]
        headers.update({'t':stamp,'nonce':nonce,'did':did,
                        'signature':hashlib.md5((stamp+nonce+did+'koTefnFEdaYDuLFmXyzt').encode()).hexdigest(),
                        'Content-Type':'application/json'})
    request=urllib.request.Request(url,None if payload is None else json.dumps(payload).encode(),headers)
    with urllib.request.urlopen(request,timeout=45) as response:
        return response.read().decode('utf-8')


def website_scope(read=read_website):
    html=read(SITE+'/lineups');asset=re.search(r'src="(/assets/index-[^"/]+\.js)"',html)
    if not asset:raise ValueError('网站脚本结构已变化，原使用率保留')
    index=read(SITE+asset[1]);desktop=re.search(r'assets/desktop-main-[\w-]+\.js',index)
    if not desktop:raise ValueError('网站默认版本不可识别')
    script=read(SITE+'/'+desktop[0]);version=re.search(r'\[\{value:"(v\d+)",label:"\1"\}',script)
    if not version:raise ValueError('网站默认版本不可识别')
    return {'version':version[1],'gameType':'2','time':7,'minimumCount':50,'sortBy':'appearanceRate'}


def _response(read,url,payload):
    data=json.loads(read(url,payload))
    if not isinstance(data,dict) or data.get('code') not in (None,0,1,200):
        raise ValueError('网站请求失败：'+str(data.get('message',data.get('msg','响应无效')) if isinstance(data,dict) else '响应无效'))
    data=data.get('data',data)
    if not isinstance(data,dict):raise ValueError('网站统计响应不是对象')
    return data


def display_name(row,heroes):
    """Mirror the site's current lineupPresentation: carries by average level."""
    from lineup_catalog import website_name
    faction=website_name({**row,'recommendedUnits':[]},heroes)
    if row.get('groupingMode')=='playstyleCarry':faction=row.get('playstyle',{}).get('name') or '未识别玩法'
    stats={str(s['heroId']):s for s in row.get('recommendedUnits',[])}
    stats.update({str(s['heroId']):s for s in row.get('heroEquipment',[])})
    explicit=row.get('carryHeroes') is not None
    candidates=[]
    for i,hero in enumerate(row.get('carryHeroes',[]) if explicit else row['heroes']):
        stat=stats.get(str(hero['id']),{});level=stat.get('avgLevel')
        valid=isinstance(level,(int,float)) and math.isfinite(level) and level>0
        if explicit or (stat.get('appearanceRate',0)>.5 and valid):
            candidates.append((hero,level if valid else 0,stat.get('appearanceRate',0),stat.get('count',0),i))
    candidates.sort(key=lambda c:(-c[1],-c[2],-c[3],c[4]));candidates=candidates[:3 if explicit else 2]
    ceiling=candidates[0][1] if candidates else 0
    names=[c[0].get('name',str(c[0]['id'])) for c in candidates if explicit or c[1]>=ceiling*.5]
    title=' · '.join([faction,*names])
    source=row.get('primaryLevelSource') if row.get('groupingMode') not in ('carryCombination','playstyleCarry') else None
    if source:
        label={'known':'来源：'+source.get('title',''),'none':'无外部来源','unknown':'来源待补全'}.get(source.get('status'))
        if label:title+='（'+label+'）'
    return title


def fetch_usage(root,read=None,pause=None,limit=10):
    read=read or read_website;pause=pause or (lambda:time.sleep(.3))
    scope=website_scope(read);pages=[];records=[];keys=set();seen=set();expected_total=None
    common={**scope,'operator':'AND','advancedMode':False,'filters':[],'exclusions':[],'pageSize':12}
    for page in range(1,501):
        data=_response(read,API+'search',{**common,'page':page})
        rows=data.get('lineups');total=data.get('total')
        if not isinstance(rows,list) or type(total) is not int or total<0:raise ValueError('网站主榜分页无效')
        if expected_total is not None and total!=expected_total:raise ValueError('网站主榜分页总数变化，请稍后重试')
        expected_total=total
        marker=json.dumps(rows,sort_keys=True)
        if rows and marker in seen:raise ValueError('网站重复返回相同分页')
        seen.add(marker);pages.append(data)
        for row in rows:
            if not isinstance(row,dict) or not row.get('lineupKey') or row['lineupKey'] in keys:
                raise ValueError('网站阵容身份缺失或重复')
            keys.add(row['lineupKey']);records.append(row)
        if len(records)>total:raise ValueError('网站主榜总数变化，请稍后重试')
        if len(records)==total:break
        if not rows:raise ValueError('网站提前返回空页，主榜不完整')
        pause()
    else:raise ValueError('网站主榜分页超过安全上限')
    import json_store
    heroes=json_store.read(Path(root)/'entities/heroes.json',[])
    for row in records:
        rate=row.get('appearanceRate')
        if not isinstance(rate,(int,float)) or isinstance(rate,bool) or not math.isfinite(rate) or rate<0:
            raise ValueError('主榜阵容登场率无效')
    groups=[];details={};eligible=[]
    for row in sorted(records,key=lambda r:(-r['appearanceRate'],r['lineupKey'])):
        # A commander's share is <= 1. Once enough eligible pairs exceed this
        # parent's rate, this and all later parents cannot enter the requested ranking.
        # Equality is deliberately NOT pruned: games/identity break rate ties.
        if len(eligible)>=limit and row['appearanceRate']<sorted(eligible,reverse=True)[limit-1]:break
        source_id=row['lineupKey']
        # ordinary contains the parent denominator; dimensions contains ALL
        # commanders, unlike the three previews in the main list.
        try:
            detail=_response(read,API+'detail',{**common,'page':1,'lineupKey':source_id,'detailSections':['ordinary','dimensions']})
        except (ValueError,OSError) as exc:
            raise ValueError(f'阵容{source_id}详情读取失败：{exc}') from exc
        if 'loadedSections' in detail and 'dimensions' not in detail['loadedSections']:
            raise ValueError('网站未返回完整棋手统计：'+source_id)
        details[source_id]=detail
        parent=detail.get('lineup',detail)
        count=parent.get('count',row.get('count'));rate=row['appearanceRate']
        commanders=detail.get('commanders')
        if type(count) is not int or count<=0 or not isinstance(rate,(int,float)) or isinstance(rate,bool) or not math.isfinite(rate) or rate<0:
            raise ValueError('阵容场次或登场率无效：'+source_id)
        if not isinstance(commanders,list):raise ValueError('阵容详情缺少完整棋手分布：'+source_id)
        people=[];ids=set()
        for person in commanders:
            if (not isinstance(person,dict) or not str(person.get('id','')).strip()
                    or type(person.get('count')) is not int or not 0<=person['count']<=count):
                raise ValueError('棋手场次无效：'+source_id)
            pid='player:'+str(person['id']).removeprefix('player:')
            if pid in ids:raise ValueError('完整棋手分布出现重复身份：'+source_id)
            ids.add(pid);people.append({'id':pid,'name':str(person.get('name') or pid),'count':person['count']})
            if person['count']>=50:eligible.append(rate*person['count']/count)
        units=row.get('heroes')
        if not isinstance(units,list) or not units or any(not isinstance(h,dict) or not str(h.get('id','')).strip() for h in units):
            raise ValueError('网站阵容缺少完整组成：'+source_id)
        groups.append({'id':source_id,'name':display_name({**row,**detail,'heroes':units},heroes),
                       'heroes':sorted({'card:'+str(h['id']).removeprefix('card:') for h in units}),
                       'hero_names':[h.get('name',str(h['id'])) for h in units],
                       'count':count,'usage':rate,'commanders':people})
        pause()
    return {'url':SITE+'/lineups','scope':scope,'groups':groups,
            'raw':{'scope':scope,'pages':pages,'details':details,'main_groups':len(records),
                   'detailed_groups':len(groups),'pruned_by_upper_bound':len(records)-len(groups)}}
