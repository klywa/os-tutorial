"""Resumable local ASR and frame extraction."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import urllib.parse
from functools import lru_cache
from wxq import atomic_json, correct_text, entities, init_store, now, read_json, source_dir


def ffmpeg():
    found = shutil.which('ffmpeg')
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def shell(args):
    subprocess.run([str(x) for x in args], check=True)


def download_observed(url, path):
    """Resume a public observed DASH stream and reject silently truncated responses."""
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('Use an observed HTTPS media URL')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(3):
        offset = path.stat().st_size if path.exists() else 0
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.bilibili.com/', 'Range': f'bytes={offset}-'})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                content_range = response.headers.get('Content-Range', '')
                expected = None
                mode = 'wb'
                if response.status == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range)
                    if not match or int(match[1]) != offset:
                        raise ValueError('Response does not match requested range')
                    expected = int(match[3])
                    mode = 'ab'
                elif response.status == 200:
                    expected = int(response.headers['Content-Length']) if response.headers.get('Content-Length') else None
                else:
                    raise ValueError('Unexpected HTTP status')
                if expected is None:
                    raise ValueError('Cannot validate full media length')
                with path.open(mode) as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                if path.stat().st_size == expected:
                    return {'path': str(path), 'bytes': expected, 'complete': True}
                last_error = f'Truncated media: {path.stat().st_size}/{expected} bytes'
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                match = re.search(r'bytes \*/(\d+)', exc.headers.get('Content-Range', ''))
                if match and offset == int(match[1]):
                    return {'path': str(path), 'bytes': offset, 'complete': True}
            last_error = str(exc)
        except (OSError, ValueError) as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or 'Media transfer failed')


@lru_cache(maxsize=4)
def phonetic_index(names):
    from pypinyin import lazy_pinyin
    index = {}
    for eid, name in names:
        if 2 <= len(name) <= 12:
            key = (len(name), tuple(lazy_pinyin(name)))
            index.setdefault(key, []).append((eid, name))
    return index


@lru_cache(maxsize=20000)
def pronunciation(token):
    from pypinyin import lazy_pinyin
    return tuple(lazy_pinyin(token))


def phonetic_candidates(text, records):
    index = phonetic_index(tuple((e['id'], e['name']) for e in records))
    result = []
    for length in sorted({key[0] for key in index}):
        for i in range(len(text) - length + 1):
            token = text[i:i + length]
            if not re.fullmatch(r'[\u4e00-\u9fff]+', token):
                continue
            for eid, name in index.get((length, pronunciation(token)), []):
                if name not in text:
                    result.append({'original': token, 'candidate': name, 'entity': eid,
                                   'status': 'needs_context_review'})
    return result


def transcribe(root, sid, audio, model_name='large-v3'):
    folder = source_dir(root, sid)
    raw_path = folder / 'asr.raw.json'
    if not raw_path.exists():
        from faster_whisper import WhisperModel, BatchedInferencePipeline
        from faster_whisper.audio import decode_audio
        import ctranslate2
        progress = read_json(folder / 'asr.progress.json', {})
        prior_segments = progress.get('segments', []) if progress.get('model') == model_name else []
        offset = prior_segments[-1]['end'] if prior_segments else 0
        device = 'cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
        records = entities(root)
        prompt = '王者万象棋。' + '、'.join(e['name'] for e in records if e['category'] == 'players')[:220]
        try:
            model = WhisperModel(model_name, device=device,
                                 compute_type='float16' if device == 'cuda' else 'int8',
                                 cpu_threads=8,
                                 download_root=str(Path(root) / '.wxq-runtime/models'))
        except RuntimeError:
            if device != 'cuda':
                raise
            device = 'cpu'
            model = WhisperModel(model_name, device='cpu', compute_type='int8',
                                 cpu_threads=8,
                                 download_root=str(Path(root) / '.wxq-runtime/models'))
        print(f'Loaded {model_name}, device={device}; running local ASR', flush=True)
        pipeline = BatchedInferencePipeline(model=model)
        beam = 1 if device == 'cpu' else 5
        waveform = decode_audio(str(audio))[int(offset * 16000):] if offset else str(audio)
        segments, info = pipeline.transcribe(waveform, language='zh', vad_filter=True,
                                             beam_size=beam, initial_prompt=prompt, word_timestamps=True, batch_size=4)
        print(f'VAD complete: {info.duration_after_vad:.1f}s speech / {info.duration:.1f}s total', flush=True)
        raw = {'model': model_name, 'device': device, 'language': info.language, 'batch_size': 4,
               'decoder_runs': progress.get('decoder_runs', []) + [{'start': offset, 'beam_size': beam}],
               'segments': prior_segments}
        for s in segments:
            raw['segments'].append({'id': len(raw['segments']) + 1, 'start': s.start + offset, 'end': s.end + offset, 'text': s.text,
                                    'avg_logprob': s.avg_logprob, 'no_speech_prob': s.no_speech_prob,
                                    'words': [{'start': w.start + offset, 'end': w.end + offset, 'word': w.word,
                                               'probability': w.probability} for w in (s.words or [])]})
            if len(raw['segments']) % 10 == 0:
                atomic_json(folder / 'asr.progress.json', raw)
                print(f'ASR: {s.end + offset:.1f}s / {info.duration + offset:.1f}s', flush=True)
        atomic_json(raw_path, raw)
    if not (folder / 'asr.corrected.json').exists():
        corrected = json.loads(json.dumps(read_json(raw_path)))
        changes = []
        records = entities(root)
        for segment in corrected['segments']:
            segment['text'], edits = correct_text(segment['text'], records)
            edits += phonetic_candidates(segment['text'], records)
            changes += [{**e, 'segment': segment['id'], 'start': segment['start']} for e in edits]
        atomic_json(folder / 'asr.corrected.json', corrected)
        atomic_json(folder / 'corrections.json', changes)
    return read_json(folder / 'asr.corrected.json')


def extract_frames(root, sid, video, times):
    folder = source_dir(root, sid)
    manifest = read_json(folder / 'frames.json', [])
    known = {row['time'] for row in manifest if (folder / row['path']).exists()}
    for t in sorted(set(round(float(t), 2) for t in times)):
        if t < 0:
            raise ValueError('Frame time must be nonnegative')
        if t in known:
            continue
        relative = 'frames/' + str(t).replace('.', '-') + '.jpg'
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shell([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-ss', t, '-i', video,
               '-frames:v', '1', '-vf', 'scale=1280:-2', '-y', destination])
        if destination.exists():
            manifest = [f for f in manifest if f['time'] != t]
            manifest.append({'time': t, 'path': relative, 'reviewed': False, 'observation': None})
    atomic_json(folder / 'frames.json', manifest)
    return manifest


def prepare(root, url, model='large-v3', cookies=None):
    import yt_dlp
    root = Path(root)
    init_store(root)
    match = re.search(r'BV[0-9A-Za-z]+', url)
    if match:
        requested_part = urllib_part(url)
        cached = []
        for folder in (root / 'raw/sources').glob(match.group() + '_p*'):
            meta = read_json(folder / 'metadata.json', {})
            if requested_part and meta.get('id') != match.group() + ':p' + requested_part:
                continue
            if read_json(folder / 'state.json', {}).get('stage') == 'complete':
                cached.append({'id': meta['id'], 'stage': 'complete', 'cached': True})
        # A bare BV URL can contain multiple parts: only skip lookup when cached part_count is known.
        if cached and (requested_part or len(cached) == read_json(source_dir(root, cached[0]['id']) / 'metadata.json', {}).get('part_count')):
            return cached
    options = {'quiet': True, 'socket_timeout': 30, 'retries': 2, 'noplaylist': False,
               'ffmpeg_location': ffmpeg()}
    if cookies:
        options['cookiefile'] = cookies
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
    entries = list(info.get('entries') or [info])
    outcomes = []
    for number, entry in enumerate(entries, 1):
        match = re.search(r'BV[0-9A-Za-z]+', url)
        # BV + actual part index is stable across playlist and single-part URLs.
        part = entry.get('playlist_index') or int(urllib_part(url) or number)
        sid = (match.group() if match else str(entry['id'])) + ':p' + str(part)
        folder = source_dir(root, sid)
        folder.mkdir(parents=True, exist_ok=True)
        if read_json(folder / 'state.json', {}).get('stage') == 'complete':
            outcomes.append({'id': sid, 'stage': 'complete', 'cached': True})
            continue
        try:
            entry_url = entry.get('webpage_url') or url
            if match:
                entry_url = 'https://www.bilibili.com/video/' + match.group() + '/?p=' + str(part)
            metadata = {'id': sid, 'bvid': match.group() if match else None, 'part': part,
                        'url': entry_url, 'title': entry.get('title'), 'author': entry.get('uploader'),
                        'published': entry.get('upload_date'), 'duration': entry.get('duration'),
                        'collected_at': now(), 'version': None, 'part_count': len(entries)}
            if not (folder / 'metadata.json').exists():
                atomic_json(folder / 'metadata.json', metadata)
            video, audio = folder / 'media.mp4', folder / 'audio.wav'
            if not (folder / 'asr.raw.json').exists() or not (folder / 'frames.json').exists():
                if not video.exists():
                    atomic_json(folder / 'state.json', {'stage': 'downloading'})
                    opts = {**options, 'noplaylist': True, 'format': 'bestvideo[height<=720]+bestaudio/best',
                            'merge_output_format': 'mp4',
                            'outtmpl': str(folder / 'media.%(ext)s'), 'writesubtitles': True,
                            'writeautomaticsub': True, 'subtitleslangs': ['zh.*'], 'subtitlesformat': 'srt/best'}
                    with yt_dlp.YoutubeDL(opts) as downloader:
                        downloaded = downloader.extract_info(entry_url, download=True)
                        actual = Path(downloader.prepare_filename(downloaded))
                        if video.exists():
                            actual = video
                    if actual != video:
                        shell([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-i', actual, '-c', 'copy', '-y', video])
                        actual.unlink()
                if not audio.exists() and not (folder / 'asr.raw.json').exists():
                    shell([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-i', video,
                           '-vn', '-ac', '1', '-ar', '16000', '-y', audio])
            atomic_json(folder / 'state.json', {'stage': 'transcribing'})
            transcript = transcribe(root, sid, audio, model)
            times = [0]
            for s in transcript['segments']:
                if any(word in s['text'] for word in ['阵容', '拍卖', '站位', '装备', '看这里', '天赋', '决赛']):
                    times += [s['start'], (s['start'] + s['end']) / 2]
            if video.exists():
                extract_frames(root, sid, video, times[:80])
            atomic_json(folder / 'state.json', {'stage': 'prepared', 'needs_review': True})
            outcomes.append({'id': sid, 'stage': 'prepared'})
        except Exception as exc:
            atomic_json(folder / 'state.json', {'stage': 'failed', 'error': str(exc), 'at': now()})
            outcomes.append({'id': sid, 'stage': 'failed', 'error': str(exc)})
    return outcomes


def urllib_part(url):
    from urllib.parse import parse_qs, urlparse
    return parse_qs(urlparse(url).query).get('p', [None])[0]


def process_local(root, sid, model='large-v3'):
    """Process browser-downloaded source media, retaining the same provenance contract."""
    folder = source_dir(root, sid)
    meta = read_json(folder / 'metadata.json', {})
    if meta.get('id') != sid or not meta.get('url'):
        raise ValueError('Save verified metadata.json before processing local media')
    if read_json(folder / 'state.json', {}).get('stage') == 'complete':
        return {'id': sid, 'stage': 'complete', 'cached': True}
    video, audio = folder / 'media.mp4', folder / 'audio.wav'
    try:
        if not video.exists() and (folder / 'video.m4s').exists() and (folder / 'audio.m4s').exists():
            shell([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-i', folder / 'video.m4s',
                   '-i', folder / 'audio.m4s', '-c', 'copy', '-y', video])
        if not audio.exists() and not (folder / 'asr.raw.json').exists():
            shell([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-i', video,
                   '-vn', '-ac', '1', '-ar', '16000', '-y', audio])
        atomic_json(folder / 'state.json', {'stage': 'transcribing', 'at': now()})
        transcript = transcribe(root, sid, audio, model)
        times = [0]
        for segment in transcript['segments']:
            if any(w in segment['text'] for w in ['阵容', '拍卖', '站位', '装备', '天赋', '决赛']):
                times += [segment['start'], (segment['start'] + segment['end']) / 2]
        if video.exists():
            extract_frames(root, sid, video, times[:80])
        atomic_json(folder / 'state.json', {'stage': 'prepared', 'needs_review': True})
        return {'id': sid, 'stage': 'prepared'}
    except Exception as exc:
        atomic_json(folder / 'state.json', {'stage': 'failed', 'error': str(exc), 'at': now()})
        raise


def finish(root, sid):
    folder = source_dir(root, sid)
    review = read_json(folder / 'review.json', {})
    if not review.get('approved'):
        raise ValueError('Create approved review.json after ASR and frame review')
    claims = [c for n in read_json(Path(root) / 'knowledge/index.json', {'notes': []})['notes']
              for c in n.get('claims', []) if any(e['source'] == sid for e in c['evidence'])]
    if not claims:
        raise ValueError('No committed knowledge for source')
    for c in claims:
        for e in c['evidence']:
            if e['source'] == sid and not any(len(interval) == 2 and interval[0] <= e['start'] <= e['end'] <= interval[1]
                                              for interval in review.get('checked_intervals', [])):
                raise ValueError('Review intervals do not cover cited evidence')
            if e['source'] == sid and e.get('frame'):
                if not any(f['path'] == e['frame'] and f.get('reviewed') and f.get('observation')
                           for f in read_json(folder / 'frames.json', [])):
                    raise ValueError('Cited frame not reviewed')
    if not (folder / 'asr.raw.json').exists() or not (folder / 'asr.corrected.json').exists():
        raise ValueError('ASR artifacts required')
    from reference_store import transcript_errors
    errors = transcript_errors(root, sid)
    if errors:
        raise ValueError('; '.join(errors))
    atomic_json(folder / 'state.json', {'stage': 'complete', 'at': now()})
    for filename in ['media.mp4', 'audio.wav', 'video.m4s', 'audio.m4s']:
        (folder / filename).unlink(missing_ok=True)
    return {'id': sid, 'stage': 'complete'}
