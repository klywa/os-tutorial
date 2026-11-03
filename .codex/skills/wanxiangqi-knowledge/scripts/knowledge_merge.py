"""Pure stable-node three-way merge. No filesystem access."""
from copy import deepcopy
import json_store as store
MISSING=object()
IGNORED={'revision','body_sha256','history','history_head','history_count','history_parents'}

def union(*values):
 out=[]
 for rows in values:
  for v in rows:
   if v not in out:out.append(deepcopy(v))
 return out

def merge_record(base,left,right,preferred='right'):
 if preferred not in ('left','right'):raise ValueError('Invalid preferred side')
 inputs=[r for r in (base,left,right) if r is not None]
 if not inputs:return {'record':None,'conflicts':[]}
 ids={r['metadata']['id'] for r in inputs}
 if len(ids)!=1:raise ValueError('Different note identities')
 conflicts=[]
 def conflict(path,b,l,r,reason='双方修改了同一内容'):
  row={'path':path,'reason':reason,'base':deepcopy(None if b is MISSING else b),'left':deepcopy(None if l is MISSING else l),'right':deepcopy(None if r is MISSING else r)}
  row['id']=store.digest([path,row['base'],row['left'],row['right']])[:24];conflicts.append(row)
  return deepcopy(r if preferred=='right' else l) if (r if preferred=='right' else l) is not MISSING else MISSING
 def value(b,l,r,path):
  if l==r:return deepcopy(l) if l is not MISSING else MISSING
  if l==b:return deepcopy(r) if r is not MISSING else MISSING
  if r==b:return deepcopy(l) if l is not MISSING else MISSING
  if isinstance(l,dict) and isinstance(r,dict) and (isinstance(b,dict) or b is MISSING):
   out={};bb={} if b is MISSING else b
   for k in dict.fromkeys([*bb,*l,*r]):
    v=value(bb.get(k,MISSING),l.get(k,MISSING),r.get(k,MISSING),path+'/'+k)
    if v is not MISSING:out[k]=v
   return out
  return conflict(path,b,l,r,'删除与修改发生分歧' if l is MISSING or r is MISSING else '双方修改了同一内容')
 if base is None or left is None or right is None:
  chosen=value(base if base is not None else MISSING,left if left is not None else MISSING,right if right is not None else MISSING,'record')
  return {'record':None if chosen is MISSING else chosen,'conflicts':conflicts}
 result={'body':{},'metadata':{}}
 def nodes(key):
  lists=[x['body'].get(key,[]) for x in (base,left,right)];maps=[{n['id']:n for n in ns} for ns in lists];out={}
  for nid in dict.fromkeys(n['id'] for ns in lists for n in ns):
   path='body/'+key+'/'+nid
   protected=[nid in store.manual_nodes(x) for x in (base,left,right)]
   if ((protected[1] and maps[1].get(nid)!=maps[2].get(nid) and maps[2].get(nid)!=maps[0].get(nid)) or (protected[2] and maps[1].get(nid)!=maps[2].get(nid) and maps[1].get(nid)!=maps[0].get(nid))):
    v=conflict(path,*(m.get(nid,MISSING) for m in maps),reason='人工正文受到保护，需要明确选择')
   else:v=value(*(m.get(nid,MISSING) for m in maps),path)
   if v is not MISSING:out[nid]=v
  # Pairwise changed order constraints preserve section positions and detect cycles.
  positions=[{n['id']:i for i,n in enumerate(ns)} for ns in lists];edges={n:set() for n in out};keys=list(out)
  for i,a in enumerate(keys):
   for c in keys[i+1:]:
    rel=[(p[a]<p[c]) if a in p and c in p else None for p in positions];b,l,r=rel
    if l is not None and r is not None:
     chosen=l if l==r or r==b else r if l==b else (r if preferred=='right' else l)
    else:chosen=l if l is not None else r if r is not None else b
    if chosen is not None:edges[a if chosen else c].add(c if chosen else a)
  ordered=[]
  while len(ordered)<len(out):
   ready=[n for n in keys if n not in ordered and not any(n in edges[x] for x in keys if x not in ordered)]
   if not ready:
    conflict('body/'+key+'/order',list(positions[0]),list(positions[1]),list(positions[2]),'章节或段落顺序相互矛盾')
    ordered.extend(n for n in positions[2 if preferred=='right' else 1] if n in out and n not in ordered);ordered.extend(n for n in keys if n not in ordered);break
   ordered.append(ready[0])
  return [out[n] for n in ordered]
 for k in dict.fromkeys(k for r in (base,left,right) for k in r['body']):
  if k in ('nodes','supporting_nodes'):result['body'][k]=nodes(k)
  else:
   b,l,r=(src['body'].get(k,MISSING) for src in (base,left,right))
   if k=='semantics' and l!=r and ((left['metadata'].get('manual_semantics') and r!=b) or (right['metadata'].get('manual_semantics') and l!=b)):
    v=conflict('body/'+k,b,l,r,'人工关联知识受到保护，需要明确选择')
   else:v=value(b,l,r,'body/'+k)
   if v is not MISSING:result['body'][k]=v
 for k in dict.fromkeys(k for r in (base,left,right) for k in r['metadata']):
  if k in IGNORED or k in ('claim_annotations','node_annotations','manual_sections','manual_semantics'):continue
  v=value(*(r['metadata'].get(k,MISSING) for r in (base,left,right)),'metadata/'+k)
  if v is not MISSING:result['metadata'][k]=v
 meta=result['metadata']
 selected=right if preferred=='right' else left
 for k in ('history_head','history_count'):
  if k in selected['metadata']:meta[k]=deepcopy(selected['metadata'][k])
 meta['history']=deepcopy(selected['metadata'].get('history',[]))
 retired=[]
 for source in (base,left,right):
  for claim in source['metadata'].get('retired_claim_annotations',[]):
   item=deepcopy(claim)
   if source['metadata'].get('history_head'):item.setdefault('history_branch',source['metadata']['history_head'])
   retired=union(retired,[item])
 if retired:meta['retired_claim_annotations']=retired
 texts={n['id']:n for k in ('nodes','supporting_nodes') for n in result['body'].get(k,[])}
 claims=[];annotations={}
 for r in (base,left,right):
  original={n['id']:n for k in ('nodes','supporting_nodes') for n in r['body'].get(k,[])}
  for c in r['metadata'].get('claim_annotations',[]):
   nid=c['text_ref']
   if nid in texts and original.get(nid)==texts[nid]:
    existing=next((v for v in claims if {k:v for k,v in v.items() if k!='evidence'}=={k:v for k,v in c.items() if k!='evidence'}),None)
    if existing is None:claims.append(deepcopy(c))
    else:existing['evidence']=union(existing.get('evidence',[]),c.get('evidence',[]))
  for nid,a in r['metadata'].get('node_annotations',{}).items():
   if nid in texts:
    if annotations.get(nid,{}).get('origin')!='manual':annotations[nid]=deepcopy(a)
 meta['claim_annotations']=claims;meta['node_annotations']=annotations
 meta['manual_sections']=union(*[r['metadata'].get('manual_sections',[]) for r in (base,left,right)])
 if any(r['metadata'].get('manual_semantics') for r in (base,left,right)):meta['manual_semantics']=True
 try:store.check_record(result)
 except ValueError as exc:
  result=conflict('record',base,left,right,'关联知识需要与正文一起选择：'+str(exc))
 return {'record':result,'conflicts':conflicts}
