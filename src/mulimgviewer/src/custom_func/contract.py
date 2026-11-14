"""Optional plugin.json contract; legacy main(images, output, names) stays valid."""
import json


def specification(registry, index):
    entry = registry[index]
    value = json.loads(entry[3]) if len(entry) > 3 else {}
    if not isinstance(value, dict):
        raise ValueError('plugin.json must contain an object')
    result = dict(device='exclusive', max_concurrency=1, cacheable=True,
                  ordered=False, identity=False, cache_version='1', working_set_bytes=0)
    result.update(value)
    result['max_concurrency'] = max(1,int(result['max_concurrency']))
    result['working_set_bytes'] = max(0,int(result['working_set_bytes']))
    if not isinstance(result['device'],str):
        raise ValueError('Plugin device must be a string')
    if result['ordered']:
        result['cacheable'] = False
        result['max_concurrency'] = 1
    return result


def original_index(registry):
    return next((i for i in range(len(registry or ())) if specification(registry,i).get('role')=='original'),None)


def processing_indices(registry, params):
    original=original_index(registry)
    if params[38]:
        return [i for i in range(len(registry)) if i!=original]
    if params[32]:return [params[37] if 0<=params[37]<len(registry) else 0]
    return []


def display_indices(registry,params):
    original=original_index(registry)
    selected=processing_indices(registry,params)
    if params[38]:return [original]+selected
    if params[32]:
        return ([original] if params[36] and original not in selected else [])+selected
    return [original]


def display_grid(registry,params):
    if not (params[32] or params[38]):return 1,1
    import math
    rows,cols=map(int,params[39].split(','))
    if min(rows,cols)<1:raise ValueError('Algorithm layout requires positive rows and columns')
    count=len(display_indices(registry,params))
    if params[40]:cols=max(cols,math.ceil(count/rows))
    else:rows=max(rows,math.ceil(count/cols))
    return rows,cols


def active_cache_names(manager):
    registry=getattr(manager,'_custom_algorithm_registry',None)
    if registry is None:return None
    original=original_index(registry)
    default='original' if original is None else specification(registry,original).get('cache_name',registry[original][0])
    return {default}|{('original' if index is None else specification(registry,index).get('cache_name',registry[index][0]))
            for index in display_indices(registry,manager.layout_params)}
