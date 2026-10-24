"""Audited schema6 migration. No old artifact is deleted before roundtrip checks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import zipfile
import json_document as document
import json_store as store


def build(root):
    import wxq, workspace, player_branches as branches
    root = Path(root).resolve()
    originals = store.read(root / 'knowledge/index.json')['notes']
    players = {e['id']: e['name'] for e in wxq.entities(root) if e['category'] == 'players'}
    items, aliases, links, audits = [], {}, {}, []
    for original in originals:
        variants = original.get('meta', {}).get('player_branches', []) if branches.enabled(original) else [None]
        for branch in variants:
            note = branches.project(original, branch['player']) if branch else deepcopy(original)
            path = branches.document_path(original, branch) if branch else original['path']
            text = (root / path).read_text('utf-8-sig')
            if document.markdown(document.parse(text)) != text:
                raise ValueError('Markdown无法无损还原：' + path)
            old_title = text.splitlines()[0][2:]
            if branch:
                player = branch['player']
                family = '常小娥灵活变阵' if original['id'] == 'changxiaoe-general-play' else original['title']
                title = family + '-' + players[player]
                nid = original['id'] if len(variants) == 1 else original['id'] + '--' + branch['id']
                note.update(id=nid, title=title, player_id=player, lineup_name=family,
                            path='knowledge/lineups/' + workspace.filename(title) + '.json',
                            migration={'note_id': original['id'], 'branch_id': branch['id'], 'old_path': path})
                aliases[original['id'] + '|' + player] = nid
                aliases[original['id'] + '|' + branch['id']] = nid
                aliases.setdefault(original['id'], nid)
                # Selection is knowledge too, not merely a management property.
                note.setdefault('meta', {})['selection'] = deepcopy(branch.get('selection', {}))
            else:
                note['path'] = str(Path(path).with_suffix('.json')).replace('\\', '/')
                nid = note['id'];title = note['title']
            note['aliases'] = list(dict.fromkeys([*note.get('aliases', []), *([original['title']] if title != original['title'] else [])]))
            text = '# ' + title + text[len('# ' + old_title):]
            links[path] = note['path']
            if original['path'] not in links:
                links[original['path']] = note['path']
            record = store.from_legacy(note, text)
            items.append(record)
            audits.append({'id': nid, 'old_path': path, 'path': note['path'], 'roundtrip': True,
                           'old_sha256': hashlib.sha256((root / path).read_bytes()).hexdigest(), 'title_changed': old_title != title})
    # Include every original claim, including preserved supporting material that
    # an old projection did not display, without reviving retired snapshots.
    for old in originals:
        assigned = [r for r in items if r['metadata'].get('migration', {}).get('note_id') == old['id'] or r['metadata']['id'] == old['id']]
        if not assigned:
            raise ValueError('笔记缺少迁移目标：' + old['id'])
        covered = {c.get('id') for r in assigned for c in r['metadata']['claim_annotations']}
        remaining = [c for c in old.get('claims', []) if c.get('id') not in covered]
        if remaining:
            extra = store.from_legacy({**old, 'claims': remaining, 'meta': {}, 'player_id': assigned[0]['metadata'].get('player_id')}, '# 临时\n')
            assigned[0]['body']['supporting_nodes'].extend(extra['body']['supporting_nodes'])
            assigned[0]['metadata']['claim_annotations'].extend(extra['metadata']['claim_annotations'])
    # Old export filenames are converted to canonical JSON targets. The UI
    # intercepts these links; exported Markdown retains meaningful local links.
    replacements = {}
    for old, new in links.items():
        replacements[Path(old).name] = Path(new).name
    def remap(value):
        if isinstance(value, str):
            return re.sub(r'(?<=\()([^\n)]+\.md)(?=\))', lambda m: str(Path(m[1]).parent / replacements.get(Path(m[1]).name, Path(m[1]).name)).replace('\\', '/'), value)
        if isinstance(value, list):return [remap(v) for v in value]
        if isinstance(value, dict):return {k: remap(v) for k, v in value.items()}
        return value
    for record in items:
        record['body'] = remap(record['body'])
        meta = record['metadata']
        for row in meta.get('related', []):
            row['id'] = aliases.get(row['id'], row['id'])
            target = next((r['metadata'] for r in items if r['metadata']['id'] == row['id']), None)
            if target:row.update(title=target['title'], path=target['path'])
        for row in meta.get('guide_related', []):
            key = row.get('note', '') + ('|' + row['player'] if row.get('player') else '')
            row['note'] = aliases.get(key, aliases.get(row.get('note'), row.get('note')))
            target = next((r['metadata'] for r in items if r['metadata']['id'] == row['note']), None)
            if target:row.update(title=target['title'], href='../' + Path(target['path']).parent.name + '/' + Path(target['path']).name)
        store.check_record(record)
    # Classify old archives before deletion. A non-current claim ID blocks
    # migration and needs semantic reconciliation, never automatic revival.
    current_ids = {c.get('id') for n in originals for c in n.get('claims', [])}
    archives = []
    for path in (root / 'knowledge/lineups').glob('*.json'):
        old = store.read(path, {})
        novel = [c.get('id') for c in old.get('claims', []) if c.get('id') not in current_ids]
        archives.append({'path': path.relative_to(root).as_posix(), 'classification': 'retired-generated-snapshot', 'unmerged_claim_ids': novel})
        if novel:raise ValueError('旧阵容档案有未归并结论：' + str(path))
    for directory in ('reviews', 'replays'):
        for path in (root / 'knowledge' / directory).glob('*.json'):
            data = store.read(path, {})
            active = [c for n in data.get('notes', []) if isinstance(n, dict) for c in n.get('claims', [])] if isinstance(data, dict) else []
            novel = [c.get('id') for c in active if c.get('id') not in current_ids]
            if novel:raise ValueError('审核或重放中存在待归并有效结论：' + str(path))
            archives.append({'path': path.relative_to(root).as_posix(), 'classification': 'audit-and-history' if directory=='reviews' else 'current-claims-replay-with-history', 'unmerged_claim_ids': novel})
    return items, aliases, {'schema_version': 6, 'notes_before': len(originals), 'notes_after': len(items), 'documents': audits,
                            'archives': archives, 'links': links, 'claims_before': len(current_ids),
                            'claims_after': len({c.get('id') for r in items for c in r['metadata']['claim_annotations']})}


MIGRATION = 'raw/knowledge/pending-json-migration.json'


def finish_cleanup(root):
    root = Path(root).resolve()
    state = store.read(root / MIGRATION)
    if not state:
        return None
    store.recover(root)
    from reference_store import _save_cards
    _save_cards(root, state['cards'])
    items = store.read(root / store.INDEX)['notes']
    keep = {r['path'] for r in items} | {store.meta_path(r['path']) for r in items} | {store.INDEX}
    keep.update(p.relative_to(root).as_posix() for p in (root / 'knowledge/cards').rglob('*.json') if p.name != 'index.json')
    for name in ('source-registry', 'document-sources'):
        old = root / ('knowledge/' + name + '.json')
        destination = root / ('knowledge/' + name + '.meta.json')
        if old.exists() and not destination.exists():
            store.write_file(destination, store.read(old))
        if destination.exists():
            keep.add(destination.relative_to(root).as_posix())
    for relative, expected in state['old_files'].items():
        if relative in keep:
            continue
        p = (root / relative).resolve()
        if not p.is_relative_to(root / 'knowledge'):
            raise ValueError('清理路径越界')
        if not p.exists():
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('迁移期间旧文件发生变化，已保留：' + relative)
        archive = root / 'raw/knowledge/retired' / p.relative_to(root / 'knowledge')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(p.read_bytes())
        p.unlink()
    report = state['report']
    report['validation'] = store.validate(root)
    store.write_file(root / 'raw/reports/json-v6/migration-report.json', report)
    (root / MIGRATION).unlink()
    return report


def migrate(root, apply=False):
    import workspace, wxq
    root = Path(root).resolve()
    out = root / 'raw/reports/json-v6'
    out.mkdir(parents=True, exist_ok=True)
    if store.enabled(root):
        if not apply:
            return store.validate(root)
        with workspace.store_lock(root, wait=True):
            store.recover(root)
            return finish_cleanup(root) or store.validate(root)
    with workspace.store_lock(root, wait=True):
        workspace.recover(root)
        import markdown_sync
        markdown_sync.assert_clean(root)
        items, aliases, report = build(root)
        store.write_file(out / 'migration-report.json', report)
        if not apply:
            return report
        old_files = [p for p in (root / 'knowledge').rglob('*') if p.is_file()]
        with zipfile.ZipFile(out / ('migration-' + wxq.uuid.uuid4().hex + '.zip'), 'x', zipfile.ZIP_DEFLATED) as archive:
            for p in old_files:
                archive.write(p, p.relative_to(root))
        cards = store.read(root / 'knowledge/cards/index.json', {}).get('cards', [])
        state = {'report': report, 'cards': cards, 'old_files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in old_files}}
        store.write_file(root / MIGRATION, state)
        store.save(root, items, aliases)
        return finish_cleanup(root)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = migrate(args.root, args.apply)
    print(json.dumps({k: v for k, v in result.items() if k not in ('documents', 'archives', 'links')}, ensure_ascii=False))
