"""Persistent topic extraction runs independently of HTTP and ASR processes."""
import argparse,time,traceback
from pathlib import Path
from topics import TopicStore,catalog,fingerprint,encode
from crawler import Store,source_rows
from topic_model import LocalModel
from reference_store import transcript_errors,repair_transcript_index
from processing_lock import file_lock
import workspace,wxq

def run(root):
 root=Path(root);topics=TopicStore(root);queue=Store(root);model=LocalModel(root)
 with file_lock(root/'raw/crawler/topic-runtime.lock'):
  with topics.db() as db:db.execute("UPDATE topic_tasks SET state='queued' WHERE state='running'")
  scanned=0
  try:
   while True:
    if time.monotonic()-scanned>=20:
     try:topics.sync(source_rows(root,queue));scanned=time.monotonic()
     except Exception:
      with (root/'raw/crawler/topic-worker.log').open('a',encoding='utf-8') as log:traceback.print_exc(file=log)
      time.sleep(5);continue
    task=topics.claim()
    if not task:
     if model.process and time.monotonic()-model.last_used>300:model.close()
     time.sleep(1);continue
    try:
     rows={r['id']:r for r in source_rows(root,queue)};row=rows.get(task['source'])
     if not row or row.get('ignored') or fingerprint(row)!=task['fingerprint']:
      topics.sync(list(rows.values()));continue
     errors=[e for e in transcript_errors(root,row['id']) if not e.startswith('Transcript was manually edited')]
     if any(e.startswith('Transcript index needs verification') for e in errors):
      repair_transcript_index(root,row['id'])
      errors=[e for e in transcript_errors(root,row['id']) if not e.startswith('Transcript was manually edited')]
     if errors:raise ValueError('文字稿需核验，未进行主题提取：'+'; '.join(errors))
     text=Path(row['transcript_path']).read_text('utf-8')
     def cancelled():
      if topics.setting('paused'):return True
      with topics.db() as db:r=db.execute('SELECT generation,state FROM topic_tasks WHERE source=?',(task['source'],)).fetchone()
      return not r or r['generation']!=task['generation'] or r['state']!='running'
     def progress(value):
      with topics.db() as db:db.execute('UPDATE topic_tasks SET progress=? WHERE source=? AND generation=?',(encode(value),task['source'],task['generation']))
     result=model.extract(row.get('title',''),text,catalog(root)['topic_players'],progress,cancelled)
     if cancelled():raise InterruptedError()
     with workspace.store_lock(root,wait=True):
      current=next((r for r in source_rows(root,queue) if r['id']==task['source']),None)
      if not current or current.get('ignored') or fingerprint(current)!=task['fingerprint']:
       topics.sync(source_rows(root,queue));continue
      topics.finish(task,result)
    except InterruptedError:
     with topics.db() as db:db.execute("UPDATE topic_tasks SET state='queued' WHERE source=? AND generation=? AND state='running'",(task['source'],task['generation']))
    except Exception as exc:
     topics.finish(task,{},str(exc))
  finally:model.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
 try:run(args.root)
 except workspace.Busy:pass
