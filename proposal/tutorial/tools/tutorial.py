"""Evidence-backed tutorial records and offline report CLI (stdlib only)."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCENES = ('前置讲解', '模拟演示', '实战')
BASES = ('明确说明', '分析推断')


def read(path, default=None):
    return json.loads(Path(path).read_text('utf-8-sig')) if Path(path).exists() else default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text('utf8') == text:
        return
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=path.parent, delete=False) as out:
        out.write(text)
        temporary = Path(out.name)
    temporary.replace(path)


def identity(url):
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('www.bilibili.com', 'bilibili.com'):
        raise ValueError('Only supplied HTTPS Bilibili video URLs are supported')
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', parsed.path)
    if not match:
        raise ValueError('Invalid BVID video path')
    part = int(parse_qs(parsed.query).get('p', ['1'])[0])
    if part < 1:
        raise ValueError('Invalid part')
    return f'{match[1]}:p{part}'


def records(root):
    found = {}
    for p in sorted((Path(root) / 'proposal/tutorial/records').glob('*.json')):
        r = read(p)
        sid = r.get('source', {}).get('id')
        if sid in found:
            raise ValueError('Duplicate source records: ' + sid)
        if sid:
            found[sid] = (p, r)
    return found


def safe_title(title):
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '－', title).rstrip(' .')[:110]
    if not title or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', title):
        title = '视频－' + (title or '未命名')
    return title


def existing_record(root, source):
    """Common no-reacquisition barrier for JSON and legacy Markdown."""
    existing = records(root).get(source['id'])
    if existing:
        return {'id': source['id'], 'status': existing[1].get('status'), 'reused_record': True,
                'issues': validate_record(root, existing[1])}
    folder = Path(root) / 'proposal/tutorial/records'
    for title in {source.get('title', ''), source.get('requested_title', '')} - {''}:
        if (folder / (safe_title(title) + '.md')).exists():
            return {'id': source['id'], 'status': 'pending', 'reused_record': True,
                    'issues': ['Markdown-only legacy record retained']}
    return None


def inside(base, relative):
    p = Path(relative)
    if p.is_absolute() or '\\' in relative or '..' in p.parts:
        raise ValueError('Unsafe relative path')
    resolved = (Path(base) / p).resolve()
    if not resolved.is_relative_to(Path(base).resolve()):
        raise ValueError('Path escapes evidence directory')
    return resolved


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_record(root, record):
    errors = []
    source = record.get('source', {})
    sid = source.get('id', '')
    try:
        if identity(source.get('url', '')) != sid:
            errors.append('Source URL and ID differ')
    except (ValueError, TypeError):
        errors.append('Invalid source URL')
    if record.get('schema_version') != 1:
        errors.append('Unsupported record schema; retain legacy record without reanalysis')
    if record.get('status') not in ('pending', 'in_progress', 'completed', 'failed'):
        errors.append('Invalid analysis status')
    if record.get('status') != 'completed':
        return errors
    duration = source.get('duration')
    if not number(duration) or duration <= 0:
        return errors + ['Completed source requires duration']
    review = record.get('review', {})
    intervals = review.get('checked_intervals', [])
    if review.get('full_transcript_read') is not True:
        errors.append('Full transcript not read')
    if not isinstance(record.get('events'), list):
        return errors + ['Missing events list']
    transcript_file = record.get('transcript_file', 'asr.corrected.json')
    if transcript_file not in ('asr.raw.json', 'asr.corrected.json'):
        return errors + ['Invalid transcript filename']
    transcript_path = Path(root) / 'raw/sources' / sid.replace(':', '_') / transcript_file
    transcript = read(transcript_path, {})
    segments = {s['id']: s for s in transcript.get('segments', [])}
    if not segments:
        errors.append('Missing or empty corrected ASR evidence')
    if transcript_path.exists() and record.get('transcript_sha256'):
        if hashlib.sha256(transcript_path.read_bytes()).hexdigest() != record['transcript_sha256']:
            errors.append('Corrected ASR changed after event review')
    ids = set()
    for e in record['events']:
        eid = e.get('id', '')
        if not eid.startswith(sid + ':e') or eid in ids:
            errors.append('Invalid or duplicate event ID: ' + eid)
        ids.add(eid)
        start, end = e.get('start'), e.get('end')
        if not number(start) or not number(end) or not 0 <= start < end <= duration:
            errors.append('Invalid event interval: ' + eid)
            continue
        if not any(isinstance(i, list) and len(i) == 2 and all(number(v) for v in i)
                   and 0 <= i[0] <= start and end <= i[1] <= duration for i in intervals):
            errors.append('Event not covered by reviewed interval: ' + eid)
        if e.get('scene') not in SCENES:
            errors.append('Invalid scene: ' + eid)
        for key in ('timing', 'content', 'quote', 'template_id'):
            if not isinstance(e.get(key), str) or not e[key].strip():
                errors.append('Missing ' + key + ': ' + eid)
        if not re.fullmatch(r'[a-z0-9-]+', e.get('template_id', '')):
            errors.append('Unsafe template ID: ' + eid)
        referenced = []
        if not e.get('segment_ids'):
            errors.append('Missing ASR segment references: ' + eid)
        elif segments:
            referenced = [segments.get(i) for i in e['segment_ids']]
            if any(s is None for s in referenced):
                errors.append('ASR reference not found: ' + eid)
            elif e.get('quote', '') not in ''.join(s['text'] for s in referenced):
                errors.append('Quote differs from referenced corrected ASR: ' + eid)
            elif any(not start <= s['start'] < s['end'] <= end for s in referenced):
                errors.append('Referenced ASR outside event interval: ' + eid)
        for key in ('background', 'goal'):
            if not e.get(key, {}).get('text') or e.get(key, {}).get('basis') not in BASES:
                errors.append('Missing evidence basis for ' + key + ': ' + eid)
        if not e.get('screenshots'):
            errors.append('Missing screenshot: ' + eid)
        for image in e.get('screenshots', []):
            try:
                p = inside(Path(root) / 'proposal', image.get('path', ''))
                if not p.is_relative_to((Path(root) / 'proposal/tutorial/assets').resolve()) or not p.is_file():
                    errors.append('Missing or unsafe screenshot: ' + eid)
                elif image.get('sha256') and hashlib.sha256(p.read_bytes()).hexdigest() != image['sha256']:
                    errors.append('Screenshot differs from reviewed image: ' + eid)
            except (ValueError, TypeError):
                errors.append('Unsafe screenshot: ' + eid)
            t = image.get('time')
            if not number(t) or not start <= t <= end:
                errors.append('Screenshot outside event interval: ' + eid)
            elif referenced and all(s is not None for s in referenced):
                gap = min(max(s['start'] - t, t - s['end'], 0) for s in referenced)
                if gap > 15:
                    errors.append('Screenshot too far from cited teaching (max 15s): ' + eid)
            if image.get('reviewed') is not True or not image.get('observation'):
                errors.append('Screenshot not reviewed: ' + eid)
    return errors


def clock(seconds):
    return f'{int(seconds)//60:02d}:{int(seconds)%60:02d}'


def markdown(record):
    s = record['source']
    lines = ['# ' + s['title'], '', '来源：' + s['url'], '', '分析状态：' + record['status'], '',
             '完整文字稿：../../../raw/' + s['id'].replace(':', '_') + '.md', '']
    for e in record.get('events', []):
        lines += ['## ' + clock(e['start']) + '–' + clock(e['end']) + ' ' + e['content'], '',
                  '- 事件 ID：' + e['id'], '- 场景：' + e['scene'], '- 时机：' + e['timing'],
                  '- 背景（' + e['background']['basis'] + '）：' + e['background']['text'],
                  '- 学习目标（' + e['goal']['basis'] + '）：' + e['goal']['text'],
                  '- 模板：' + e['template_id'], '- ASR 段落：' + str(e['segment_ids']), '',
                  '> ' + e['quote'].replace('\n', '\n> '), '']
        for image in e.get('screenshots', []):
            lines += ['![' + image['observation'] + '](../assets/' + image['path'].split('assets/', 1)[1] + ')', '']
    lines += ['## 待核实与局限', ''] + ['- ' + str(u) for u in record.get('unresolved', [])]
    return '\n'.join(lines) + '\n'


def save_record(root, record):
    errors = validate_record(root, record)
    if errors:
        raise ValueError('\n'.join(errors))
    sid = record['source']['id']
    existing = records(root).get(sid)
    if existing:
        if existing[1] == record:
            return existing[0]
        raise ValueError('Existing record preserved; explicitly review edits in place instead of reanalysis')
    folder = Path(root) / 'proposal/tutorial/records'
    name = safe_title(record['source']['title'])
    path = folder / (name + '.json')
    if path.exists() or path.with_suffix('.md').exists():
        path = folder / (name + '－' + sid.replace(':', '_') + '.json')
    write(path, record)
    write(path.with_suffix('.md'), markdown(record))
    return path


def state(root, sid, status, **details):
    path = Path(root) / 'proposal/tutorial/status.json'
    data = read(path, {})
    data[sid] = {'status': status, **details}
    write(path, data)
    return data[sid]


def prepare_source(root, source, acquire=None, reuse_root=None, model='large-v3'):
    root = Path(root)
    sid = source['id']
    if not re.fullmatch(r'BV[0-9A-Za-z]{10}:p[1-9][0-9]*', sid):
        raise ValueError('Invalid source ID')
    existing = existing_record(root, source)
    if existing:
        return existing
    folder = root / 'raw/sources' / sid.replace(':', '_')
    cached = False
    if reuse_root:
        old = Path(reuse_root) / 'raw/sources' / sid.replace(':', '_')
        if old.exists():
            folder.mkdir(parents=True, exist_ok=True)
            for p in old.rglob('*'):
                dest = folder / p.relative_to(old)
                if p.is_file() and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
            cached = True
    if (folder / 'asr.corrected.json').exists() and (folder / 'frames.json').exists():
        return state(root, sid, 'in_progress', material_reused=True,
                     stage='prepared', note='等待完整逐段阅读、纠正和教学帧核对') | {'id': sid}
    state(root, sid, 'in_progress', stage='acquisition', material_reused=cached)
    try:
        if acquire is None:
            sys.path.insert(0, str(root / '.codex/skills/wanxiangqi-knowledge/scripts'))
            from media import prepare
            acquire = lambda r, s: prepare(r, s['url'], model=model)
        result = acquire(root, source)
        if any(p.get('stage') == 'failed' for p in result):
            raise RuntimeError('; '.join(p.get('error', '') for p in result if p.get('stage') == 'failed'))
        return state(root, sid, 'in_progress', stage='prepared', material_reused=cached) | {'id': sid}
    except Exception as exc:
        return state(root, sid, 'failed', stage='acquisition', error=str(exc), material_reused=cached) | {'id': sid}


def aggregate(root, sources, templates):
    saved = records(root)
    states = read(Path(root) / 'proposal/tutorial/status.json', {})
    output, events, issues = [], [], []
    for source in sources:
        sid = source['id']
        row = {**source, **states.get(sid, {'status': 'pending'})}
        if sid in saved:
            path, r = saved[sid]
            problems = validate_record(root, r)
            row.update(r['source'])
            row.update(status=r.get('status', 'pending'), record_path=path.relative_to(Path(root) / 'proposal').as_posix())
            row['issues'] = problems + r.get('unresolved', [])
            if problems:
                row['status'] = 'invalid_record'
            elif row['status'] == 'completed':
                events += [{**e, 'source_id': sid, 'title': row['title'], 'author': row.get('author', '未知')}
                           for e in r['events']]
            issues += [{'source_id': sid, 'text': str(p)} for p in row['issues']]
        else:
            legacy = Path(root) / 'proposal/tutorial/records' / (safe_title(source['title']) + '.md')
            if legacy.exists():
                row['issues'] = ['已有 Markdown 记录缺结构化数据，保留且不重新分析']
                issues.append({'source_id': sid, 'text': row['issues'][0]})
        output.append(row)
    grouped = defaultdict(list)
    for e in events:
        grouped[e['template_id']].append(e)
    definitions = {t['id']: t for t in templates}
    result = []
    for tid, examples in sorted(grouped.items()):
        fallback = {'id': tid, 'title': examples[0]['content'], 'trigger': examples[0]['timing'],
                    'teach': examples[0]['content'], 'goal': examples[0]['goal']['text'],
                    'conditions': '仅在示例所述条件下适用；跨视频泛化待补证', 'priority': '待验证',
                    'recommendation': '先说明条件，再解释操作与理由。'}
        result.append({**fallback, **definitions.get(tid, {}), 'event_ids': [e['id'] for e in examples],
                       'event_count': len(examples), 'video_count': len({e['source_id'].split(':')[0] for e in examples}),
                       'author_count': len({e['author'] for e in examples}),
                       'scenes': dict(Counter(e['scene'] for e in examples))})
    completed = [s for s in output if s['status'] == 'completed']
    stats = {'planned': len(output), 'planned_videos': len({s['id'].split(':')[0] for s in output}),
             'completed': len(completed), 'failed': sum(s['status'] == 'failed' for s in output),
             'pending': sum(s['status'] in ('pending', 'in_progress') for s in output),
             'invalid_records': sum(s['status'] == 'invalid_record' for s in output),
             'material_reused': sum(bool(s.get('material_reused')) for s in output),
             'events': len(events), 'templates': len(result),
             'duration': sum(s.get('duration', 0) for s in completed),
             'scenes': dict(Counter(e['scene'] for e in events)),
             'authors': dict(Counter(s.get('author', '未知') for s in completed))}
    summary = read(Path(root) / 'proposal/tutorial/synthesis.json', {'conclusions': [], 'limitations': []})
    valid_ids = {e['id'] for e in events}
    for conclusion in summary.get('conclusions', []):
        refs = conclusion.get('event_ids', [])
        if not refs or any(ref not in valid_ids for ref in refs):
            raise ValueError('Conclusion must reference validated completed events')
    return {'stats': stats, 'sources': output, 'events': events, 'templates': result,
            'issues': issues, 'synthesis': summary}


def render_report(data):
    template = Path(__file__).with_name('report.html').read_text('utf8')
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return template.replace('@@DATA@@', payload)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('render')
    sub.add_parser('validate')
    sub.add_parser('register')
    prep = sub.add_parser('prepare')
    prep.add_argument('source_id')
    prep.add_argument('--reuse-root', type=Path)
    prep.add_argument('--model', default='large-v3')
    save = sub.add_parser('save-record')
    save.add_argument('file', type=Path)
    args = p.parse_args()
    base = args.root / 'proposal/tutorial'
    sources = read(base / 'batch.json', [])
    if args.command == 'prepare':
        result = prepare_source(args.root, next(s for s in sources if s['id'] == args.source_id),
                                reuse_root=args.reuse_root, model=args.model)
    elif args.command == 'save-record':
        result = {'path': str(save_record(args.root, read(args.file)))}
    elif args.command == 'register':
        sys.path.insert(0, str(args.root / '.codex/skills/wanxiangqi-knowledge/scripts'))
        import workspace, wxq
        with workspace.store_lock(args.root):
            workspace.recover(args.root)
            pending = wxq.read_json(args.root / 'knowledge/pending-commit.json')
            if pending:
                wxq._commit_notes(args.root, pending['notes'])
        existing = {s['id'] for s in workspace.sources(args.root)}
        for s in sources:
            if s['id'] not in existing:
                workspace.register_source(args.root, {'url': s['url'], 'title': s['title']})
        result = {'registered': len(sources)}
    else:
        data = aggregate(args.root, sources, read(base / 'templates.json', []))
        if args.command == 'validate':
            result = {'stats': data['stats'], 'issues': data['issues']}
        else:
            write(base / 'aggregate.json', data)
            write(args.root / 'proposal/实战教学分析报告.html', render_report(data))
            result = data['stats']
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if (isinstance(result, dict) and (result.get('status') == 'failed' or result.get('stats', {}).get('invalid_records'))) else 0


if __name__ == '__main__':
    sys.exit(main())
