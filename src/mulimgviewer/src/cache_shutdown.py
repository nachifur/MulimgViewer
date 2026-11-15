"""Startup and close-time removal of the application-owned cache_frames tree."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import time


def clear_cache_on_startup(root):
    """Remove stale layers synchronously BEFORE creating any cache producers.

    Failure aborts startup rather than letting the new session reuse a partly
    cleaned tree. Only the literal, non-linked cache_frames root is eligible.
    """
    import stat
    root=Path(root).absolute()
    if root.name!='cache_frames' or root.is_symlink() or root.resolve()!=root:
        raise ValueError('Startup cleanup target must be the actual cache_frames directory')
    try:
        info=root.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('Startup cache_frames target is not a directory')
    identity=(info.st_dev,info.st_ino)
    print('[Cache] Clearing previous session cache...')
    for attempt in range(4):
        try:
            info=root.lstat()
            if root.resolve()!=root or (info.st_dev,info.st_ino)!=identity:
                raise ValueError('Startup cache directory was replaced; refusing to delete its replacement')
            shutil.rmtree(root)
            print('[Cache] Previous session cache cleared')
            return True
        except OSError as error:
            # rmtree can also report a missing child while the root survives.
            # Only a missing root means startup cleanup is actually complete.
            if isinstance(error,FileNotFoundError) and not root.exists():return True
            if attempt==3:
                raise RuntimeError(f'Cannot clear previous cache before startup: {root}: {error}') from error
            time.sleep(.05*(attempt+1))


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
