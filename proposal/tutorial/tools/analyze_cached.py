"""Persist the manually reviewed annotation input; not an automatic semantic classifier."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tutorial import ROOT, read, write, save_record, state, existing_record


def main():
    p = Path(sys.argv[1])
    annotations = read(p)
    sid = annotations['source_id']
    batch_source = next(s for s in read(ROOT / 'proposal/tutorial/batch.json') if s['id'] == sid)
    if existing_record(ROOT, batch_source):
        print('Existing tutorial record retained; no analysis or asset writes')
        return
    folder = ROOT / 'raw/sources' / sid.replace(':', '_')
    source = read(folder / 'metadata.json')
    transcript_file = annotations.get('transcript_file', 'asr.corrected.json')
    if transcript_file not in ('asr.raw.json', 'asr.corrected.json'):
        raise ValueError('Invalid transcript filename')
    transcript = read(folder / transcript_file)
    by_id = {s['id']: s for s in transcript['segments']}
    frames = read(folder / 'frames.json')
    events = []
    for n, a in enumerate(annotations['events'], 1):
        seg_ids = a['segments']
        text = ''.join(by_id[i]['text'] for i in seg_ids)
        if a['quote'] not in text:
            raise ValueError('Quote does not occur in corrected ASR: ' + a['quote'])
        frame = next(f for f in frames if f['time'] == a['frame'])
        image = folder / frame['path']
        if not image.exists():
            raise ValueError('Missing frame: ' + str(image))
        start, end = by_id[seg_ids[0]]['start'], by_id[seg_ids[-1]]['end']
        if max(start - a['frame'], a['frame'] - end, 0) > 15:
            raise ValueError('Frame must be within 15 seconds of cited teaching')
        dest = ROOT / 'proposal/tutorial/assets' / sid.replace(':', '_') / image.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, dest)
        frame['reviewed'] = True
        frame['observation'] = a['observation']
        # Frame in a short transition gap may extend the evidence interval; record explicitly.
        start, end = min(start, a['frame']), max(end, a['frame'])
        events.append({'id': sid + ':e' + str(n).zfill(3), 'start': start, 'end': end,
                       'scene': a['scene'], 'timing': a['timing'], 'content': a['content'],
                       'background': {'text': a['background'], 'basis': a.get('background_basis', '明确说明')},
                       'goal': {'text': a['goal'], 'basis': '分析推断'},
                       'quote': a['quote'], 'segment_ids': seg_ids, 'template_id': a['template'],
                       'screenshots': [{'path': dest.relative_to(ROOT / 'proposal').as_posix(),
                                        'time': a['frame'], 'reviewed': True,
                                        'observation': a['observation'],
                                        'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}]})
    record = {'schema_version': 1, 'source': source, 'status': 'completed',
              'review': {'full_transcript_read': annotations['full_transcript_read'],
                         'checked_intervals': annotations['checked_intervals'],
                         'notes': annotations['review_notes']},
              'events': events, 'unresolved': annotations['unresolved'],
              'transcript_file': transcript_file,
              'transcript_sha256': hashlib.sha256((folder / transcript_file).read_bytes()).hexdigest()}
    dest = save_record(ROOT, record)
    write(folder / 'frames.json', frames)
    state(ROOT, sid, 'completed', material_reused=annotations.get('material_reused', False),
          note='已完整阅读 ASR，逐条核对所引用截图；学习目标为分析判断。')
    print(json.dumps({'record': str(dest), 'events': len(events)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
