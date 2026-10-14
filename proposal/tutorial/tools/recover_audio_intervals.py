"""Recover damaged audio as independently validated, time-located PCM intervals."""
import argparse,json,subprocess,sys,wave
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'));sys.path.insert(0,str(ROOT/'proposal/tutorial/tools'))
from media import ffmpeg,validate_audio_duration
from tutorial import read,write,existing_record

def run(sid,workers=2):
 source=next(s for s in read(ROOT/'proposal/tutorial/batch.json') if s['id']==sid)
 if existing_record(ROOT,source):return
 f=ROOT/'raw/sources'/sid.replace(':','_');j=read(ROOT/'raw/reports'/('observed-'+source['bvid']+'.json'));duration=j['source']['duration'];d=f/'audio-intervals';d.mkdir(exist_ok=True)
 def valid(p,n,last):
  try:
   with wave.open(str(p),'rb') as w:actual=w.getnframes()/w.getframerate()
   return abs(actual-n)<(.99 if last else .1)
  except (OSError,EOFError,wave.Error):return False
 def get(t):
  n=min(20,duration-t);last=t+n==duration;p=d/(str(t)+'.wav')
  if valid(p,n,last):return t,p
  for attempt in range(3):
   try:
    result=subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-user_agent','Mozilla/5.0','-headers','Referer: https://www.bilibili.com/\r\n','-ss',str(t),'-i',j['audio'],'-t',str(n),'-ar','16000','-ac','1','-c:a','pcm_s16le','-y',str(p)],capture_output=True,timeout=45)
    if result.returncode==0 and valid(p,n,last):return t,p
   except subprocess.TimeoutExpired:pass
  return t,None
 rows=[]
 with ThreadPoolExecutor(max_workers=workers) as pool:
  for index,row in enumerate(pool.map(get,range(0,duration,20)),1):
   rows.append(row)
   if index%10==0:print(sid,'audio intervals',index,'of',(duration+19)//20,flush=True)
 missing=[t for t,p in rows if not p];write(f/'audio-interval-recovery.json',{'interval_seconds':20,'missing_starts':missing,'validated_intervals':len(rows)-len(missing)})
 if missing:print(sid,'missing audio intervals',len(missing),flush=True);return
 output=f/'audio-recovered.wav'
 with wave.open(str(output),'wb') as out:
  out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000)
  for _,p in rows:
   with wave.open(str(p),'rb') as w:out.writeframes(w.readframes(w.getnframes()))
 with wave.open(str(output),'rb') as w:decoded=w.getnframes()/w.getframerate()
 validate_audio_duration(ROOT,sid,decoded);write(f/'audio-interval-ready.json',{'path':str(output),'bytes':output.stat().st_size,'complete':True,'decoded_duration':decoded,'interval_seconds':20});print(sid,'complete audio recovered',decoded,flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('source_id');args=parser.parse_args();run(args.source_id)
