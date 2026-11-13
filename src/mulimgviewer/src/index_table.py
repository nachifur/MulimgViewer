"""Searchable, exportable source/page index without decoding or scanning videos."""
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import wx
from ..gui.index_table_gui import IndexTableGui
from .index_catalog import IndexCatalog
from .index_columns import view_columns, view_row, export_filename
from .index_excel import write_index_xlsx


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
        self.Show(show)
        if auto_export and out_path_str:
            self._export(Path(out_path_str)/export_filename(0,catalog.video),view=0)

    def change_view(self, event):
        self._search_cancel.set()
        self._revision += 1
        self.id_list, self.id = [], 0
        caption = self.view_choice.GetStringSelection()
        self.view = {'Sources': 0, 'Pages': 1, 'Visual items': 2}.get(caption,0)
        self.index_table.SetItemCount(0)
        self.index_table.DeleteAllColumns()
        for number,column in enumerate(view_columns(self.view,self.catalog.video)):
            self.index_table.InsertColumn(number,column.label,width=column.width)
        self.index_table.get_row = self._display_row
        self.index_table.SetItemCount(self.catalog.rows(self.view))
        self.index_table.Refresh()
        mode = 'Video' if self.catalog.video else 'Image'
        self.summary.SetLabel(f'{mode} | {self.catalog.input_mode} | {self.catalog.pages} pages | '
                              f'{self.catalog.sources} source entries | {self.catalog.visual_total} visual items')
        self.match_label.SetLabel('Double-click a row to go to its page; counters start at 1')
        self._selected_entry = None
        self._selected_index = None
        self.path_details.ChangeValue('')
        self.copy_frame_button.Disable(); self.copy_source_button.Disable(); self.jump_button.Disable()
        self._update_buttons()

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
        self._jump_row(event.GetIndex())

    def refresh_index(self, event):
        if self.refresh_model:
            self.catalog = self.refresh_model()
        self.change_view(None)

    def export_index(self, event):
        with wx.FileDialog(self, 'Export index', defaultDir=self.out_path_str,
                           defaultFile=export_filename(self.view,self.catalog.video), wildcard='Excel workbook (*.xlsx)|*.xlsx',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self._export(Path(dialog.GetPath()))

    def _export(self, path, view=None):
        model, view, stop = self.catalog, self.view if view is None else view, self._stop
        self.export_button.Disable()
        self.match_label.SetLabel('Exporting index...')
        if Path(path).suffix.lower() != '.xlsx':
            self.export_button.Enable()
            self.match_label.SetLabel('Use the .xlsx extension for Excel export')
            return
        states = dict(self._cache_states)
        def write():
            return write_index_xlsx(path,model,view,stop.is_set,states)
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
                self.match_label.SetLabel('Main layout/input changed. Refresh the index before jumping.')
        elif self.on_jump:
            self.on_jump(page)

    def locate_main_image(self,event):
        if not self.on_locate:
            return
        # Refresh a potentially stale snapshot, then use the displayed main page.
        self.refresh_index(None)
        location = self.on_locate()
        if not self.catalog.pages or not self.catalog.visual_total:
            self.match_label.SetLabel('No displayed image to locate')
            return
        page = max(0,min(int(location['page']),self.catalog.pages-1))
        first,last = self.catalog.visual_page_start(page), self.catalog.visual_page_start(page+1)
        if first == last:
            self.match_label.SetLabel('No visible image on this page')
            return
        rank = int(location.get('rank',0))
        index = first+rank if 0 <= rank < last-first else first
        self._choose_view(2)
        self.change_view(None)
        self.index_table.Select(index)
        self.index_table.Focus(index)
        self.index_table.EnsureVisible(index)
        self._select_index(index)
        self.match_label.SetLabel(f'Located Visual ID {index+1} on page {page+1}')

    def _choose_view(self, view):
        """Resolve semantic view IDs independently of the FBP choice order."""
        caption = ('Sources', 'Pages', 'Visual items')[view]
        index = self.view_choice.FindString(caption)
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
        if isinstance(panel, wx.ScrolledWindow) and panel.GetSizer() is not None:
            if not hasattr(panel, '_fbp_min_height'):
                panel._fbp_min_height = panel.GetMinSize().height
            row = panel.GetSizer().GetMinSize()
            needs_scroll = row.width > panel.GetClientSize().width
            scrollbar = max(0, wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y, panel)) if needs_scroll else 0
            required = max(panel._fbp_min_height, row.height + scrollbar)
            if panel.GetMinSize().height != required:
                panel.SetMinSize((panel.GetMinSize().width, required))
                self.Layout()
            panel.FitInside()
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
