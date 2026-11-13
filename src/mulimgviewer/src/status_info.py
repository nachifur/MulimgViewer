"""In-memory source lookup for the currently displayed image/video mosaic."""
import os
from pathlib import Path


def key(path):
    return os.path.normcase(os.path.normpath(str(path)))


class ImageSourceIndex:
    """Read-only dataset metadata, shared by render snapshots without copying."""
    def __init__(self, manager):
        self.folders, self.names, self.files = {}, {}, {}
        self.file_paths = manager.path_list
        paths = list(manager.path_list)
        names = manager.name_list
        if manager.type == 3:
            for offset, path in enumerate(paths):
                folder = key(Path(path).parent)
                if folder not in self.folders:
                    self.folders[folder] = len(self.folders)
                self.files.setdefault(key(path), offset)
            self.total = len(paths)
        else:
            common = None
            for offset, path in enumerate(paths):
                self.folders[key(path)] = offset
                if manager.parallel_to_sequential:
                    values = names[offset]
                    index = {str(name): i for i, name in enumerate(values)}
                else:
                    if common is None:
                        common = {str(name): i for i, name in enumerate(names)}
                    index = common
                self.names[key(path)] = index
            self.total = 0

    def locate(self, path, hint=None):
        folder = key(Path(path).parent)
        directory = self.folders.get(folder)
        if self.files:
            position = self.files.get(key(path))
            if hint is not None and 0 <= hint < len(self.file_paths) and key(self.file_paths[hint]) == key(path):
                position = hint
            total = self.total
        else:
            names = self.names.get(folder, {})
            position = names.get(Path(path).name)
            total = len(names)
        return position, total, directory, len(self.folders)


def selection_info(manager, cfg, grid=0):
    """Resolve layout cell -> source, using only already displayed metadata."""
    paths = list(getattr(manager, 'flist', []))
    mapping = getattr(manager, 'xy_grids_id_list', [])
    if not paths or grid < 0 or grid >= len(mapping):
        return None
    slot = int(mapping[grid])
    variants = getattr(manager, '_status_source_slots', None)
    if variants is not None:
        if not 0 <= slot < len(variants):
            return None
        slot = variants[slot]
    if not 0 <= slot < len(paths):
        return None
    if cfg.video_mode:
        sources = getattr(manager, '_status_video_sources', ())
        if slot >= len(sources):
            return None
        video, logical = sources[slot]
        videos = manager._status_video_paths
        counts = manager._status_video_counts
        if not 0 <= video < min(len(videos), len(counts)):
            return None
        step = manager._status_video_step
        physical = logical * step
        fps = manager._status_video_fps[video]
        seconds = physical / fps if fps > 0 else 0
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(int(minutes), 60)
        timestamp = f'{hours:02}:{minutes:02}:{seconds:06.3f}'
        return dict(position=f'Frame {logical+1}/{counts[video]} | Video {video+1}/{len(videos)}',
                    source=os.path.abspath(os.path.expanduser(str(videos[video]))), detail=f'Time {timestamp}; original frame {physical+1}'
                    + (f'; sample every {step} frames' if step > 1 else ''), timestamp=timestamp)
    index = getattr(manager, '_status_source_index', None)
    if index is None:
        return None
    hint = int(getattr(manager, 'action_count', 0)) * max(1, int(manager.count_per_action)) + slot
    position, total, folder, folders = index.locate(paths[slot], hint)
    if position is None or folder is None:
        return None
    return dict(position=f'Image {position+1}/{total} | Folder {folder+1}/{folders}',
                source=os.path.abspath(os.path.expanduser(str(paths[slot]))),
                detail=os.path.abspath(os.path.expanduser(str(Path(paths[slot]).parent))), timestamp='')


def status_widths(width, measured, padding=24):
    """Protect selection information; let long paths share the remaining room."""
    width = max(4, int(width))
    preferred = [max(125, min(260, measured[0]+padding)),
                 max(260, min(520, measured[1]+padding)), 180, 140]
    if sum(preferred) > width:
        total = sum(preferred)
        result = [max(1, int(value * width / total)) for value in preferred]
    else:
        spare = width-sum(preferred)
        result = preferred[:]
        result[2] += int(spare*.65)
        result[3] += spare-int(spare*.65)
    result[-1] += width-sum(result)
    return result
