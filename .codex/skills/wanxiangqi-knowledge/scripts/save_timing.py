"""Request-local save timings. No payloads or filesystem paths are recorded."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from time import perf_counter
import logging

_request=ContextVar('save_timing',default=None)

def begin():
    _request.set((perf_counter(),{}))

def record(name,milliseconds):
    current=_request.get()
    if current is not None:current[1][name]=current[1].get(name,0)+milliseconds

@contextmanager
def stage(name):
    if _request.get() is None:
        yield
        return
    started=perf_counter()
    try:yield
    finally:record(name,(perf_counter()-started)*1000)

def timed(name):
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            with stage(name):return fn(*args,**kwargs)
        return call
    return decorate

def finish(status):
    current=_request.get();_request.set(None)
    if current is None:return None
    values={**current[1],'total':(perf_counter()-current[0])*1000}
    header=', '.join(f'{name};dur={duration:.2f}' for name,duration in values.items())
    logging.getLogger('save-performance').info('status=%s %s',status,header)
    return header
