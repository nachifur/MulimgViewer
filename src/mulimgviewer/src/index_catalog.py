"""Lazy, metadata-only source/page index shared by the index-table window."""
from bisect import bisect_right
from .status_info import key
from pathlib import Path
from .video_timeline import page_count, page_segments
from .visual_catalog import VisualCatalogMixin


class IndexCatalog(VisualCatalogMixin):
    columns = ('ID', 'Page(s)', 'Source', 'Image / frame', 'Original source', 'Visual position', 'Image / frame path', 'Cache state')

    def __init__(self, manager, config, parallel_sequential=False):
        self.video = bool(config.video_mode)
        self.kind = manager.type
        self.serial = bool(config.parallel_to_sequential if self.video else manager.parallel_to_sequential)
        self.parallel_sequential = bool(parallel_sequential)
        self.linear = self.serial or (not self.video and self.kind in (2,3))
        self.size = max(1, int(manager.count_per_action))
        self.paths = tuple(config.real_video_path if self.video else manager.path_list)
        self.names = manager.name_list if not self.video else None
        self._row_cache = {}
        self.folder_ids = {}
        if not self.video and self.kind == 3:
            for path in self.paths:
                self.folder_ids.setdefault(key(Path(path).parent), len(self.folder_ids))
        self.step = max(1, int(config.skip_frames)+1)
        self.fps = tuple(config.video_fps_list)
        if self.video:
            self.counts = tuple(max(0, int(n)) for n in config.video_num_list)
        elif self.kind == 3:
            self.counts = (len(self.paths),)
        elif self.serial:
            self.counts = tuple(len(names) for names in self.names)
        else:
            self.counts = tuple(len(self.names) for _ in self.paths)
        self.prefix = [0]
        for count in self.counts:
            self.prefix.append(self.prefix[-1]+count)
        self.pages = page_count(self.counts, self.size, self.linear)
        self.sources = len(self.paths) if self.video else self.prefix[-1]
        self._init_visual(manager,config)
        self.order = 'parallel_to_sequential' if self.serial else ('parallel_sequential' if self.parallel_sequential else 'parallel')

    def _image(self, offset):
        if self.kind == 3:
            return self.folder_ids[key(Path(self.paths[offset]).parent)], offset, str(Path(self.paths[offset]).absolute())
        folder = bisect_right(self.prefix, offset)-1
        local = offset-self.prefix[folder]
        names = self.names[folder] if self.serial else self.names
        return folder, local, str((Path(self.paths[folder])/str(names[local])).absolute())

    def source_row(self, offset):
        if self.video:
            count = self.counts[offset]
            first = self.prefix[offset]//self.size if self.serial else 0
            last = (self.prefix[offset+1]-1)//self.size if self.serial else self.pages-1
            fps = self.fps[offset]
            duration = (count-1)*self.step/fps if count and fps > 0 else 0
            return (str(offset+1), f'{first+1}-{last+1}' if count else '-',
                    f'Video {offset+1}', f'Frames 1-{count}' if count else 'No frames',
                    f'{Path(self.paths[offset]).absolute()} | 0-{duration:.3f}s | sample step {self.step}')
        folder, local, path = self._image(offset)
        page = offset//self.size if self.linear else local//self.size
        return (str(offset+1), str(page+1), f'Folder {folder+1}',
                f'Image {local+1}', path)

    def page_row(self, batch):
        if self.video:
            spans = page_segments(self.counts, self.size, batch, self.serial)
            return (str(batch+1), str(batch+1), '; '.join(f'Video {v+1}' for v,a,b in spans),
                    '; '.join(f'{a+1}-{b}' for v,a,b in spans),
                    '; '.join(f'{Path(self.paths[v]).absolute()} [{a*self.step/self.fps[v]:.3f}s]'
                              if self.fps[v] > 0 else str(self.paths[v]) for v,a,b in spans))
        if self.linear:
            offsets = range(batch*self.size, min((batch+1)*self.size, self.sources))
        else:
            offsets = (self.prefix[folder]+i for folder,count in enumerate(self.counts)
                       for i in range(batch*self.size, min((batch+1)*self.size,count)))
        items = [self._image(i) for i in offsets]
        return (str(batch+1), str(batch+1), '; '.join(dict.fromkeys(f'Folder {f+1}' for f,i,p in items)),
                '; '.join(str(i+1) for f,i,p in items), '; '.join(p for f,i,p in items))

    def rows(self, view):
        return self.visual_total if view == 2 else self.sources if view == 0 else self.pages

    def row(self, view, index):
        cache_key = (view,index)
        if cache_key not in self._row_cache:
            if len(self._row_cache) >= 128:
                self._row_cache.pop(next(iter(self._row_cache)))
            values = self.visual_row(index) if view == 2 else self.source_row(index) if view == 0 else self.page_row(index)
            self._row_cache[cache_key] = values + ('',)*(len(self.columns)-len(values))
        return self._row_cache[cache_key]

    def target(self, view, row):
        if view == 2:return self.visual_entry(row)['page']
        if view == 1:
            return row
        if self.video:
            return self.prefix[row]//self.size if self.serial else 0
        folder, local, path = self._image(row)
        return row//self.size if self.linear else local//self.size

    def search(self, text, view, stop, limit=10000):
        if view == 2:return self.visual_search(text,stop,limit)
        text = text.strip().casefold()
        if not text:
            return [], False
        if text.startswith('page:'):
            try:
                page = int(text[5:])-1
            except ValueError:
                return [], False
            if not 0 <= page < self.pages:
                return [], False
            if view == 1:
                return [page], False
        matches = set()
        page_query = text.startswith('page:')
        for index in range(self.sources):
            if stop():
                return [], False
            row = self.source_row(index)
            if page_query:
                first = self.target(0,index)
                last = ((self.prefix[index+1]-1)//self.size if self.serial else self.pages-1) if self.video else first
                found = first <= page <= last
            else:
                found = text in ' '.join(row).casefold()
            if found:
                if view == 0:
                    matches.add(index)
                elif self.video:
                    first = self.target(0, index)
                    last = (self.prefix[index+1]-1)//self.size if self.serial else self.pages-1
                    matches.update(range(first, min(last+1, first+limit)))
                else:
                    matches.add(self.target(0,index))
            if len(matches) >= limit:
                return sorted(matches)[:limit], True
        return sorted(matches), False
