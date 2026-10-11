"""Bounded cross-video downloads and serial ASR, independent of analysis."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading

from tutorial import ROOT, existing_record, identity, read, state, write


def run_batch(root, jobs, model, download, transcribe, finalize, downloads=3, asr_workers=1):
    root = Path(root)
    lock = threading.RLock()
    seen = set()
    active = []
    results = [None] * len(jobs)
    def update(sid, status, **details):
        with lock:
            state(root, sid, status, **details)
        print(sid, status, details.get('stage', ''), details.get('error', ''), flush=True)
    # Check all identities and reuse barriers before scheduling any media work.
    for index, job in enumerate(jobs):
        source = job['source']
        sid = source['id']
        if identity(source['url']) != sid or sid in seen:
            raise ValueError('Duplicate or inconsistent source: ' + sid)
        seen.add(sid)
        reused = existing_record(root, source)
        if reused:
            results[index] = reused
            continue
        folder = root / 'raw/sources' / sid.replace(':', '_')
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / 'metadata.json', source)
        active.append((index, job, folder))
    with ThreadPoolExecutor(max_workers=downloads) as transfers, ThreadPoolExecutor(max_workers=asr_workers) as decoder:
        pending = []
        def decode(sid, folder, audio_future):
            audio_future.result()
            update(sid, 'in_progress', stage='transcribing')
            transcribe(root, sid, folder / 'audio.m4s', str(model))
            update(sid, 'in_progress', stage='video_transfer', note='ASR已保存，等待视频及人工分析')
        for index, job, folder in active:
            sid = job['source']['id']
            update(sid, 'in_progress', stage='acquisition')
            audio = transfers.submit(download, job['audio'], folder / 'audio.m4s') if not (folder / 'asr.raw.json').exists() else transfers.submit(lambda: None)
            video = transfers.submit(download, job['video'], folder / 'video.m4s')
            asr = decoder.submit(decode, sid, folder, audio)
            pending.append((index, sid, asr, video))
        # Transfers and decoding continue while individual sources finalize.
        for index, sid, asr, video in pending:
            try:
                asr.result()
                video.result()
                with lock:
                    finalize(root, sid, str(model))
                update(sid, 'in_progress', stage='prepared', note='素材就绪；教学分析尚未完成')
                results[index] = {'id': sid, 'status': 'prepared'}
            except Exception as exc:
                update(sid, 'failed', stage='acquisition-or-asr', error=str(exc))
                results[index] = {'id': sid, 'status': 'failed', 'error': str(exc)}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observed', nargs='+', type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--download-workers', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.download_workers <= 6:
        parser.error('download-workers must be between 1 and 6')
    sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
    from media import download_observed, transcribe, process_local
    from reference_store import export_transcripts
    def decode(root, sid, audio, model):
        transcribe(root, sid, audio, model)
        result = export_transcripts(root, [sid])
        if result['errors']:
            raise RuntimeError(str(result['errors']))
    results = run_batch(ROOT, [read(path) for path in args.observed], args.model_dir,
                        download_observed, decode, process_local, args.download_workers)
    write(ROOT / 'raw/reports/pipeline-last-run.json', results)
    return int(any(result['status'] == 'failed' for result in results))


if __name__ == '__main__':
    sys.exit(main())
