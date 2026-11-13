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

    def _seek_display_page(self, value):
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
        self.ImgManager.set_action_count(batch)
        if self.shared_config.video_mode:
            wx.CallAfter(self.video_manager.update_cache)
        self.show_img(preserve_text_value=True)

    def skip_to_n_img(self, event):
        self._seek_display_page(self.slider_img.GetValue())

    def slider_value_change(self, event, value=None):
        self._seek_display_page(self.slider_value.GetValue() if value is None else value)
