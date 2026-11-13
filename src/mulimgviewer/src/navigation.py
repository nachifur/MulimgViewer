"""One-based navigation controls over zero-based internal page/cache IDs."""
import wx
from .video_timeline import page_count


class NavigationMixin:
    def _navigation_total(self):
        manager, cfg = self.ImgManager, self.shared_config
        count = max(1, int(manager.count_per_action))
        if cfg.video_mode:
            total = page_count(cfg.video_num_list, count, cfg.parallel_to_sequential)
        else:
            total = (int(manager.img_num) + count - 1) // count
        manager.max_action_num = max(1, total)
        return manager.max_action_num

    def _seek_display_page(self, value, selection=None):
        if not self.ImgManager.img_num:
            return
        total = self._navigation_total()
        try:
            page = max(1, min(total, int(str(value).strip())))
        except (ValueError, TypeError):
            page = max(1, min(total, self.shared_config.batch_idx + 1))
        batch = page - 1
        self.slider_value.ChangeValue(str(page))
        self.slider_img.SetRange(1, total)
        self.slider_img.SetValue(page)
        self.slider_value_max.SetLabel(str(total))
        self.shared_config.batch_idx = batch
        self._pending_index_selection = selection
        self.ImgManager.set_action_count(batch)
        if self.shared_config.video_mode:
            wx.CallAfter(self.video_manager.update_cache)
        self.show_img(preserve_text_value=True)

    def skip_to_n_img(self, event):
        self._seek_display_page(self.slider_img.GetValue())

    def slider_value_change(self, event, value=None):
        self._seek_display_page(self.slider_value.GetValue() if value is None else value)

    def _index_context(self):
        """Identify input/layout, excluding the page and transient cache contents."""
        manager, cfg = self.ImgManager, self.shared_config
        layout = getattr(manager, 'layout_params', [])
        geometry = tuple(tuple(layout[i]) for i in (0, 1)) if len(layout) > 1 else ()
        directions = tuple(bool(layout[i]) for i in (24, 25)) if len(layout) > 25 else ()
        return (bool(cfg.video_mode), getattr(manager, 'type', None),
                id(getattr(manager, 'path_list', None)), id(getattr(manager, 'name_list', None)),
                int(getattr(manager, 'count_per_action', 1)), geometry, directions,
                bool(cfg.parallel_to_sequential), bool(cfg.parallel_sequential))

    def _display_grid_order(self):
        """Use painted coordinates rather than assuming grid IDs are row-major."""
        manager = self.ImgManager
        coordinates = getattr(manager, 'xy_grid', [])
        mapping = getattr(manager, 'xy_grids_id_list', [])
        variants = getattr(manager, '_status_source_slots', None)
        paths = getattr(manager, 'flist', [])
        valid = []
        for grid, slot in enumerate(mapping):
            if grid >= len(coordinates):
                break
            if variants is not None:
                slot = variants[slot] if 0 <= slot < len(variants) else -1
            if 0 <= slot < len(paths):
                valid.append(grid)
        return sorted(valid, key=lambda grid: (coordinates[grid][1], coordinates[grid][0]))

    def _remember_main_selection(self, grid):
        self.selected_img_id = grid
        self._status_selected_grid = grid
        self._index_selection_record = dict(page=getattr(self, '_status_display_batch', None),
                                           grid=grid, context=self._index_context())

    def _index_location(self):
        page = getattr(self, '_status_display_batch', self.shared_config.batch_idx)
        context = self._index_context()
        record = getattr(self, '_index_selection_record', None)
        order = self._display_grid_order()
        rank = 0
        if (record and record['page'] == page and record['context'] == context
                and record['grid'] in order):
            rank = order.index(record['grid'])
        return dict(page=page, rank=rank, context=context)

    def _jump_to_index_item(self, page, rank=0, context=None):
        current = self._index_context()
        if context is not None and context != current:
            return False
        pending = dict(page=page, rank=rank, context=current)
        self._seek_display_page(page+1, selection=pending)
        # Same-page jumps may reuse an already-painted bitmap with no callback.
        if self._apply_pending_index_selection():
            self.update_status_bar_for_current_page()
        return True

    def _apply_pending_index_selection(self):
        """Select only after the requested pixels, grid and source state exist."""
        pending = getattr(self, '_pending_index_selection', None)
        if not pending:
            return False
        if (pending['page'] != int(self.shared_config.batch_idx)
                or pending['context'] != self._index_context()):
            self._pending_index_selection = None
            return False
        if pending['page'] != getattr(self, '_status_display_batch', None):
            return False
        order = self._display_grid_order()
        if not order:
            return False
        rank = pending['rank'] if 0 <= pending['rank'] < len(order) else 0
        self._remember_main_selection(order[rank])
        self._pending_index_selection = None
        return True
