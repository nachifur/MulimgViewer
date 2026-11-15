"""Frame path naming shared by extraction and future/virtual index entries."""

def frame_filename(index, fps, step=1, extension="jpeg"):
    physical = int(index)*max(1,int(step))
    fps = float(fps or 0)
    rounded = max(1,int(round(fps))) if fps > 0 else 1
    seconds = f'{physical/(fps if fps > 0 else rounded):.2f}'.rstrip('0').rstrip('.') or '0'
    return f'{seconds}s_frame_{physical%rounded+1}.{extension}'


def cache_extension(config):
    return 'png' if getattr(config,'cache_save_format',0)==1 else 'jpeg'


def resolve_cache_format(selection,save_format=0,output_scale=(1,1)):
    """Keep legacy jpg=0/png=1; auto=2 resolves from captured output settings."""
    import math
    if selection!=2:return 1 if selection==1 else 0
    try:
        scales=tuple(float(value) for value in output_scale)
        return int(save_format in (1,2) and len(scales)==2
                   and all(math.isfinite(value) and value>=1 for value in scales))
    except (TypeError,ValueError):return 0


def manager_cache_format(manager,save_format=None):
    params=getattr(manager,'layout_params',())
    selection=params[41] if len(params)>41 else getattr(manager,'cache_save_format',0)
    output=(params[35] if len(params)>35 else 0) if save_format is None else save_format
    scale=params[5] if len(params)>5 else (1,1)
    return resolve_cache_format(selection,output,scale)


def lossless_export(manager,save_format=None):
    params=manager.layout_params
    return (manager_cache_format(manager,save_format)==1 and (params[35] if save_format is None else save_format) in (1,2)
        and all(float(scale)>=1 for scale in params[5]))
