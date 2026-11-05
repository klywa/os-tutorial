"""Private scheduled official-card worker. Never runs inside the HTTP service."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import official_sync
import wxq
import json_store as store
from processing_lock import file_lock
from workspace import Busy,store_lock
from card_publication import home, publish, prune_versions, CLOCK


def tick(state,force=False,bundle_root=None):
    folder=home(state);workspace=folder/'workspace'
    with file_lock(folder/'worker.lock'):
        if bundle_root and not (folder/'current.json').exists():publish(bundle_root,state,bundled=True)
        if not store.enabled(workspace):store.initialize(workspace)
        with store_lock(workspace,wait=True):official_sync.recover(workspace,apply_notes=False)
        previous=store.read(folder/'status.json',{})
        # Failed publication retries independently of a successful upstream fetch.
        needed=force or official_sync.due(workspace,CLOCK)
        if not needed and official_sync.status(workspace,CLOCK).get('state')=='failed':return previous
        if not needed and previous.get('state')=='success' and (folder/'current.json').exists():
            prune_versions(state)
            return previous
        value={**previous,'state':'running','last_check':wxq.now(),'error':None}
        wxq.atomic_json(folder/'status.json',value)
        try:
            if needed:official_sync.run(workspace,CLOCK,apply_notes=False)
            version=publish(workspace,state)
            value.update(state='success',version=version,last_success=wxq.now(),error=None)
            wxq.atomic_json(folder/'status.json',value)
            return value
        except Exception as exc:
            value.update(state='failed',error=str(exc))
            wxq.atomic_json(folder/'status.json',value)
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--state-dir',type=Path,default=Path('/var/lib/os-tutorial'))
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    try:print(tick(args.state_dir,args.force,bundle_root=ROOT))
    except Busy:print('Official card worker already running; skipped.')
