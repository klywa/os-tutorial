"""Disposable local source/staging fixture; never opens the project's knowledge store."""
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store,server,wxq

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='source-staging-',dir=ROOT/'temp') as folder:
  root=Path(folder);json_store.initialize(root)
  rows=[{'id':f'BV{n:010}:p1','url':f'https://www.bilibili.com/video/BV{n:010}',
         'title':f'教学 {n:02}','notes':f'备注 {n:02}','updated_at':f'2026-11-02T00:00:{n:02}'} for n in range(1,31)]
  wxq.atomic_json(root/'knowledge/source-registry.json',rows)
  manifest={}
  for row in rows:
   relative='raw/'+row['id'].replace(':','_')+'.md'
   wxq.atomic_text(root/relative,'文字稿 '+row['title']);manifest[row['id']]={'path':relative}
  wxq.atomic_json(root/'raw/index.json',{'sources':manifest})
  http=server.create_server(root,0)
  print(json.dumps({'port':http.server_port,'root':str(root)}),flush=True)
  try:http.serve_forever()
  finally:http.server_close()
