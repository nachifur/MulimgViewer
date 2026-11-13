"""Four-field status bar: action, selection, input/source, output path."""
import wx
from .status_info import selection_info, status_widths


class StatusBarMixin:
    def _init_status_bar(self):
        self._status_selected_grid = 0
        self._status_field_tooltips = [''] * 4
        style = self.m_statusBar1.GetWindowStyleFlag() & ~(wx.STB_ELLIPSIZE_START | wx.STB_ELLIPSIZE_END)
        self.m_statusBar1.SetWindowStyleFlag(style | wx.STB_ELLIPSIZE_MIDDLE)
        self.m_statusBar1.Bind(wx.EVT_SIZE, self._on_status_bar_size)
        self.m_statusBar1.Bind(wx.EVT_MOTION, self._on_status_bar_hover)
        self.m_statusBar1.SetStatusText('Output: not set', 3)
        self._fit_status_fields()

    def _fit_status_fields(self):
        bar = self.m_statusBar1
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
        bar = self.m_statusBar1
        for field in range(4):
            if bar.GetFieldRect(field).Contains(event.GetPosition()):
                tip = (self._status_field_tooltips[field] if field in (1, 2) else '') or bar.GetStatusText(field)
                current = bar.GetToolTip()
                if not current or current.GetTip() != tip:
                    bar.SetToolTip(tip)
                break
        event.Skip()

    def SetStatusText_(self, texts):
        for field, text in enumerate(texts[:self.Status_number]):
            if text != '-1':
                self.m_statusBar1.SetStatusText(str(text), field)
                if hasattr(self, '_status_field_tooltips'):
                    self._status_field_tooltips[field] = str(text)
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
        inputs = ('Sequential', 'Parallel auto', 'Parallel manual', 'Image File List')
        if self.shared_config.video_mode:
            choice = getattr(self.ImgManager, '_status_input_mode', self.choice_input_mode.GetSelection())
        else:
            choice = {2: 0, 0: 1, 1: 2, 3: 3}.get(self.ImgManager.type, -1)
        input_mode = inputs[choice] if 0 <= choice < len(inputs) else 'Input'
        position = info['position'] if info else 'No source selected'
        self.SetStatusText_([f'{mode} | {playback}', f'Page {batch+1}/{pages} | {position}',
                             f'{input_mode} | {info["source"]}' if info else input_mode, '-1'])
        if info:
            if info['timestamp']:
                self.m_statusBar1.SetStatusText(f'{input_mode} | {info["source"]} | {info["timestamp"]}', 2)
            self._status_field_tooltips[1] = f'Page {batch+1}/{pages}\n{position}\n{info["detail"]}'
            self._status_field_tooltips[2] = f'{input_mode}\n{info["source"]}\n{info["detail"]}'
        self._fit_status_fields()
