"""Lazy global visual IDs, ordered by page, screen row and screen column."""
from bisect import bisect_right
from functools import lru_cache
import re
import os
from pathlib import Path
from types import SimpleNamespace
from .video_timeline import page_segments
from .video_paths import frame_filename


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
        self._visual_page = lru_cache(maxsize=2)(self._visual_page)
        self.cells=tuple(visual_cells(outer,inner,vertical))
        self.cell_algorithms={};self.cell_algorithm_indices={}
        self.algorithm_registry=getattr(manager,'_custom_algorithm_registry',()) or ()
        self.naming_manager=SimpleNamespace(path_list=tuple(manager.path_list),
            _status_source_index=getattr(manager,'_status_source_index',None))
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

    def _visual_page(self, page):
        """Compute one page of file references; no stat, image load or decoding."""
        items=[]
        if self.video:
            for video,first,stop in page_segments(self.counts,self.size,page,self.serial):
                for frame in range(first,stop):
                    if len(items)>=self.capacity:break
                    original=str(Path(self.paths[video]).absolute())
                    path=str(Path(self.cache_paths[video])/frame_filename(frame,self.fps[video],self.step))
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
        first,last,count,base=self.visual_ranges[interval]
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
                    candidates=sorted(set((self.prefix[video]+i)//self.size if self.serial else i//self.size for i in frames))
                    if candidates and not self.serial and any(i//self.size==(self.counts[video]-1)//self.size for i in frames):
                        first=candidates[0]
                        def repeated_pages():
                            for a,b,count,base in self.visual_ranges:
                                start=max(a,first)
                                if start<b and any(e['video']==video for y,x,e in self._visual_page(start)):
                                    yield from range(start,b)
                        candidates=repeated_pages()
                else:
                    haystack=(' '.join(self.source_row(video))+' '+self.cache_paths[video]).casefold()
                    if text not in haystack and text not in self.algorithm_search:continue
                    first=self.prefix[video]//self.size if self.serial else 0
                    last=(self.prefix[video+1]-1)//self.size if self.serial else self.pages-1
                    def visible_pages():
                        for a,b,count,base in self.visual_ranges:
                            start,end=max(a,first),min(b,last+1)
                            if start<end and any(e['video']==video for y,x,e in self._visual_page(start)):
                                yield from range(start,end)
                    candidates=visible_pages()
                for page in candidates:
                    if stop():return [],False
                    entries=self._visual_page(page)
                    base=self.visual_page_start(page)
                    for rank,(y,x,entry) in enumerate(entries):
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
