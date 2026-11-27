"""Image and video index data, the index window, and Excel export."""
import os
import re
import tempfile
import threading
import weakref
import wx
from bisect import bisect_right
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from itertools import chain
from pathlib import Path
from types import SimpleNamespace

from ..gui.index_table_gui import IndexTableGui
from .data import loaded_input_mode
from .image_encoding import manager_cache_format
from .status_bar import key
from .video_source import frame_filename, page_count, page_segments


# Index data, visual order, and Excel export
# Visual order and IDs
def visual_cells(outer, inner, vertical=(False,False)):
    """Invert renderer reshape_higher_dim, then visit global screen rows.

    Inner rows of adjacent outer groups interleave on screen; grouping source
    files first would assign the wrong IDs even when both flags are horizontal.
    """
    rows,cols=outer; subrows,subcols=inner
    for y in range(rows*subrows):
        for x in range(cols*subcols):
            oy,iy=divmod(y,subrows);ox,ix=divmod(x,subcols)
            group=ox*rows+oy if vertical[0] else oy*cols+ox
            item=ix*subrows+iy if vertical[1] else iy*subcols+ix
            yield y+1,x+1,group*(subrows*subcols)+item


class VisualCatalogMixin:
    def _init_visual(self, manager, config):
        layout=getattr(manager,'layout_params',[])
        if len(layout)>25:
            outer,inner=tuple(layout[0]),tuple(layout[1])
            vertical=(bool(layout[24]),bool(layout[25]))
        else:
            outer=(1,len(self.paths) if not self.linear else 1)
            inner=(1,self.size);vertical=(False,False)
        self._visual_page = lru_cache(maxsize=2)(self._build_visual_page)
        self.cells=tuple(visual_cells(outer,inner,vertical))
        self.cell_algorithms={};self.cell_algorithm_indices={}
        self.algorithm_registry=getattr(manager,'_custom_algorithm_registry',()) or ()
        self.naming_manager=SimpleNamespace(path_list=tuple(manager.path_list),
            _status_source_index=getattr(manager,'_status_source_index',None),
            video_mode=self.video,_cache_original_paths=tuple(config.real_video_path) if self.video else (),
            cache_save_format=manager_cache_format(manager))
        self.algorithm_root=Path(getattr(manager,'_algorithm_cache_root',Path('cache_frames')/'algorithms')).absolute()
        self.algorithm_search=' '.join(str(v) for entry in self.algorithm_registry for v in entry[:2]).casefold()
        self.capacity=len(self.cells)
        if len(layout)>40 and (layout[32] or layout[38]):
            from .custom_func.contract import display_grid, display_indices
            original=self.cells
            registry=getattr(manager,'_custom_algorithm_registry',()) or ()
            rows,cols=display_grid(registry,layout)
            selected=display_indices(registry,layout)
            variants=len(selected);column_first=bool(layout[40])
            cells=[]
            for pane in range(variants):
                if column_first:row=pane%rows;col=pane//rows
                else:row,col=divmod(pane,cols)
                for y,x,slot in original:
                    cell=(y+row*outer[0]*inner[0],x+col*outer[1]*inner[1],slot)
                    cells.append(cell)
                    index=selected[pane]
                    self.cell_algorithms[cell]='Original' if index is None else registry[index][0]
                    self.cell_algorithm_indices[cell]=index
            self.cells=tuple(sorted(cells))
        self.cache_extension='png' if manager_cache_format(manager)==1 else 'jpeg'
        self.cache_paths=tuple(str(Path(p).absolute()) for p in getattr(config,'video_path',manager.path_list))
        # Visible item counts are piecewise constant. Store only stream-end
        # breakpoints, never an entry per page or frame of a long video.
        points={0,self.pages}
        if self.linear:
            points.add(self.prefix[-1]//self.size)
        else:
            for n in self.counts:
                q=(n-1)//self.size if self.video and n else n//self.size
                points.update((q,q+1))
        points=sorted(p for p in points if 0<=p<=self.pages)
        self.visual_ranges=[];self.visual_ends=[];total=0
        for first,last in zip(points,points[1:]):
            count=len(self._visual_page(first))
            if count:
                self.visual_ranges.append((first,last,count,total))
                total+=(last-first)*count
                self.visual_ends.append(total)
        self.visual_total=total

    def _build_visual_page(self, page):
        """Compute one page of file references; no stat, image load or decoding."""
        items=[]
        if self.video:
            for video,first,stop in page_segments(self.counts,self.size,page,self.serial):
                for frame in range(first,stop):
                    if len(items)>=self.capacity:break
                    original=str(Path(self.paths[video]).absolute())
                    path=str(Path(self.cache_paths[video])/frame_filename(frame,self.fps[video],self.step,self.cache_extension))
                    seconds=frame*self.step/self.fps[video] if self.fps[video]>0 else 0
                    items.append(dict(source=original,path=path,label=f'Video {video+1}',
                                      item=f'Frame {frame+1}/{self.counts[video]} | {seconds:.3f}s',
                                      video=video,frame=frame))
                if len(items)>=self.capacity:break
        else:
            if self.linear:
                offsets=range(page*self.size,min((page+1)*self.size,self.sources))
            else:
                offsets=(self.prefix[v]+i for v,n in enumerate(self.counts)
                         for i in range(page*self.size,min((page+1)*self.size,n)))
            for offset in offsets:
                if len(items)>=self.capacity:break
                folder,local,path=self._image(offset)
                items.append(dict(source=path,path=path,label=f'Folder {folder+1}',item=f'Image {local+1}',offset=offset))
        from .cache_layout import processed_names, component
        from .custom_func.contract import specification
        names=processed_names(self.naming_manager,[item['path'] for item in items]) if self.cell_algorithms else ()
        visible=[]
        for y,x,slot in self.cells:
            if slot>=len(items):continue
            item=items[slot]
            algorithm=self.cell_algorithms.get((y,x,slot))
            if algorithm:
                index=self.cell_algorithm_indices[(y,x,slot)]
                spec=specification(self.algorithm_registry,index) if index is not None else {'identity':True}
                path=item['path'] if spec['identity'] else str(self.algorithm_root/component(algorithm)/'processed'/names[slot])
                item=dict(item,algorithm=algorithm,algorithm_path=self.algorithm_registry[index][1] if index is not None else '',
                    raw_path=item['path'],path=path,processed=not spec['identity'],item=item['item']+' | '+algorithm)
            visible.append((y,x,item))
        return visible

    def visual_entry(self, index):
        interval=bisect_right(self.visual_ends,index)
        first,_,count,base=self.visual_ranges[interval]
        page=first+(index-base)//count
        rank=(index-base)%count
        y,x,item=self._visual_page(page)[rank]
        return dict(item,id=index+1,page=page,row=y,column=x)

    def visual_row(self, index):
        entry=self.visual_entry(index)
        return (str(index+1),str(entry['page']+1),entry['label'],entry['item'],entry['source'],
                f'Row {entry["row"]}, Col {entry["column"]}',entry['path'], 'Checking...' if self.video or entry.get('processed') else 'Original')

    def visual_page_start(self, page):
        for first,last,count,base in self.visual_ranges:
            if first<=page<last:return base+(page-first)*count
        return self.visual_total

    def _visible_video_pages(self, video, first, last):
        """Keep lazy page iteration bound to one video and its page limits."""
        for a,b,_,_ in self.visual_ranges:
            start,end=max(a,first),min(b,last+1)
            if start<end and any(entry['video']==video for _,_,entry in self._visual_page(start)):
                yield from range(start,end)

    def visual_search(self, text, stop, limit=10000):
        text=text.strip().casefold();matches=[]
        if not text:return [],False
        if text.startswith('page:'):
            try:page=int(text[5:])-1
            except ValueError:return [],False
            if not 0<=page<self.pages:return [],False
            first=self.visual_page_start(page);last=self.visual_page_start(page+1)
            return list(range(first,min(last,first+limit))),last-first>limit
        if text.startswith('id:'):
            try:index=int(text[3:])-1
            except ValueError:return [],False
            return ([index] if 0<=index<self.visual_total else []),False
        if self.video:
            # Timestamp + frame-in-second narrows full-path queries to a few
            # candidate ordinals, including fractional-FPS rounding.
            exact=re.search(r'(\d+(?:\.\d+)?)s_frame_\d+\.(?:jpeg|png)$',text)
            matched=set()
            for video in range(len(self.paths)):
                if stop():return [],False
                if exact:
                    filename=exact.group(0)
                    guess=round(float(exact.group(1))*self.fps[video]/self.step)
                    radius=max(2,int(self.fps[video]*.006/self.step)+2)
                    frames=[i for i in range(max(0,guess-radius),min(self.counts[video],guess+radius+1))
                            if (Path(frame_filename(i,self.fps[video],self.step)).stem+'.'+filename.rsplit('.',1)[-1]).casefold()==filename]
                    candidates=sorted({(self.prefix[video]+i)//self.size if self.serial else i//self.size for i in frames})
                    if candidates and not self.serial and any(i//self.size==(self.counts[video]-1)//self.size for i in frames):
                        first=candidates[0]
                        candidates=self._visible_video_pages(video,first,self.pages-1)
                else:
                    haystack=(' '.join(self.source_row(video))+' '+self.cache_paths[video]).casefold()
                    if text not in haystack and text not in self.algorithm_search:continue
                    first=self.prefix[video]//self.size if self.serial else 0
                    last=(self.prefix[video+1]-1)//self.size if self.serial else self.pages-1
                    candidates=self._visible_video_pages(video,first,last)
                for page in candidates:
                    if stop():return [],False
                    entries=self._visual_page(page)
                    base=self.visual_page_start(page)
                    for rank,(_,_,entry) in enumerate(entries):
                        if entry['video']!=video or (exact and entry['frame'] not in frames):continue
                        if exact and '/' not in text and '\\' not in text and Path(entry['path']).name.casefold()!=filename:continue
                        if exact and ('/' in text or '\\' in text):
                            query=os.path.normcase(os.path.normpath(str(Path(text).absolute()))).casefold()
                            paths=(entry['path'],entry.get('raw_path',''))
                            if not any(os.path.normcase(os.path.normpath(p)).casefold()==query for p in paths if p):continue
                        if not exact and text not in (' '.join(map(str,entry.values()))+' '+haystack).casefold():continue
                        matched.add(base+rank)
                    if len(matched)>=limit:return sorted(matched)[:limit],True
            return sorted(matched),False
        for index in range(self.visual_total):
            if stop():return [],False
            if text and text in ' '.join(self.visual_row(index)).casefold():
                matches.append(index)
                if len(matches)>=limit:return matches,True
        return matches,False


# Source and page catalog
class IndexCatalog(VisualCatalogMixin):
    columns = ('ID', 'Page(s)', 'Source', 'Image / frame', 'Original source', 'Visual position', 'Image / frame path', 'Cache state')

    def __init__(self, manager, config, parallel_sequential=False):
        self.video = bool(config.video_mode)
        self.kind = manager.type
        self.serial = bool(config.parallel_to_sequential if self.video else manager.parallel_to_sequential)
        layout = getattr(manager, 'layout_params', ())
        self.parallel_sequential = bool(layout[22] if len(layout) > 22 else parallel_sequential)
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
        self.input_mode = loaded_input_mode(manager, config)
        parallel = len(self.paths) > 1 if self.video else self.kind in (0, 1)
        self.order = ('parallel_to_sequential' if self.serial else
                      'parallel_sequential' if self.parallel_sequential else 'parallel') if parallel else 'sequential'

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


# Columns shared by the virtual table and the Excel export.
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


# Excel export
EXCEL_ROWS = 1048576
MAX_TEXT_UNITS = 32000


def _text_parts(value):
    """Excel counts UTF-16 code units, not Python Unicode code points."""
    encoded = value.encode('utf-16-le')
    start = 0
    while start < len(encoded):
        end = min(len(encoded),start+MAX_TEXT_UNITS*2)
        if end < len(encoded) and 0xD800 <= int.from_bytes(encoded[end-2:end],'little') <= 0xDBFF:
            end -= 2
        yield encoded[start:end].decode('utf-16-le')
        start = end


def write_index_xlsx(path, model, view, cancelled=lambda:False, cache_states=None, sheet_rows=EXCEL_ROWS):
    try:
        from xlsxwriter import Workbook
    except ImportError as error:
        raise RuntimeError('Excel export requires XlsxWriter; install the updated requirements.txt') from error
    if not 2 <= sheet_rows <= EXCEL_ROWS:
        raise ValueError('Invalid Excel worksheet row limit')
    path = Path(path)
    columns = view_columns(view,model.video)
    cache_states = cache_states or {}
    total = model.rows(view)
    with tempfile.TemporaryDirectory(prefix='.index_excel_',dir=path.parent) as work:
        temporary = Path(work)/'index.xlsx'
        with Workbook(str(temporary), {'constant_memory': True, 'strings_to_formulas': False,
                                      'strings_to_urls': False, 'tmpdir': work, 'use_zip64': True}) as workbook:
            title = workbook.add_format({'bold':True,'font_color':'white','bg_color':'#30577E',
                                         'text_wrap':True,'valign':'vcenter'})
            body = workbook.add_format({'text_wrap':True,'valign':'top'})
            info = workbook.add_worksheet('Info')
            info.set_column(0,0,24); info.set_column(1,1,70)
            for row,values in enumerate((('View',VIEW_NAMES[view]),('Media','Video' if model.video else 'Image'),
                                        ('Input mode',getattr(model,'input_mode','Input')),
                                        ('Order',model.order),('Records',total),
                                        ('Created UTC',datetime.now(timezone.utc).isoformat()),
                                        ('Cache state','Snapshot of checked files; Not checked does not mean missing'),
                                        ('Long text','Cells beyond Excel text limits continue in Long text sheets'))):
                info.write_row(row,0,values,body)
            sheet = None; row = 0; number = 0
            long_sheet = None; long_row = 0; long_number = 0
            for index in range(max(1,total)):
                if cancelled():
                    raise CancelledError('Index export canceled')
                if sheet is None or row >= sheet_rows:
                    if sheet is not None:sheet.autofilter(0,0,row-1,len(columns)-1)
                    number += 1
                    sheet = workbook.add_worksheet(f'{VIEW_NAMES[view]} {number}')
                    sheet.freeze_panes(1,1)
                    for col,column in enumerate(columns):sheet.set_column(col,col,max(10,min(75,column.width/7)))
                    sheet.set_row(0,30)
                    sheet.write_row(0,0,[c.label for c in columns],title)
                    row = 1
                if not total:break
                values = list(view_row(model,view,index))
                if view == 2:
                    entry = model.visual_entry(index)
                    frame_path = entry['path']
                    cached = model.video or entry.get('processed',False)
                    state = cache_states.get(frame_path)
                    values[-1] = ('Not checked' if state is None else
                                  ('Cached' if cached else 'Exists') if state else
                                  ('Virtual / not cached' if cached else 'Missing'))
                for col,value in enumerate(values):
                    if not isinstance(value,str) or len(value) < 16000:
                        continue
                    parts = iter(_text_parts(value))
                    first = next(parts,'')
                    rest = next(parts,None)
                    if rest is None:continue
                    values[col] = first+'\n[Full text continues in Long text sheets]'
                    for part,chunk in enumerate(chain((first,rest),parts),1):
                        if long_sheet is None or long_row >= sheet_rows:
                            long_number += 1
                            long_sheet = workbook.add_worksheet(f'Long text {long_number}')
                            long_sheet.freeze_panes(1,0)
                            long_sheet.set_column(0,0,20);long_sheet.set_column(1,3,12);long_sheet.set_column(4,4,75)
                            long_sheet.write_row(0,0,('Sheet','Excel row','Column','Part','Text'),title)
                            long_row = 1
                        long_sheet.write_row(long_row,0,(sheet.name,row+1,columns[col].label,part,chunk),body)
                        long_row += 1
                sheet.write_row(row,0,values,body)
                row += 1
            if sheet is not None:sheet.autofilter(0,0,max(0,row-1),len(columns)-1)
        if cancelled():
            raise CancelledError('Index export canceled')
        os.replace(temporary,path)
    return total


# Index window and user interactions
from .localization import bind_window, tr


class IndexTable(IndexTableGui):
    def __init__(self, parent, catalog, out_path_str='', on_jump=None, refresh=None, auto_export=False, show=True, on_locate=None, on_jump_item=None):
        super().__init__(parent)
        self.catalog = catalog
        self.out_path_str = out_path_str
        self.on_jump, self.refresh_model = on_jump, refresh
        self.on_locate, self.on_jump_item = on_locate, on_jump_item
        self.locate_main_button.Enable(on_locate is not None)
        self._closed = False
        self._revision = 0
        self._cache_states = {}
        self._probe_future = None
        self._selected_entry = None
        self.m_search_txt.SetDescriptiveText('Name, path, page:12 or id:25')
        self._stop = threading.Event()
        self._search_cancel = threading.Event()
        self._workers = ThreadPoolExecutor(2, thread_name_prefix='index-table')
        self.id_list, self.id = [], 0
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self.change_view(None)
        self.resize_controls_row(None)
        self.Layout()
        self._probe_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER,self._probe_visible,self._probe_timer)
        self._probe_timer.Start(500)
        bind_window(self)
        self.Show(show)
        if auto_export and out_path_str:
            self._export(Path(out_path_str)/export_filename(0,catalog.video),view=0)

    def change_view(self, event):
        self._search_cancel.set()
        self._revision += 1
        self.id_list, self.id = [], 0
        caption = self.view_choice.GetStringSelection()
        self.view = next((i for i, name in enumerate(('Sources', 'Pages', 'Visual items'))
                          if caption in (name, tr(name))), 0)
        self.index_table.SetItemCount(0)
        self.index_table.DeleteAllColumns()
        for number,column in enumerate(view_columns(self.view,self.catalog.video)):
            self.index_table.InsertColumn(number,tr(column.label),width=column.width)
        self.index_table.get_row = self._display_row
        self.index_table.SetItemCount(self.catalog.rows(self.view))
        self.index_table.Refresh()
        self._refresh_language()
        self._selected_entry = None
        self._selected_index = None
        self.path_details.ChangeValue('')
        self.copy_frame_button.Disable(); self.copy_source_button.Disable(); self.jump_button.Disable()
        self._update_buttons()

    def _refresh_language(self):
        self.m_search_txt.SetDescriptiveText(tr('Name, path, page:12 or id:25'))
        for n, column in enumerate(view_columns(self.view, self.catalog.video)):
            item = self.index_table.GetColumn(n)
            item.SetText(tr(column.label))
            self.index_table.SetColumn(n, item)
        mode = tr('Video' if self.catalog.video else 'Image')
        self.summary.SetLabel(tr('{mode} | {input} | {pages} pages | {sources} source entries | {items} visual items').format(
            mode=mode, input=tr(self.catalog.input_mode), pages=self.catalog.pages, sources=self.catalog.sources, items=self.catalog.visual_total))
        self.match_label.SetLabel(tr('Double-click a row to go to its page; counters start at 1'))

    def _update_buttons(self):
        self.b_last_txt.Enable(bool(self.id_list) and self.id > 0)
        self.b_next_txt.Enable(bool(self.id_list) and self.id < len(self.id_list)-1)

    def search_txt(self, event):
        if self.m_search_txt.GetValue().strip().casefold().startswith('id:') and self.view!=2:
            self._choose_view(2)
            self.change_view(None)
        self._revision += 1
        revision = self._revision
        query = self.m_search_txt.GetValue()
        self._search_cancel.set()
        self._search_cancel = cancel = threading.Event()
        model, view, stop = self.catalog, self.view, self._stop
        self.match_label.SetLabel(tr('Searching...'))
        ref = weakref.ref(self)
        future = self._workers.submit(model.search, query, view, lambda: stop.is_set() or cancel.is_set())
        def done(completed):
            if completed.cancelled():
                return
            try:
                matches, limited = completed.result()
            except Exception:
                matches, limited = [], False
            def deliver():
                owner = ref()
                if owner is None or owner._closed or owner._revision != revision:
                    return
                owner.id_list, owner.id = matches, 0
                owner._matches_limited = limited
                owner.match_label.SetLabel(tr('{count} matches').format(count=str(len(matches))+('+' if limited else '')) if matches else tr('No matches'))
                owner.set_pos(0)
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def clear_search(self, event):
        self._search_cancel.set()
        self._revision += 1
        self.m_search_txt.ChangeValue('')
        self.id_list, self.id = [], 0
        self.match_label.SetLabel(tr('Search cleared'))
        self._update_buttons()

    def set_pos(self, index):
        if self.id_list:
            self.id = max(0,min(index,len(self.id_list)-1))
            row = self.id_list[self.id]
            self.index_table.Select(row)
            self.index_table.Focus(row)
            self.index_table.EnsureVisible(row)
            self.match_label.SetLabel(tr('Match {current}/{total}').format(current=self.id+1,total=len(self.id_list))
                                     + (tr(' (first 10000)') if getattr(self,'_matches_limited',False) else ''))
        self._update_buttons()

    def next_txt(self, event):
        self.set_pos(self.id+1)

    def last_txt(self, event):
        self.set_pos(self.id-1)

    def activate_row(self, event):
        self._jump_row(event.GetIndex())

    def refresh_index(self, event):
        if self.refresh_model:
            self.catalog = self.refresh_model()
        self.change_view(None)

    def export_index(self, event):
        with wx.FileDialog(self, tr('Export index'), defaultDir=self.out_path_str,
                           defaultFile=export_filename(self.view,self.catalog.video), wildcard='Excel workbook (*.xlsx)|*.xlsx',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self._export(Path(dialog.GetPath()))

    def _export(self, path, view=None):
        model, view, stop = self.catalog, self.view if view is None else view, self._stop
        self.export_button.Disable()
        self.match_label.SetLabel(tr('Exporting index...'))
        if Path(path).suffix.lower() != '.xlsx':
            self.export_button.Enable()
            self.match_label.SetLabel(tr('Use the .xlsx extension for Excel export'))
            return
        states = dict(self._cache_states)
        def write():
            return write_index_xlsx(path,model,view,stop.is_set,states)
        future = self._workers.submit(write)
        ref = weakref.ref(self)
        def done(completed):
            try:
                completed.result()
                message = tr('Exported: {path}').format(path=path)
            except Exception as error:
                message = tr('Export failed: {error}').format(error=error)
            def deliver():
                owner = ref()
                if owner is not None and not owner._closed:
                    owner.export_button.Enable()
                    owner.match_label.SetLabel(message)
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._shutdown()
        event.Skip()

    def _shutdown(self):
        self._closed = True
        if hasattr(self,'_probe_timer'):self._probe_timer.Stop()
        self._stop.set()
        self._search_cancel.set()
        self._workers.shutdown(wait=False,cancel_futures=True)

    def close(self, event):
        self._shutdown()
        self.Destroy()

    def _display_row(self, index):
        values=self.catalog.row(self.view,index)
        if self.view==2:
            state=self._cache_states.get(values[6])
            cached=self.catalog.video or self.catalog.visual_entry(index).get('processed',False)
            status=('Cached' if cached else 'Exists') if state else ('Virtual / not cached' if cached else 'Missing')
            values=values[:-1]+(tr('Checking...' if state is None else status),)
        return tuple(str(value) for value in view_row(self.catalog,self.view,index,values))

    def _probe_visible(self, event):
        if self._closed or self.view!=2 or (self._probe_future and not self._probe_future.done()):return
        first=max(0,self.index_table.GetTopItem())
        last=min(self.catalog.visual_total,first+min(80,max(1,self.index_table.GetCountPerPage()+1)))
        if last<=first:return
        paths=[self.catalog.row(2,row)[6] for row in range(first,last)]
        if self._selected_entry:paths.append(self._selected_entry['path'])
        future=self._workers.submit(lambda:{path:Path(path).is_file() for path in paths})
        self._probe_future=future; ref=weakref.ref(self)
        def done(completed):
            if completed.cancelled():return
            try:states=completed.result()
            except OSError:states={}
            def deliver():
                owner=ref()
                if owner is None or owner._closed:return
                owner._cache_states.update(states)
                while len(owner._cache_states)>512:owner._cache_states.pop(next(iter(owner._cache_states)))
                owner.index_table.Refresh()
                selected=owner.index_table.GetFirstSelected()
                if selected<0:selected=getattr(owner,'_selected_index',None)
                if selected is not None and selected>=0:owner._select_index(selected,preserve_details=True)
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def select_row(self, event):
        self._select_index(event.GetIndex())

    def _select_index(self, index, preserve_details=False):
        self._selected_index=index
        if self.view==2:
            entry=self.catalog.visual_entry(index)
            state=self._cache_states.get(entry['path'])
            cached=self.catalog.video or entry.get('processed',False)
            cache='Checking...' if state is None else ('Cached' if cached else 'Exists') if state else ('Virtual / not cached' if cached else 'Missing')
            text=f'ID {entry["id"]} | {tr("Page")} {entry["page"]+1} | {tr("Row")} {entry["row"]}, {tr("Col")} {entry["column"]} | {tr(cache)}\n{tr("Original source")}: {entry["source"]}\n{tr("Image / frame path")}: {entry["path"]}'
            if entry.get('algorithm'):
                text+=f'\n{tr("Algorithm")}: {entry["algorithm"]}\n{tr("Algorithm path")}: {entry.get("algorithm_path","")}\n{tr("Raw image / frame path")}: {entry.get("raw_path",entry["path"])}'
        elif self.view==0:
            source=str(Path(self.catalog.paths[index]).absolute()) if self.catalog.video else self.catalog._image(index)[2]
            entry=dict(source=source,path=source if not self.catalog.video else '',page=self.catalog.target(0,index))
            text='\n'.join(self.catalog.row(0,index))
        else:
            entry=dict(source='',path='',page=index)
            text='\n'.join(self.catalog.row(1,index))
        self._selected_entry=entry
        details=self.path_details
        selection=details.GetSelection()
        reading=preserve_details and (details.HasFocus() or selection[0]!=selection[1])
        if details.GetValue()!=text and not reading:
            position=details.GetInsertionPoint()
            scroll=details.GetScrollPos(wx.VERTICAL)
            details.ChangeValue(text)
            if preserve_details:
                details.SetInsertionPoint(min(position,details.GetLastPosition()))
                details.ScrollLines(scroll-details.GetScrollPos(wx.VERTICAL))
        self.copy_frame_button.Enable(bool(entry['path']))
        self.copy_source_button.Enable(bool(entry['source']))
        self.jump_button.Enable(True)

    def _copy_path(self, value):
        if value and wx.TheClipboard.Open():
            try:wx.TheClipboard.SetData(wx.TextDataObject(value))
            finally:wx.TheClipboard.Close()

    def copy_frame_path(self,event):
        if self._selected_entry:self._copy_path(self._selected_entry['path'])

    def copy_source_path(self,event):
        if self._selected_entry:self._copy_path(self._selected_entry['source'])

    def jump_selected(self,event):
        if self._selected_index is not None:
            self._jump_row(self._selected_index)

    def _jump_row(self, index):
        page = self.catalog.target(self.view,index)
        if self.on_jump_item:
            first, last = self.catalog.visual_page_start(page), self.catalog.visual_page_start(page+1)
            rank = index-first if self.view == 2 else 0
            if self.view == 0:
                for candidate in range(first,last):
                    entry = self.catalog.visual_entry(candidate)
                    same = entry.get('video') == index if self.catalog.video else entry.get('offset') == index
                    if same:
                        rank = candidate-first
                        break
            accepted = self.on_jump_item(page,rank,getattr(self.catalog,'context',None))
            if accepted is False:
                self.match_label.SetLabel(tr('Main layout/input changed. Refresh the index before jumping.'))
        elif self.on_jump:
            self.on_jump(page)

    def locate_main_image(self,event):
        if not self.on_locate:
            return
        # Refresh a potentially stale snapshot, then use the displayed main page.
        self.refresh_index(None)
        location = self.on_locate()
        if not self.catalog.pages or not self.catalog.visual_total:
            self.match_label.SetLabel(tr('No displayed image to locate'))
            return
        page = max(0,min(int(location['page']),self.catalog.pages-1))
        first,last = self.catalog.visual_page_start(page), self.catalog.visual_page_start(page+1)
        if first == last:
            self.match_label.SetLabel(tr('No visible image on this page'))
            return
        rank = int(location.get('rank',0))
        index = first+rank if 0 <= rank < last-first else first
        self._choose_view(2)
        self.change_view(None)
        self.index_table.Select(index)
        self.index_table.Focus(index)
        self.index_table.EnsureVisible(index)
        self._select_index(index)
        self.match_label.SetLabel(tr('Located Visual ID {item} on page {page}').format(item=index+1,page=page+1))

    def _choose_view(self, view):
        """Resolve semantic view IDs independently of the FBP choice order."""
        caption = ('Sources', 'Pages', 'Visual items')[view]
        index = self.view_choice.FindString(tr(caption))
        if index != wx.NOT_FOUND:
            self.view_choice.SetSelection(index)

    def resize_controls_row(self, event):
        """Preserve FBP sizes, increasing minima only to fit native font/DPI."""
        # FlexGridSizer updates rows sequentially. Do not recalculate its
        # minima inside a child SIZE event while the parent is still laying out.
        if event is not None:
            event.Skip()
            if not getattr(self, '_controls_resize_pending', False):
                self._controls_resize_pending = True
                wx.CallAfter(self.resize_controls_row, None)
            return
        self._controls_resize_pending = False
        if getattr(self, '_closed', False) or not self:
            return
        panel = self.m_search_txt.GetParent()
        if panel.GetSizer() is not None:
            if not hasattr(panel, '_fbp_min_height'):
                panel._fbp_min_height = panel.GetMinSize().height
            row = panel.GetSizer().GetMinSize()
            needs_scroll = isinstance(panel,wx.ScrolledWindow) and row.width > panel.GetClientSize().width
            scrollbar = max(0, wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y, panel)) if needs_scroll else 0
            # Native control metrics can change after the first layout (font,
            # DPI, wx version). WrapSizer's cached minimum can then be too low.
            content=max([row.height]+[item.GetWindow().GetRect().GetBottom()+item.GetBorder()+1
                for item in panel.GetSizer().GetChildren() if item.GetWindow() and item.IsShown()])
            required = max(panel._fbp_min_height, content + scrollbar)
            if panel.GetMinSize().height != required:
                panel.SetMinSize((panel.GetMinSize().width, required))
                self.Layout()
            if isinstance(panel,wx.ScrolledWindow):panel.FitInside()
        root = self.GetSizer()
        if root is not None:
            if not hasattr(self, '_fbp_index_min_height'):
                self._fbp_index_min_height = self.GetMinSize().height
            decoration = self.GetSize().height - self.GetClientSize().height
            minimum = max(self._fbp_index_min_height, root.GetMinSize().height + decoration)
            if self.GetMinSize().height != minimum:
                self.SetMinSize((self.GetMinSize().width, minimum))
                if self.GetSize().height < minimum:
                    self.SetSize((self.GetSize().width, minimum))
        if event is not None:
            event.Skip()
