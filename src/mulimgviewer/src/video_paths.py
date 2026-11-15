"""Frame path naming shared by extraction and future/virtual index entries."""

def frame_filename(index, fps, step=1, extension="jpeg"):
    physical = int(index)*max(1,int(step))
    fps = float(fps or 0)
    rounded = max(1,int(round(fps))) if fps > 0 else 1
    seconds = f'{physical/(fps if fps > 0 else rounded):.2f}'.rstrip('0').rstrip('.') or '0'
    return f'{seconds}s_frame_{physical%rounded+1}.{extension}'


def cache_extension(config):
    return 'png' if getattr(config,'cache_save_format',0)==1 else 'jpeg'


def manager_cache_format(manager):
    params=getattr(manager,'layout_params',())
    return int(params[41]) if len(params)>41 else int(getattr(manager,'cache_save_format',0))


def lossless_export(manager,save_format=None):
    params=manager.layout_params
    return (manager_cache_format(manager)==1 and (params[35] if save_format is None else save_format) in (1,2)
        and all(float(scale)>=1 for scale in params[5]))
