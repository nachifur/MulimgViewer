"""Viewer status bar and image/video selection metadata."""
import os
import wx
from pathlib import Path

from .localization import tr



# Selection metadata and field sizing
def key(path):
    return os.path.normcase(os.path.normpath(str(path)))


class ImageSourceIndex:
    """Read-only dataset metadata, shared by render snapshots without copying."""
    def __init__(self, manager):
        self.folders, self.names, self.files = {}, {}, {}
        self.source_folders = {}  # Original spelling for exported paths and metadata.
        self.file_paths = manager.path_list
        paths = list(manager.path_list)
        names = manager.name_list
        if manager.type == 3:
            for offset, path in enumerate(paths):
                folder = key(Path(path).parent)
                if folder not in self.folders:
                    self.folders[folder] = len(self.folders)
                    self.source_folders[Path(path).parent] = self.folders[folder]
                self.files.setdefault(key(path), offset)
            self.total = len(paths)
        else:
            common = None
            for offset, path in enumerate(paths):
                self.folders[key(path)] = offset
                self.source_folders[Path(path)] = offset
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


def source_slot(manager, grid=0):
    """Resolve a painted cell, including algorithm panes, to its raw source."""
    paths = getattr(manager, 'flist', [])
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
    if int(mapping[grid]) in getattr(manager, '_blank_img_ids', ()):
        return None
    return slot


def pixel_memory(size, mode):
    """Pillow pixel storage estimate; RGB uses four bytes internally too."""
    width, height = map(int, size)
    channels = 1 if mode in ('1', 'L', 'P') else 2 if mode.startswith('I;16') else 4
    return max(0, width)*max(0, height)*channels


def image_memory_tooltip(manager, canvas, grid=0):
    """Metadata only: never decode, allocate a canvas or inspect the disk here."""
    lines=[]
    slot=source_slot(manager,grid)
    sources=getattr(manager,'_status_source_images',())
    for label, info in (('Original (selected)', sources[slot] if slot is not None and slot<len(sources) else None),
                        ('Page mosaic',canvas)):
        if info is None:
            lines.append(tr('{label}: unavailable').format(label=tr(label)))
            continue
        size,mode=info
        amount=pixel_memory(size,mode)/1024**2
        lines.append(tr('{label}: {w} x {h} {mode} | pixels ~ {mib:.2f} MiB').format(
            label=tr(label), w=size[0], h=size[1], mode=mode, mib=amount))
    lines.append(tr('Pixel estimates only; codec, processing and GUI copies need extra RAM.'))
    return '\n'.join(lines)


def selection_info(manager, cfg, grid=0):
    """Resolve layout cell -> source, using only already displayed metadata."""
    paths = getattr(manager, 'flist', [])
    slot = source_slot(manager, grid)
    if slot is None:
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
        return dict(position=f'{tr("Frame")} {logical+1}/{counts[video]} | {tr("Video")} {video+1}/{len(videos)}',
                    source=os.path.abspath(os.path.expanduser(str(videos[video]))), detail=f'{tr("Time")} {timestamp}; {tr("original frame")} {physical+1}'
                    + ('; '+tr('sample every {n} frames').format(n=step) if step > 1 else ''), timestamp=timestamp)
    index = getattr(manager, '_status_source_index', None)
    if index is None:
        return None
    hint = int(getattr(manager, 'action_count', 0)) * max(1, int(manager.count_per_action)) + slot
    position, total, folder, folders = index.locate(paths[slot], hint)
    if position is None or folder is None:
        return None
    return dict(position=f'{tr("Image")} {position+1}/{total} | {tr("Folder")} {folder+1}/{folders}',
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


# Status bar events and display
class StatusBarMixin:
    def _init_status_bar(self):
        self._status_selected_grid = 0
        self._status_field_tooltips = [''] * 4
        style = self.main_status_bar.GetWindowStyleFlag() & ~(wx.STB_ELLIPSIZE_START | wx.STB_ELLIPSIZE_END)
        self.main_status_bar.SetWindowStyleFlag(style | wx.STB_ELLIPSIZE_MIDDLE)
        self.main_status_bar.Bind(wx.EVT_SIZE, self._on_status_bar_size)
        self.main_status_bar.Bind(wx.EVT_MOTION, self._on_status_bar_hover)
        self.main_status_bar.SetStatusText('Output: not set', 3)
        self._fit_status_fields()

    def _show_input_status(self, message=None, state='Ready', path=None, persistent=False):
        media='Video' if self.shared_config.video_mode else 'Image'
        mode=self.choice_input_mode.GetStringSelection()
        if message is None:
            message=('Video mode: please select a video input' if self.shared_config.video_mode
                     else 'Image mode: please select an image input')
        detail=f'{mode} | {tr(message)}'
        if path is not None:detail+=f' | {path}'
        action=f'{tr(media)} | {tr(state)}'
        self._input_feedback=(action,detail) if persistent else None
        self._input_feedback_state = state if persistent else None
        loaded=(getattr(self.ImgManager,'img_num',0) and
                bool(getattr(self.ImgManager,'video_mode',False))==bool(self.shared_config.video_mode))
        selection='-1' if loaded else 'No source loaded'
        self.SetStatusText_([action,selection,detail,'-1'])

    def _fit_status_fields(self):
        bar = self.main_status_bar
        width = bar.GetClientSize().width
        if width < 4:
            return
        scale = max(1, self.FromDIP(100)) / 100
        measured = [bar.GetTextExtent(bar.GetStatusText(i)).width / scale for i in range(4)]
        widths = tuple(round(value*scale) for value in status_widths(width/scale, measured))
        widths = widths[:-1] + (width-sum(widths[:-1]),)
        if widths != getattr(self, '_status_widths', None):
            self._status_widths = widths
            bar.SetStatusWidths(list(widths))

    def _on_status_bar_size(self, event):
        self._fit_status_fields()
        event.Skip()

    def _on_status_bar_hover(self, event):
        bar = self.main_status_bar
        for field in range(4):
            if bar.GetFieldRect(field).Contains(event.GetPosition()):
                if field==0:
                    tip=bar.GetStatusText(0)+'\n'+image_memory_tooltip(self.ImgManager,
                        getattr(self,'_status_canvas_info',None),getattr(self,'_status_selected_grid',0))
                else:
                    tip = (self._status_field_tooltips[field] if field in (1, 2) else '') or bar.GetStatusText(field)
                current = bar.GetToolTip()
                if not current or current.GetTip() != tip:
                    bar.SetToolTip(tip)
                break
        event.Skip()

    def SetStatusText_(self, texts):
        changed = False
        for field, text in enumerate(texts[:self.Status_number]):
            if text != '-1':
                if field==3 and getattr(self,'_export_active',False):text=self._export_status
                if field == 3:
                    self._last_output_message = text
                text = tr(str(text))
                if field == 3:
                    for prefix in ('Saving:', 'Output:'):
                        if text.startswith(prefix):
                            text = tr(prefix) + text[len(prefix):]
                            break
                if self.main_status_bar.GetStatusText(field) != str(text):
                    self.main_status_bar.SetStatusText(str(text), field)
                    changed = True
                if hasattr(self, '_status_field_tooltips'):
                    self._status_field_tooltips[field] = str(text)
        if changed:
            self._fit_status_fields()

    def update_status_bar_for_current_page(self, clicked_img_id=None):
        if clicked_img_id is not None:
            self._status_selected_grid = int(clicked_img_id)
        mapping = getattr(self.ImgManager, 'xy_grids_id_list', [])
        grid = getattr(self, '_status_selected_grid', 0)
        if not 0 <= grid < len(mapping):
            grid = 0
        info = selection_info(self.ImgManager, self.shared_config, grid)
        batch = getattr(self, '_status_display_batch', 0)
        pages = max(1, int(getattr(self.ImgManager, 'max_action_num', 1)))
        mode = 'Video' if self.shared_config.video_mode else 'Image'
        playback = 'Playing' if self.shared_config.is_playing else 'Paused'
        from .data import loaded_input_mode

        input_mode = tr(loaded_input_mode(self.ImgManager, self.shared_config, painted=True))
        position = info['position'] if info else tr('No source selected')
        if self.select_img_box.Value:
            total=min(len(self.xy_magnifier),len(getattr(self.ImgManager,'crop_points',())))
            selected=getattr(self,'box_id',-1)
            if 0<=selected<total:
                position+=f' | {tr("Box")} {selected+1}/{total}'
        feedback=getattr(self,'_input_feedback',None)
        source = f'{input_mode} | {info["source"]}' if info else input_mode
        if info and info['timestamp']:
            source += f' | {info["timestamp"]}'
        self.SetStatusText_([feedback[0] if feedback else f'{tr(mode)} | {tr(playback)}',
            f'{tr("Page")} {batch+1}/{pages} | {position}',feedback[1] if feedback else source,'-1'])
        if info:
            self._status_field_tooltips[1] = f'{tr("Page")} {batch+1}/{pages}\n{position}\n{info["detail"]}'
            if not feedback:self._status_field_tooltips[2] = f'{input_mode}\n{info["source"]}\n{info["detail"]}'
