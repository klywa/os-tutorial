"""Coverage accounting for source-led scenario discovery."""
import re


def source_segments(source):
    segments = []
    for match in re.finditer(r'(?m)^[^\S\n]*\S[^\n]*(?:\n[^\S\n]*\S[^\n]*)*', source):
        line = source.count('\n', 0, match.start()) + 1
        segments.append({'id': f's{line}', 'line': line, 'text': match[0]})
    return segments


def validate_coverage(dispositions, segments, points):
    accepted = {}
    attributed = set()
    by_id = {segment['id']: segment for segment in segments}
    if not isinstance(dispositions, list):
        raise ValueError('逐段覆盖 coverage 须为列表')
    for row in dispositions:
        if not isinstance(row, dict):
            raise ValueError('逐段记录须为对象')
        sid = row.get('segment_id')
        if not isinstance(sid, str) or sid not in by_id or sid in accepted:
            raise ValueError(f'逐段记录的段落 ID 未知或重复：{sid}')
        reason = row.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'{sid} 需要写明发现或排除的理由')
        pids = row.get('point_ids')
        if not isinstance(pids, list) or any(not isinstance(pid, str) or pid not in points for pid in pids):
            raise ValueError(f'{sid} 引用了无效知识点')
        for pid in pids:
            point = points[pid]
            if not any(ref['quote'] in by_id[sid]['text'] for ref in point['source_refs'] + point.get('related_refs', [])):
                raise ValueError(f'{sid} 缺少 {pid} 的对应原文引句')
        accepted[sid] = row
        attributed.update(pids)
    missing = [f"第 {row['line']} 行" for row in segments if row['id'] not in accepted]
    if missing:
        raise ValueError('以下原文段落缺少覆盖记录：' + '、'.join(missing))
    if points.keys() - attributed:
        raise ValueError('以下知识点未关联原文段落：' + '、'.join(sorted(points.keys() - attributed)))


def report(segments, dispositions, branches, links, discovered_links, duplicates, refinements):
    groups_by_point = {}
    for gid, sentences in links.items():
        pid = next(iter(sentences.values()))['point_id']
        groups_by_point.setdefault(pid, []).append(gid)
    for gid, kept in duplicates.items():
        pid = next(iter(discovered_links[gid].values()))['point_id']
        groups_by_point.setdefault(pid, []).append(kept)
    outcomes = {}
    for pid, branch in branches.items():
        if 'seed' in branch:
            continue
        outcomes[pid] = {'groups': list(dict.fromkeys(groups_by_point.get(pid, []))),
                         'evidence_kind': branch['point'].get('evidence_kind', 'note'),
                         'events': [{'id': event['id'], 'event': event['event']} for event in branch['events']['events']],
                         'rejected_events': branch['conditions'].get('rejected', []),
                         'excluded_events': branch['events'].get('excluded', []),
                         'unselected_conditions': [row['condition_id'] for row in branch['phrases']['groups']
                                                   if not row['selected']]}
    by_id = {row['segment_id']: row for row in dispositions}
    seed_sources = [(branch['seed']['id'], [ref['quote'] for ref in branch['enrich']['source_refs']])
                    for branch in branches.values() if 'seed' in branch]
    return {'segments': [{**{k: v for k, v in segment.items() if k != 'text'}, **by_id[segment['id']],
                          'seed_group_ids': [gid for gid, quotes in seed_sources if any(
                              quote in segment['text'] for quote in quotes)]}
                         for segment in segments], 'points': outcomes, 'refinements': refinements}
