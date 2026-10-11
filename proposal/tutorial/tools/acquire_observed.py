"""Acquire only exact browser-observed media; resume local large-v3 ASR."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from tutorial import ROOT, read, existing_record, state


def main():
    p = argparse.ArgumentParser()
    p.add_argument('observed', type=Path, help='Verified source metadata and exact observed audio/video URLs')
    p.add_argument('--model-dir', required=True, type=Path, help='Existing faster-whisper-large-v3 snapshot')
    args = p.parse_args()
    data = read(args.observed)
    sid = data['source']['id']
    if existing_record(ROOT, data['source']):
        print('Existing tutorial record retained; no acquisition')
        return 0
    sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
    from media import download_observed, transcribe, process_local
    from wxq import atomic_json, source_dir
    from reference_store import export_transcripts
    folder = source_dir(ROOT, sid)
    folder.mkdir(parents=True, exist_ok=True)
    atomic_json(folder / 'metadata.json', data['source'])
    state(ROOT, sid, 'in_progress', stage='acquisition', note='正常浏览器已公开播放，使用实际观察到的DASH资源')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(download_observed, data['video'], folder / 'video.m4s')
            if not (folder / 'asr.raw.json').exists():
                print('Audio:', download_observed(data['audio'], folder / 'audio.m4s'), flush=True)
            state(ROOT, sid, 'in_progress', stage='transcribing', note='large-v3本地ASR；完成后还需语义与截图核对')
            atomic_json(folder / 'state.json', {'stage': 'transcribing'})
            transcribe(ROOT, sid, folder / 'audio.m4s', str(args.model_dir))
            state(ROOT, sid, 'in_progress', stage='video_transfer', note='ASR已保存；等待完整视频传输和画面核对')
            print('Video:', future.result(), flush=True)
        process_local(ROOT, sid, str(args.model_dir))
        result = export_transcripts(ROOT, [sid])
        if result['errors']:
            raise RuntimeError(str(result['errors']))
        state(ROOT, sid, 'in_progress', stage='prepared', note='完整ASR与初步帧已就绪，等待逐段语义核对')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        state(ROOT, sid, 'failed', stage='acquisition-or-asr', error=str(exc))
        print(type(exc).__name__ + ': ' + str(exc), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
