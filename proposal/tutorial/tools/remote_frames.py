"""Extract only requested evidence frames from an observed public media URL."""
import argparse,json,subprocess,sys,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'))
sys.path.insert(0,str(ROOT/'proposal/tutorial/tools'))
from media import ffmpeg
from wxq import atomic_json,read_json
from tutorial import existing_record

def run(source_id,annotations,workers=2):
 source=next(s for s in read_json(ROOT/'proposal/tutorial/batch.json') if s['id']==source_id)
 folder=ROOT/'raw/sources'/source_id.replace(':','_')
 if existing_record(ROOT,source):
  print('Existing tutorial record retained; no frame acquisition');return read_json(folder/'frames.json',[])
 j=read_json(ROOT/'raw/reports'/('observed-'+source_id.split(':')[0]+'.json'))
 manifest=read_json(folder/'frames.json',[]);known={x['time'] for x in manifest if (folder/x['path']).exists()}
 times=sorted({round(float(e['frame']),2) for e in read_json(annotations)['events']})
 def frame(t):
  if t in known:return None
  relative='frames/'+str(t).replace('.','-')+'.jpg';p=folder/relative;p.parent.mkdir(parents=True,exist_ok=True)
  error=''
  for attempt in range(2):
   try:
    result=subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-threads','1','-filter_threads','1','-user_agent','Mozilla/5.0','-headers','Referer: https://www.bilibili.com/\r\n','-ss',str(t),'-i',j['video'],'-frames:v','1','-vf','scale=1280:-2,format=yuvj420p','-threads','1','-y',str(p)],capture_output=True,timeout=90)
    if result.returncode==0 and p.exists() and p.stat().st_size>0:
     print(source_id,'frame',t,'ready',flush=True);return {'time':t,'path':relative,'reviewed':False,'observation':None,'acquisition':'observed-url-seek'}
    error=re.sub(r'https?://[^\s]+','[media-url]',result.stderr.decode('utf8','replace'))[-800:]
   except subprocess.TimeoutExpired:error='ffmpeg timeout after 90 seconds'
  print(source_id,'frame',t,'failed',error,flush=True);return None
 with ThreadPoolExecutor(max_workers=workers) as pool:
  for task in as_completed([pool.submit(frame,t) for t in times]):
   entry=task.result()
   if entry:
    manifest=sorted([x for x in manifest if x['time']!=entry['time']]+[entry],key=lambda x:x['time']);atomic_json(folder/'frames.json',manifest)
 return manifest
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('source_id');parser.add_argument('annotations',type=Path);parser.add_argument('--workers',type=int,default=2);args=parser.parse_args();run(args.source_id,args.annotations,args.workers)
