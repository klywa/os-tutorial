"""Stdlib-only crash breadcrumbs, initialized before acquisition/native imports."""
from datetime import datetime, timezone
import faulthandler
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import sys
import uuid


class Diagnostic:
    def __init__(self, root, bvid, generation):
        if not re.fullmatch(r'BV[0-9A-Za-z]+', bvid):
            raise ValueError('非法视频 ID')
        self.path = Path(root) / 'raw/crawler/attempts' / bvid / f'{int(generation or 0)}.json'

    def read(self):
        try:
            return json.loads(self.path.read_text('utf-8'))
        except (OSError, ValueError):
            return {}

    def write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as handle:
                json.dump(value, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def event(self, phase, dependencies=False, **fields):
        value = self.read()
        value.update(phase=phase, at=datetime.now(timezone.utc).isoformat(), pid=os.getpid())
        value.update({key: fields[key] for key in ('source', 'device', 'profile', 'processed_seconds', 'total_seconds') if key in fields})
        if dependencies:
            value['python'] = sys.version.split()[0]
            packages = {}
            for name in ('yt-dlp', 'faster-whisper', 'ctranslate2', 'av', 'onnxruntime'):
                try: packages[name] = version(name)
                except PackageNotFoundError: packages[name] = 'not installed'
            value['dependencies'] = packages
        self.write(value)
        print('[worker] ' + json.dumps({'phase': phase, **{k: value[k] for k in ('source', 'device', 'profile') if k in value}}, ensure_ascii=False), flush=True)

    def exit(self, code):
        value = self.read()
        value.update(exit_code=code, exit_hex=f'0x{code & 0xffffffff:08X}', exited_at=datetime.now(timezone.utc).isoformat())
        self.write(value)

    def recovery_progress(self, progress):
        detail = self.read()
        result = dict(progress)
        for key in ('phase', 'source', 'device'):
            if detail.get(key):result[key]=detail[key]
        if detail.get('profile')=='cpu_safe' or (detail.get('device')=='cuda' and detail.get('phase') in ('initializing_asr','transcribing')):
            result['asr_profile']='cpu_safe'
        return result


def bootstrap():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(line_buffering=True, write_through=True)
    faulthandler.enable(all_threads=True)
    # Imports in tests have no worker arguments and must remain side-effect free.
    if '--root' not in sys.argv or '--bvid' not in sys.argv:
        return None
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--root'); parser.add_argument('--bvid'); parser.add_argument('--generation', type=int, default=0)
    args, _ = parser.parse_known_args()
    diagnostic = Diagnostic(args.root, args.bvid, args.generation)
    diagnostic.event('starting', dependencies=True)
    diagnostic.event('importing_runtime')
    return diagnostic
