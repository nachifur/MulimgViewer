"""Optional plugin.json contract; legacy main(images, output, names) stays valid."""
import json


def specification(registry, index):
    entry = registry[index]
    value = json.loads(entry[3]) if len(entry) > 3 else {}
    if not isinstance(value, dict):
        raise ValueError('plugin.json must contain an object')
    result = dict(device='exclusive', max_concurrency=1, cacheable=True,
                  ordered=False, identity=False, api_version=1, processing_mode='batch', cache_version='1', working_set_bytes=0,working_set_bytes_per_pixel=16)
    result.update(value)
    if result['max_concurrency']=='auto':
        import os
        result['max_concurrency']=max(1,os.cpu_count() or 1)
    result['max_concurrency'] = max(1,int(result['max_concurrency']))
    result['working_set_bytes'] = max(0,int(result['working_set_bytes']))
    result['working_set_bytes_per_pixel']=max(8,int(result['working_set_bytes_per_pixel']))
    if not isinstance(result['device'],str):
        raise ValueError('Plugin device must be a string')
    if result['processing_mode'] not in ('image', 'batch'):
        raise ValueError('processing_mode must be image or batch')
    if result['api_version'] not in (1, 2):
        raise ValueError('Unsupported plugin api_version')
    if result['processing_mode'] == 'image' and (result['device'] != 'cpu' or result['ordered']):
        raise ValueError('Image parallelism requires an unordered CPU plugin; use batch for GPU/stateful processing')
    if result['ordered']:
        result['cacheable'] = False
        result['max_concurrency'] = 1
    return result


def original_index(registry):
    return next((i for i in range(len(registry or ())) if specification(registry,i).get('role')=='original'),None)


def processing_indices(registry, params):
    """Compute only visible non-original algorithms; raw mosaic is retained separately."""
    if not (params[32] or params[38]):return []
    original=original_index(registry)
    return [index for index in display_indices(registry,params)
            if index is not None and index!=original]


def display_indices(registry,params):
    original=original_index(registry)
    if not (params[32] or params[38]):return [original]
    if params[38]:
        selected=[index for index in range(len(registry)) if index!=original]
    else:
        selected=[params[37] if 0<=params[37]<len(registry) else 0] if registry else []
        selected=[index for index in selected if index!=original]
    indices=([original] if params[36] else [])+selected
    rows,cols=display_grid(registry,params)
    return indices[:rows*cols]


def display_grid(registry,params):
    """Respect the configured canvas exactly; direction changes ordering only."""
    if not (params[32] or params[38]):return 1,1
    rows,cols=map(int,params[39].split(','))
    if min(rows,cols)<1:raise ValueError('Algorithm layout requires positive rows and columns')
    return rows,cols


def active_cache_names(manager):
    registry=getattr(manager,'_custom_algorithm_registry',None)
    if registry is None:return None
    original=original_index(registry)
    default='original' if original is None else specification(registry,original).get('cache_name',registry[original][0])
    return {default}|{('original' if index is None else specification(registry,index).get('cache_name',registry[index][0]))
            for index in display_indices(registry,manager.layout_params)}
