"""Apply an explicitly reviewed, segment-local correction ledger, preserving raw ASR."""
import argparse
import hashlib
from pathlib import Path
from tutorial import ROOT, read, write


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source_id')
    p.add_argument('ledger', type=Path)
    args = p.parse_args()
    folder = ROOT / 'raw/sources' / args.source_id.replace(':', '_')
    raw = folder / 'asr.raw.json'
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    corrected = read(folder / 'asr.corrected.json')
    corrections = read(folder / 'corrections.json', [])
    for change in read(args.ledger):
        segment = next(s for s in corrected['segments'] if s['id'] == change['segment'])
        if change['original'] not in segment['text']:
            if any(c.get('segment') == change['segment'] and c.get('original') == change['original']
                   and c.get('standard') == change['standard'] for c in corrections):
                continue
            raise ValueError('Original token missing: ' + change['original'])
        if not change.get('reason') or not change.get('evidence'):
            raise ValueError('Correction must have evidence and reason')
        segment['text'] = segment['text'].replace(change['original'], change['standard'])
        corrections.append({**change, 'start': segment['start'], 'status': 'confirmed',
                            'scope': 'segment-local; no global alias update'})
    write(folder / 'asr.corrected.json', corrected)
    write(folder / 'corrections.json', corrections)
    assert before == hashlib.sha256(raw.read_bytes()).hexdigest()
    print('Reviewed corrections saved; raw ASR unchanged')


if __name__ == '__main__':
    main()
