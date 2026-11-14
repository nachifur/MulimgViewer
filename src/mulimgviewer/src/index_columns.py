"""View-specific columns shared by the virtual list and Excel export."""
from dataclasses import dataclass
from pathlib import Path
from .video_timeline import page_segments

VIEW_NAMES = ('Sources', 'Pages', 'Visual items')


@dataclass(frozen=True)
class IndexColumn:
    key: object
    label: str
    width: int


def view_columns(view, video):
    C = IndexColumn
    if view == 2:
        columns = [C(0,'Visual ID',75), C(1,'Page',65), C(2,'Video' if video else 'Folder',100),
                   C(3,'Frame / time' if video else 'Image',170),
                   C(4,'Original video' if video else 'Image path',330), C(5,'Position',115)]
        columns.append(C(6,'Frame path' if video else 'Image / cache path',340))
        columns.extend((C('algorithm','Algorithm',140),C('algorithm_path','Algorithm path',340)))
        columns.append(C(7,'Cache state' if video else 'File status',145))
        return tuple(columns)
    if view == 1:
        columns = [C(1,'Page',65), C(2,'Videos' if video else 'Folders',150),
                   C(3,'Frame ranges' if video else 'Image positions',200)]
        if video:
            columns.extend((C('page_times','Time ranges (s)',240), C('page_paths','Video paths',450)))
        else:
            columns.append(C(4,'Image paths',500))
        return tuple(columns)
    if video:
        return (C(0,'Video #',75), C(1,'Pages',95), C('frames','Frames',95),
                C('source_path','Video path',400), C('last_time','Last frame time (s)',145),
                C('step','Sample step',100))
    return (C(0,'Source #',75), C(1,'Page',65), C(2,'Folder',110),
            C(3,'Image',110), C(4,'Image path',500))


def view_row(model, view, index, raw=None):
    """Project canonical metadata without depending on the displayed column order."""
    if raw is None:
        raw = model.visual_row(index) if view == 2 else model.source_row(index) if view == 0 else model.page_row(index)
    spans = None
    result = []
    for column in view_columns(view,model.video):
        key = column.key
        if isinstance(key,int):
            value = raw[key]
            if key in (0,1) and str(value).isdigit():
                value = int(value)
        elif key in ('algorithm','algorithm_path'):
            value=model.visual_entry(index).get(key,'Original' if key=='algorithm' else '')
        elif key == 'frames':
            value = model.counts[index]
        elif key == 'source_path':
            value = str(Path(model.paths[index]).absolute())
        elif key == 'last_time':
            fps = model.fps[index]
            value = max(0,model.counts[index]-1)*model.step/fps if fps > 0 else 0
        elif key == 'step':
            value = model.step
        else:
            if spans is None:
                spans = page_segments(model.counts,model.size,index,model.serial)
            if key == 'page_paths':
                value = '; '.join(str(Path(model.paths[v]).absolute()) for v,a,b in spans)
            else:
                value = '; '.join(f'{a*model.step/model.fps[v]:.3f}-{(b-1)*model.step/model.fps[v]:.3f}'
                                  if model.fps[v] > 0 else 'Unknown' for v,a,b in spans)
        result.append(value)
    return tuple(result)


def export_filename(view, video):
    return ('video' if video else 'image') + '_index_' + ('sources','pages','visual_items')[view] + '.xlsx'
