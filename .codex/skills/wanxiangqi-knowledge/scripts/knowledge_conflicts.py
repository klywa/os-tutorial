"""Append-only conflict requests and transactional resolutions."""
from pathlib import Path
from copy import deepcopy
import re
import json_store as store
import knowledge_history as history
from knowledge_merge import merge_record,union
from workspace import Conflict,store_lock

def create_request(base,left,right,preferred='right',origin='local'):
 rows=[x for x in (base,left,right) if x is not None]
 if not rows:raise ValueError('Empty request')
 nid=rows[0]['metadata']['id']
 for row in rows:
  store.check_record(row)
  if row['metadata']['id']!=nid:raise ValueError('Different note identities')
 return {'schema_version':1,'kind':'request','note_id':nid,'base':deepcopy(base),'left':deepcopy(left),'right':deepcopy(right),'preferred':preferred,'origin':origin}

def event_path(value):
 if value['kind']=='request':return 'knowledge-sync/requests/'+store.digest(value)+'.json'
 return 'knowledge-sync/resolutions/'+store.digest(value['note_id'])[:32]+'/'+store.digest(value)+'.json'

def validate_event(relative,value):
 if not isinstance(value,dict) or value.get('kind') not in ('request','resolution'):raise ValueError('Invalid sync event')
 nid=value.get('note_id','')
 if not re.fullmatch(r'[a-zA-Z0-9_-]+',nid) or relative!=event_path(value):raise ValueError('Sync integrity mismatch')
 if value['kind']=='request':
  expected=create_request(value['base'],value['left'],value['right'],value['preferred'],value['origin'])
  if expected!=value:raise ValueError('Invalid request')
 else:
  if not isinstance(value.get('request_ids'),list) or any(not re.fullmatch('[0-9a-f]{64}',x) for x in value['request_ids']):raise ValueError('Invalid resolution requests')
 return value

def immutable_event(root,relative,value):
 validate_event(relative,value);path=Path(root)/relative
 if path.exists() and store.read(path)!=value:raise ValueError('Immutable sync collision')
 store.write_file(path,value)

def write_request(root,request):
 """Caller holds store_lock, shared with resolve and other canonical writes."""
 path=event_path(request);immutable_event(root,path,request);return store.digest(request)

def _requests(root,nid=None):
 rows=[]
 for p in (Path(root)/'knowledge-sync/requests').glob('*.json'):
  value=validate_event(p.relative_to(root).as_posix(),store.read(p))
  if nid is None or value['note_id']==nid:rows.append((p.stem,value))
 closed=set()
 for p in (Path(root)/'knowledge-sync/resolutions').glob('*/*.json'):
  value=validate_event(p.relative_to(root).as_posix(),store.read(p))
  if nid is None or value['note_id']==nid:closed.update(value['request_ids'])
 return sorted((key,v) for key,v in rows if key not in closed)

def _detail(root,nid):
 rows=_requests(root,nid)
 if not rows:return None
 current=store.load_record(root,nid);variants={}
 for _,req in rows:
  for side in ('left','right'):
   v=req[side];key=store.digest(v)
   if v!=current:variants[key]=v
 conflicts=[];merged=deepcopy(current)
 for rid,req in rows:
  # The actual disk record is current, regardless of request side preference.
  for side in ('left','right'):
   incoming=req[side]
   if incoming==current:continue
   vid=store.digest(incoming);m=merge_record(req['base'],merged,incoming,preferred='left');merged=m['record']
   for c in m['conflicts']:
    c.update(variant_id=vid,request_id=rid);c['id']=store.digest([rid,vid,c['id']])[:24];conflicts.append(c)
 return {'note_id':nid,'revision':store.digest([rows,current]),'note_revision':current['metadata'].get('revision') if current else None,'request_ids':[k for k,_ in rows],'current':current,'variants':variants,'conflicts':conflicts,'merged':merged,'requests':rows}

def _text(value):
 if value is None:return None
 if isinstance(value,str):return value
 if isinstance(value,dict):return value.get('value',value.get('title','关联信息发生变化'))
 if isinstance(value,list) and all(isinstance(x,str) for x in value):return value
 return '关联信息发生变化'

def get_group(root,note_id):
 d=_detail(root,note_id)
 if d is None:return None
 return {**{k:d[k] for k in ('note_id','revision','note_revision','request_ids')},
  'current':{'variant_id':store.digest(d['current']),'body':deepcopy(d['current']['body']) if d['current'] else None},
  'variants':[{'variant_id':k,'body':deepcopy(v['body']) if v else None} for k,v in d['variants'].items()],
  'conflicts':[{'id':c['id'],'path':c['path'],'reason':c['reason'],'base':_text(c['base']),'current':_text(c['left']),'incoming':_text(c['right']),'variant_id':c['variant_id']} for c in d['conflicts']]}

def list_groups(root):return [get_group(root,n) for n in sorted({v['note_id'] for _,v in _requests(root)})]
def is_blocked(root,note_id):return bool(_requests(root,note_id))

def _assign(record,path,value):
 parts=path.split('/')
 if parts==['record']:return deepcopy(value)
 parent=record
 for p in parts[:-1]:
  if isinstance(parent,list):parent=next(x for x in parent if x['id']==p)
  else:parent=parent[p]
 key=parts[-1]
 if key=='order' and isinstance(parent,list):parent[:]=sorted(parent,key=lambda n:value.index(n['id']) if n['id'] in value else len(value));return record
 if isinstance(parent,list):
  old=next((x for x in parent if x['id']==key),None)
  position=parent.index(old) if old is not None else len(parent)
  if old is not None:parent.remove(old)
  if value is not None:parent.insert(position,deepcopy(value))
 elif value is None:parent.pop(key,None)
 else:parent[key]=deepcopy(value)
 return record

def resolve(root,note_id,payload,actor='admin'):
 with store_lock(root,wait=True):
  store.recover(root);d=_detail(root,note_id)
  if not d or payload.get('revision')!=d['revision'] or payload.get('note_revision')!=d['note_revision']:raise Conflict('冲突集合或当前笔记已变化，请重新读取')
  choices={c['conflict_id']:c for c in payload.get('choices',[])};record=d['merged'];manual=[]
  for c in d['conflicts']:
   choice=choices.get(c['id'])
   if not choice:raise ValueError('缺少冲突选择：'+c['id'])
   action=choice['action']
   if action=='current':selected=c['left']
   elif action=='incoming':
    if choice.get('variant_id',c['variant_id'])!=c['variant_id']:raise ValueError('候选版本不匹配')
    selected=c['right']
   elif action=='manual':
    parts=c['path'].split('/')
    if not isinstance(choice.get('text'),str) or parts[0]!='body' or parts[1] not in ('nodes','supporting_nodes'):raise ValueError('只能手工修改正文文本')
    if len(parts)==4 and parts[-1] in ('value','title'):selected=choice['text']
    elif len(parts)==3 and isinstance(c['left'] or c['right'],dict):
     selected=deepcopy(c['left'] or c['right']);selected['value' if selected['type']=='entry' else 'title']=choice['text']
    else:raise ValueError('只能手工修改正文文本')
    manual.append(parts[2])
   else:raise ValueError('无效解决动作')
   record=_assign(record,c['path'],selected)
  archives=[];parents=[]
  for _,req in d['requests']:
   for side in ('base','left','right'):
    if req[side]:
     plan=history.archive_record(req[side],origin='sync_conflict');archives.extend(plan['writes']);parents.append(plan['ref'])
  if record:
   # Rebuild evidence from versions whose node text is actually selected.
   sources=[d['current'],*d['variants'].values()];nodes={n['id']:n for k in ('nodes','supporting_nodes') for n in record['body'].get(k,[])};claims=[]
   for src in sources:
    if not src:continue
    original={n['id']:n for k in ('nodes','supporting_nodes') for n in src['body'].get(k,[])}
    claims=union(claims,[c for c in src['metadata'].get('claim_annotations',[]) if c['text_ref'] not in manual and c['text_ref'] in nodes and original.get(c['text_ref'])==nodes[c['text_ref']]])
   record['metadata']['claim_annotations']=claims
   record['metadata']['manual_sections']=union(*[v['metadata'].get('manual_sections',[]) for v in sources if v])
   for source in sources:
    if not source:continue
    for nid,annotation in source['metadata'].get('node_annotations',{}).items():
     if nid in nodes and annotation.get('origin')=='manual':record['metadata'].setdefault('node_annotations',{})[nid]=deepcopy(annotation)
   if any(v and v['metadata'].get('manual_semantics') for v in sources):record['metadata']['manual_semantics']=True
   for nid in manual:record['metadata'].setdefault('node_annotations',{})[nid]={'origin':'manual','actor':actor}
   plan=history.archive_record(record,origin='sync_resolution',parents=parents)
   archives.extend(plan['writes'])
   record['metadata'].setdefault('history',[]).append({'origin':'sync_resolution','version_ref':plan['ref'],'actor':actor})
   journal=store.save(root,[record],partial=True,origin='sync_resolution',prepare_only=True)
  else:journal=store.save(root,[r for r in store.records(root) if r['metadata']['id']!=note_id],origin='sync_resolution',prepare_only=True)
  if not journal:journal={'records':[],'index':store.read(Path(root)/store.INDEX),'versions':[],'origin':'sync_resolution'}
  event={'kind':'resolution','schema_version':1,'note_id':note_id,'request_ids':d['request_ids'],'revision':d['revision'],'actor':actor,'choices':deepcopy(payload['choices'])}
  journal.setdefault('archives',[]).extend(archives);journal['sync_events']=[{'path':event_path(event),'value':event}]
  store.write_file(Path(root)/store.JOURNAL,journal);store.recover(root)
  saved=store.load_record(root,note_id);return store.project(saved,public=True) if saved else None
