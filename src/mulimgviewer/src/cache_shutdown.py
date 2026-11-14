"""Authorized close-time removal of the application's cache_frames tree."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import time


def schedule_cache_removal(root,pools=(),futures=()):
    root=Path(root).absolute()
    if root.name!='cache_frames' or root.resolve()!=root:
        raise ValueError('Cache cleanup target must be the actual cache_frames directory')
    try:
        info=root.stat();identity=(info.st_dev,info.st_ino)
    except FileNotFoundError:identity=None

    def finish():
        for pool in pools:
            if pool is not None:pool.shutdown(wait=True)
        for future in futures:
            if future is not None:future.result()
        for attempt in range(4):
            try:
                info=root.stat()
                if root.resolve()!=root or (identity is not None and (info.st_dev,info.st_ino)!=identity):
                    raise ValueError('Cache directory was replaced; refusing to delete its replacement')
                shutil.rmtree(root)
                return
            except FileNotFoundError:return
            except OSError:
                if attempt==3:raise
                time.sleep(.05*(attempt+1))

    executor=ThreadPoolExecutor(1,thread_name_prefix='cache-shutdown')
    future=executor.submit(finish)
    executor.shutdown(wait=False)
    def report(completed):
        error=completed.exception()
        if error is not None:print(f'[Cache] Close-time cleanup failed: {error}')
    future.add_done_callback(report)
    return future
