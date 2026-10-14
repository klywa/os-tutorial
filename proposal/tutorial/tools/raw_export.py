"""Export complete uncorrected ASR without creating a correction artefact."""
import hashlib
from pathlib import Path
import sys
from tutorial import read,write

def export_raw(root,sid):
 root=Path(root);sys.path.insert(0,str(root/'.codex/skills/wanxiangqi-knowledge/scripts'))
 from workspace import store_lock
 from reference_store import stamp
 folder=root/'raw/sources'/sid.replace(':','_');raw=folder/'asr.raw.json'
 metadata=read(folder/'metadata.json');segments=read(raw)['segments']
 if not segments:raise ValueError('Missing raw ASR segments')
 lines=[f"# {metadata['title']}",'',f"来源：{metadata['url']}",'',f"分 P：{metadata.get('part',1)}",'',
        '全文按原始 ASR 段落顺序保存；未做人工修正，时间戳异常原样保留并标注。','']
 previous=0;previous_start=-1
 for segment in segments:
  a,b=segment['start'],segment['end']
  if not 0<=a<=b<=metadata.get('duration',b)+1:raise ValueError('Invalid raw transcript time range')
  if a<previous_start:lines+=['> 原始 ASR 时间戳小幅倒退，未调整。','']
  if a-previous>20:lines+=[f'> 转写间隔 {stamp(previous)}–{stamp(a)}：可能为静音或漏识别，未补写。','']
  lines += [f'## {stamp(a)}–{stamp(b)}','',segment['text'],'']
  previous=max(previous,b);previous_start=a
 text='\n'.join(lines)+'\n'
 with store_lock(root):
  index=read(root/'raw/index.json',{'schema_version':1,'sources':{}});entry=index['sources'].get(sid,{})
  target=root/'raw'/(folder.name+'.md')
  if target.exists():
   # Existing full transcript is retained, including earlier correction work.
   return target
  write(target,text)
  index['sources'][sid]={'path':target.relative_to(root).as_posix(),'transcript_file':'asr.raw.json','raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
  write(root/'raw/index.json',index)
 return target
