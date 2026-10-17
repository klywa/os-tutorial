"""One acquisition per process: release ASR memory and keep the HTTP server responsive."""
import argparse
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
from reference_store import export_transcripts, transcript_errors
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
    # prepare shares a BV-level cross-process lock with the CLI.
    outcomes = media.prepare.__wrapped__(root, f'https://www.bilibili.com/video/{bvid}',
                             cookies=store.settings()['cookies'] or None, progress_callback=progress)
    failed = [r for r in outcomes if r.get('stage') == 'failed']
    if failed:
        raise RuntimeError('; '.join(r.get('error', '') for r in failed))
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
            # Stale ASR is not safe to discard; manual output edits are deliberately preserved.
            errors = [e for e in transcript_errors(root, sid) if not e.startswith('Transcript was manually edited')]
            if errors:
                raise RuntimeError('; '.join(errors))
        for name in ['media.mp4', 'audio.wav', 'video.m4s', 'audio.m4s']:
            (folder / name).unlink(missing_ok=True)
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
        store.finish_task(args.bvid, 'failed', str(exc), generation=args.generation)
        raise
    else:
        # Persist completion even if the HTTP service was restarted during ASR.
        store.finish_task(args.bvid, 'succeeded', progress={'phase': 'ready'}, generation=args.generation)
    finally:
        stopped.set()
