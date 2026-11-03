"""Explicit, backed-up, transactional history migration; defaults to dry-run."""
import argparse
from pathlib import Path
import json
import shutil
import uuid
import json_store as store
import knowledge_history as history
from workspace import store_lock

def migrate(root, *, apply=False):
    root=Path(root)
    with store_lock(root,wait=True):
        if store.pending_save(root):
            if not apply: raise ValueError('Pending transaction; recover before dry-run')
            store.recover(root)
        records=store.records(root)
        writes=[]; mapping=[]
        for record in records:
            nid=record['metadata']['id']
            import note_review
            for path in note_review.version_folder(root,nid).glob('*.json'):
                if path.name=='index.meta.json': continue
                value=store.read(path)
                if value.get('note_id')!=nid: raise ValueError('Version identity mismatch')
                entry=history.version_write(value); writes.append(entry)
                mapping.append({'old':path.relative_to(root).as_posix(),'new':entry['path'],'version_id':value['id']})
        report={'storage_version':2,'notes':len(records),'legacy_history_entries':sum(len(r['metadata'].get('history',[])) for r in records),
                'versions':len(writes),'archive_bytes':sum(len(json.dumps(w['value'],ensure_ascii=False).encode('utf-8')) for w in writes), 'mapping':mapping}
        if not apply or history.enabled(root): return report
        backup=root/'raw/backups/history-migration'/uuid.uuid4().hex
        backup.mkdir(parents=True)
        shutil.copytree(root/'knowledge',backup/'knowledge')
        if (root/'raw/knowledge/versions').exists(): shutil.copytree(root/'raw/knowledge/versions',backup/'versions')
        journal=store.save(root,records,origin='history_migration',prepare_only=True,storage_version=2)
        journal['archives']=writes+journal.get('archives',[])
        # Immutable per-note mapping also preserves old numeric history_index positions.
        for record in records:
            nid=record['metadata']['id']
            value={'note_id':nid,'version_mapping':[m for m in mapping if m['old'].startswith(note_review.version_folder(root,nid).relative_to(root).as_posix()+'/')],
                   'history_index_count':len(record['metadata'].get('history',[]))}
            journal['archives'].append({'path':history.folder(nid)+'/migrations/'+store.digest(value)+'.json','value':value})
        store.write_file(backup/'report.json',report)
        store.write_file(root/store.JOURNAL,journal)
        store.recover(root)
        return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(migrate(args.root,apply=args.apply),ensure_ascii=False,indent=2))
