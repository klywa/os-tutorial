"""Per-source OS locks shared by CLI and acquisition workers."""
from contextlib import contextmanager
from pathlib import Path
import os
import workspace


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise workspace.Busy('此来源正在处理，请稍后重试') from exc
        yield


def locked_source(function):
    from functools import wraps
    @wraps(function)
    def run(root, sid, *args, **kwargs):
        from wxq import source_dir
        with file_lock(source_dir(root, sid) / '.processing.lock'):
            return function(root, sid, *args, **kwargs)
    return run


def locked_video(function):
    from functools import wraps
    import re
    @wraps(function)
    def run(root, identity, *args, **kwargs):
        found = re.search(r'BV[a-zA-Z0-9]+', str(identity))
        key = found.group() if found else None
        if key:
            with file_lock(Path(root) / 'raw/crawler/locks' / (key + '.lock')):
                return function(root, identity, *args, **kwargs)
        return function(root, identity, *args, **kwargs)
    return run
