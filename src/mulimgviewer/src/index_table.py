"""Searchable, exportable source/page index without decoding or scanning videos."""
import os
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import wx
from ..gui.index_table_gui import IndexTableGui
from .index_catalog import IndexCatalog


class IndexTable(IndexTableGui):
    def __init__(self, parent, catalog, out_path_str='', on_jump=None, refresh=None, auto_export=False, show=True):
        super().__init__(parent)
        self.catalog = catalog
        self.out_path_str = out_path_str
        self.on_jump, self.refresh_model = on_jump, refresh
        self._closed = False
        self._revision = 0
        self._cache_states = {}
        self._probe_future = None
        self._selected_entry = None
        for column,label in enumerate(catalog.columns):
            self.index_table.InsertColumn(column,label,width=(65,80,100,140,250,110,300,95)[column])
        self.m_search_txt.SetDescriptiveText('Name, path, page:12 or id:25')
        self._stop = threading.Event()
        self._search_cancel = threading.Event()
        self._workers = ThreadPoolExecutor(2, thread_name_prefix='index-table')
        self.id_list, self.id = [], 0
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self.change_view(None)
        self._probe_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER,self._probe_visible,self._probe_timer)
        self._probe_timer.Start(500)
        self.Show(show)
        if auto_export and out_path_str:
            self._export(Path(out_path_str)/'index_table.txt',view=0)

    def change_view(self, event):
        self._search_cancel.set()
        self._revision += 1
        self.id_list, self.id = [], 0
        self.view = self.view_choice.GetSelection()
        self.index_table.get_row = self._display_row
        self.index_table.SetItemCount(self.catalog.rows(self.view))
        self.index_table.Refresh()
        mode = 'Video' if self.catalog.video else 'Image'
        self.summary.SetLabel(f'{mode} | {self.catalog.order} | {self.catalog.pages} pages | '
                              f'{self.catalog.sources} source entries | {self.catalog.visual_total} visual items')
        self.match_label.SetLabel('Double-click a row to go to its page; counters start at 1')
        self._selected_entry = None
        self._selected_index = None
        heading=self.index_table.GetColumn(0)
        heading.SetText('Visual ID' if self.view==2 else 'Source #' if self.view==0 else 'Page')
        self.index_table.SetColumn(0,heading)
        self.path_details.ChangeValue('')
        self.copy_frame_button.Disable(); self.copy_source_button.Disable(); self.jump_button.Disable()
        self._update_buttons()

    def _update_buttons(self):
        self.b_last_txt.Enable(bool(self.id_list) and self.id > 0)
        self.b_next_txt.Enable(bool(self.id_list) and self.id < len(self.id_list)-1)

    def search_txt(self, event):
        if self.m_search_txt.GetValue().strip().casefold().startswith('id:') and self.view!=2:
            self.view_choice.SetSelection(2)
            self.change_view(None)
        self._revision += 1
        revision = self._revision
        query = self.m_search_txt.GetValue()
        self._search_cancel.set()
        self._search_cancel = cancel = threading.Event()
        model, view, stop = self.catalog, self.view, self._stop
        self.match_label.SetLabel('Searching...')
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
                owner.match_label.SetLabel(f'{len(matches)}'+('+' if limited else '')+' matches' if matches else 'No matches')
                owner.set_pos(0)
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def clear_search(self, event):
        self._search_cancel.set()
        self._revision += 1
        self.m_search_txt.ChangeValue('')
        self.id_list, self.id = [], 0
        self.match_label.SetLabel('Search cleared')
        self._update_buttons()

    def set_pos(self, index):
        if self.id_list:
            self.id = max(0,min(index,len(self.id_list)-1))
            row = self.id_list[self.id]
            self.index_table.Select(row)
            self.index_table.Focus(row)
            self.index_table.EnsureVisible(row)
            self.match_label.SetLabel(f'Match {self.id+1}/{len(self.id_list)}'
                                     + (' (first 10000)' if getattr(self,'_matches_limited',False) else ''))
        self._update_buttons()

    def next_txt(self, event):
        self.set_pos(self.id+1)

    def last_txt(self, event):
        self.set_pos(self.id-1)

    def activate_row(self, event):
        if self.on_jump:
            self.on_jump(self.catalog.target(self.view,event.GetIndex()))

    def refresh_index(self, event):
        if self.refresh_model:
            self.catalog = self.refresh_model()
        self.change_view(None)

    def export_index(self, event):
        with wx.FileDialog(self, 'Export index', defaultDir=self.out_path_str,
                           defaultFile='index_table.txt', wildcard='Text (*.txt)|*.txt',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self._export(Path(dialog.GetPath()))

    def _export(self, path, view=None):
        model, view, stop = self.catalog, self.view if view is None else view, self._stop
        self.export_button.Disable()
        self.match_label.SetLabel('Exporting index...')
        def write():
            temporary = path.with_name('.'+path.name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
            try:
                with temporary.open('w',encoding='utf-8') as stream:
                    stream.write('\t'.join(model.columns)+'\n')
                    for row in range(model.rows(view)):
                        if stop.is_set():
                            return
                        values = model.visual_row(row) if view == 2 else model.source_row(row) if view == 0 else model.page_row(row)
                        values += ('',)*(len(model.columns)-len(values))
                        stream.write('\t'.join(value.replace('\n',' ') for value in values)+'\n')
                os.replace(temporary,path)
            finally:
                temporary.unlink(missing_ok=True)
        future = self._workers.submit(write)
        ref = weakref.ref(self)
        def done(completed):
            try:
                completed.result()
                message = f'Exported: {path}'
            except Exception as error:
                message = f'Export failed: {error}'
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
            status=('Cached' if self.catalog.video else 'Exists') if state else ('Virtual / not cached' if self.catalog.video else 'Missing')
            values=values[:-1]+(('Checking...' if state is None else status),)
        return values

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
                if selected is not None and selected>=0:owner._select_index(selected)
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def select_row(self, event):
        self._select_index(event.GetIndex())

    def _select_index(self, index):
        self._selected_index=index
        if self.view==2:
            entry=self.catalog.visual_entry(index)
            state=self._cache_states.get(entry['path'])
            cache='Checking...' if state is None else ('Cached' if self.catalog.video else 'Exists') if state else ('Virtual / not cached' if self.catalog.video else 'Missing')
            text=f'ID {entry["id"]} | Page {entry["page"]+1} | Row {entry["row"]}, Col {entry["column"]} | {cache}\nOriginal source: {entry["source"]}\nImage / frame path: {entry["path"]}'
        elif self.view==0:
            source=str(Path(self.catalog.paths[index]).absolute()) if self.catalog.video else self.catalog._image(index)[2]
            entry=dict(source=source,path=source if not self.catalog.video else '',page=self.catalog.target(0,index))
            text='\n'.join(self.catalog.row(0,index))
        else:
            entry=dict(source='',path='',page=index)
            text='\n'.join(self.catalog.row(1,index))
        self._selected_entry=entry
        self.path_details.ChangeValue(text)
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
        if self.on_jump and self._selected_entry:self.on_jump(self._selected_entry['page'])
