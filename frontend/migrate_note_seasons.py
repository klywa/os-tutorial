"""Backfill explicit S1 on existing formal notes using the normal knowledge transaction."""
import argparse
from pathlib import Path

from server import ROOT
import json_store as store
from workspace import store_lock


def migrate(root):
    root = Path(root)
    with store_lock(root, wait=True):
        store.recover(root)
        pending = []
        for record in store.records(root):
            metadata = record['metadata']
            if 'seasons' not in metadata:
                metadata['seasons'] = ['S1']
                pending.append(record)
        if pending:
            store.save(root, pending, origin='season_backfill', partial=True)
        return len(pending)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(f'Migrated {migrate(args.root)} notes')
