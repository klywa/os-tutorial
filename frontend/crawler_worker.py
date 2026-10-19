"""One acquisition per process: release ASR memory and keep the HTTP server responsive."""
import argparse
import json
import sys
import time
import threading
import os
import subprocess
from pathlib import Path
from crawler import Store, register_discovered
import wxq
import media
import workspace
from reference_store import export_transcripts, transcript_errors, repair_transcript_index
from processing_lock import locked_video


def watch_requests(store, bvid, stopped, on_cancel, generation=None):
    """A worker surviving an HTTP restart still observes deletion of its last batch."""
    while not stopped.wait(.5):
        if store.halted(bvid) or (generation is not None and not store.requested(bvid, generation)) or (not store.requested(bvid) and store.cancel_orphan(bvid)):
            on_cancel()
            return


def cancel_self():
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/PID', str(os.getpid()), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        import signal
        os.kill(os.getpid(), signal.SIGTERM)


@locked_video
def run(root, bvid, generation=None):
    store = Store(root)
    last = [0.0, None]
    def progress(value):
        if value.get('phase') != last[1] or time.monotonic() - last[0] >= 1:
            store.finish_task(bvid, 'running', progress=value, generation=generation)
            last[0] = time.monotonic()
            last[1] = value.get('phase')
    adapter = [None]
    from bilibili import Bilibili
    from acquisition_errors import describe_error
    def client():
        if adapter[0] is None:adapter[0]=Bilibili(store.settings()['cookies'],refresh=bool(store.risk_retry('task',bvid)),root=root)
        return adapter[0]
    def entries():
        try:return client().entries(bvid)
        except Exception as exc:
            detail=describe_error(exc,'discovery')
            if detail['category'] not in ['risk','network']:raise
            cached=[]
            for folder in sorted((Path(root)/'raw/sources').glob(bvid+'_p*')):
                meta=wxq.read_json(folder/'metadata.json',{})
                part=meta.get('part')
                if meta.get('bvid')==bvid and type(part) is int and part>0 and meta.get('id')==f'{bvid}:p{part}':
                    cached.append({'id':str(meta.get('cid') or part),'cid':meta.get('cid'),'playlist_index':part,
                        'title':meta.get('title',''),'duration':meta.get('duration'),'uploader':meta.get('author',''),
                        'upload_date':meta.get('published'),'webpage_url':f'https://www.bilibili.com/video/{bvid}/?p={part}',
                        'part_count':meta.get('part_count')})
            if cached and cached[0].get('part_count')==len(cached) and len({r['playlist_index'] for r in cached})==len(cached):
                wxq.atomic_json(Path(root)/'raw/crawler'/f'{bvid}-discovery-fallback.json',{'at':wxq.now(),**detail})
                return cached
            return client().metadata_entries(bvid)

    def fetch_subtitle(video, part, duration):
        for attempt in range(2):
            try:return client().subtitles(video,part,duration,progress=progress)
            except Exception as exc:
                detail=describe_error(exc,'fetching_subtitles')
                folder=wxq.source_dir(root,f'{video}:p{part}');folder.mkdir(parents=True,exist_ok=True)
                history=wxq.read_json(folder/'subtitle-fallback.json',{}).get('attempts',[])
                history.append({'at':wxq.now(),**detail})
                wxq.atomic_json(folder/'subtitle-fallback.json',{'at':wxq.now(),**detail,'attempts':history[-20:]})
                if attempt==0:
                    try:
                        client().refresh_session()
                        if getattr(client(),'gate',None):client().gate.probe('subtitles');client().gate.probe('subtitle_file')
                    except Exception:break
                else:break
        return None  # Explicit recorded fallback, never reported as absence of subtitles.
    outcomes = media.prepare.__wrapped__(root, f'https://www.bilibili.com/video/{bvid}',
        cookies=store.settings()['cookies'] or None, progress_callback=progress, require_frames=False,
        subtitle_fetcher=fetch_subtitle,entry_fetcher=entries,
        download_callback=lambda url,options,attempts:client().download(url,options,attempts))
    failed = [r for r in outcomes if r.get('stage') == 'failed']
    if failed:
        from acquisition_errors import AcquisitionFailure
        raise AcquisitionFailure(failed)
    if not outcomes:
        raise RuntimeError('未获取到视频分P')
    progress({'phase': 'exporting'})
    for result in outcomes:
        sid = result['id']
        folder = wxq.source_dir(root, sid)
        metadata = wxq.read_json(folder / 'metadata.json', {})
        with workspace.store_lock(root, wait=True):
            existing = next((s for s in workspace.sources(root) if s['id'] == sid), None)
        if not existing:
            workspace.register_source(root, {'url': metadata['url'], 'title': metadata.get('title', ''), 'notes': ''})
        # Reuse a valid export, including existing human-edited text. Never overwrite it.
        manifest = wxq.read_json(Path(root) / 'raw/index.json', {}).get('sources', {}).get(sid)
        if not manifest or not (Path(root) / manifest['path']).is_file():
            report = export_transcripts(root, [sid])
            if report['errors']:
                raise RuntimeError(report['errors'][0]['error'])
        else:
            repair_transcript_index(root, sid)
            # Stale ASR is not safe to discard; manual output edits are deliberately preserved.
            errors = [e for e in transcript_errors(root, sid) if not e.startswith('Transcript was manually edited')]
            if errors:
                raise RuntimeError('; '.join(errors))
        if not wxq.read_json(folder / 'state.json', {}).get('warnings'):
            for name in ['media.mp4', 'audio.wav', 'video.m4s', 'audio.m4s']:
                (folder / name).unlink(missing_ok=True)
    # Topic enrichment is independent: queue failures never turn a valid ASR into failure.
    try:
        from topics import TopicStore
        from crawler import source_rows
        TopicStore(root).sync(source_rows(root, store))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('文字稿已完成，主题入队等待后台补查：%s', exc)
    return outcomes


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--bvid', required=True)
    parser.add_argument('--generation', type=int)
    args = parser.parse_args()
    store = Store(args.root)
    stopped = threading.Event()
    if any(t['bvid'] == args.bvid and t['state'] == 'running' for t in store.tasks()):
        threading.Thread(target=watch_requests, args=(store, args.bvid, stopped, cancel_self, args.generation), daemon=True).start()
    try:
        run(args.root, args.bvid, generation=args.generation)
    except workspace.Busy:
        store.finish_task(args.bvid, 'queued', '来源正在处理，稍后自动重试', generation=args.generation)
        sys.exit(75)
    except Exception as exc:
        current=next((t for t in store.tasks() if t['bvid']==args.bvid),{})
        store.finish_task(args.bvid, 'failed', exc, progress=json.loads(current.get('progress') or '{}'), generation=args.generation)
        raise
    else:
        # Persist completion even if the HTTP service was restarted during ASR.
        store.finish_task(args.bvid, 'succeeded', progress={'phase': 'ready'}, generation=args.generation)
    finally:
        stopped.set()
