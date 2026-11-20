"""Splitter-local coordinates, stable user widths and DPI-aware restoration."""
import json
import unittest
from unittest.mock import patch
import wx
import test_configuration as fixtures


class SidebarLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.ConfigurationTests.setUpClass()

    def setUp(self):
        self.fixture=fixtures.ConfigurationTests();self.fixture.setUp()
        self.frame=self.fixture.frame()

    def tearDown(self):self.fixture.tearDown()

    def drag(self,width):
        f=self.frame;sp=f.viewer_settings_splitter
        event=wx.SplitterEvent(wx.wxEVT_SPLITTER_SASH_POS_CHANGING,sp)
        event.SetSashPosition(sp.ClientSize.width-sp.GetSashSize()-width)
        f.split_sash_pos_changing(event)
        sp.SetSashPosition(event.GetSashPosition())
        event=wx.SplitterEvent(wx.wxEVT_SPLITTER_SASH_POS_CHANGED,sp)
        event.SetSashPosition(sp.SashPosition);f.split_sash_pos_changed(event)

    def test_save_load_and_reset_restore_sidebar_width(self):
        f=self.frame
        self.drag(340);f.save_configuration(None)
        self.assertEqual(self.fixture.read()['window_state']['sidebar_width_dip'],f.ToDIP(340))
        self.drag(400);f.load_configuration(None)
        self.assertEqual(f.width_setting,340)
        self.assertEqual(f._sidebar_preferred_dip,f.ToDIP(340))
        f.reset_configuration(None)
        self.assertIsNone(f._sidebar_preferred_dip)
        self.assertEqual(f.width_setting,f._automatic_sidebar_width())
        self.assertIsNone(self.fixture.read('default_config.json')['window_state']['sidebar_width_dip'])
        self.assertIsNone(self.fixture.read('session_config.json')['window_state']['sidebar_width_dip'])
        self.assertEqual(self.fixture.read()['window_state']['sidebar_width_dip'],f.ToDIP(340))

    def test_loading_legacy_configuration_clears_previous_width_preference(self):
        f=self.frame
        f.save_configuration(None)
        self.drag(400)
        f.load_configuration(None)
        self.assertIsNone(f._sidebar_preferred_dip)
        self.assertEqual(f.width_setting,f._automatic_sidebar_width())

    def test_hidden_toolbar_explicitly_hides_native_separators_and_restores_them(self):
        f=self.frame
        controls=f.playback_toolbar_panel.GetChildren()
        separators=[f.input_toolbar_separator,f.save_toolbar_separator,f.view_toolbar_separator]
        self.assertTrue(all(control.IsShown() for control in controls))
        for _ in range(2):
            f.hidden(None)
            self.fixture.app.Yield(True)
            self.assertFalse(f.playback_toolbar_panel.IsShown())
            self.assertTrue(all(not control.IsShown() for control in controls))
            self.assertTrue(all(not line.IsShown() for line in separators))
            self.assertFalse(f.viewer_settings_splitter.IsSplit())
            self.assertFalse(f.IsFrozen())
            f.hidden(None)
            self.fixture.app.Yield(True)
            self.assertTrue(f.playback_toolbar_panel.IsShown())
            self.assertTrue(all(control.IsShown() for control in controls))
            self.assertTrue(f.viewer_settings_splitter.IsSplit())

    def test_initial_size_is_usable_and_dragging_has_no_xor_tracker(self):
        f=self.frame;sp=f.viewer_settings_splitter
        self.assertGreaterEqual(f.Size.width,f.FromDIP(600))
        self.assertTrue(sp.GetWindowStyleFlag() & wx.SP_LIVE_UPDATE)
        self.assertEqual(sp.GetSashGravity(),1.)
        self.assertIsNone(f._sidebar_preferred_dip)
        self.assertEqual(f.width_setting,f.scrolledWindow_set.Size.width)
        self.assertEqual(sp.SashPosition+sp.GetSashSize()+f.width_setting,sp.ClientSize.width)

    def test_drag_uses_splitter_client_coordinates_and_never_relayouts_while_tracking(self):
        f=self.frame;sp=f.viewer_settings_splitter
        self.assertNotEqual(f.Size.width,sp.ClientSize.width)
        event=wx.SplitterEvent(wx.wxEVT_SPLITTER_SASH_POS_CHANGING,sp)
        event.SetSashPosition(sp.ClientSize.width-sp.GetSashSize()-350)
        with patch.object(f,'init_min_size') as minimum,patch.object(f,'Layout') as layout:
            f.split_sash_pos_changing(event)
            minimum.assert_not_called();layout.assert_not_called()
        sp.SetSashPosition(event.GetSashPosition())
        event=wx.SplitterEvent(wx.wxEVT_SPLITTER_SASH_POS_CHANGED,sp)
        event.SetSashPosition(sp.SashPosition);f.split_sash_pos_changed(event)
        self.assertEqual(f.scrolledWindow_set.Size.width,350)
        self.assertEqual(f._sidebar_preferred_dip,f.ToDIP(350))

    def test_resize_clamps_temporarily_and_restores_the_users_preference(self):
        f=self.frame;self.drag(420)
        preferred=f._sidebar_preferred_dip
        for size in ((1400,800),(500,500),(1300,800)):
            f.SetSize(size);f.auto_layout(frame_resize=True)
            available,minimum,maximum=f._sidebar_bounds()
            self.assertEqual(f.width_setting,min(maximum,max(minimum,f.FromDIP(preferred))))
            self.assertEqual(f._sidebar_preferred_dip,preferred)
            self.assertGreaterEqual(f.scrolledWindow_img.Size.width,f.FromDIP(120))
        self.assertEqual(f.width_setting,420)

    def test_proposed_drag_positions_are_clamped_to_usable_panes(self):
        f=self.frame;sp=f.viewer_settings_splitter
        available,minimum,maximum=f._sidebar_bounds()
        for position in (-10000,100000):
            event=wx.SplitterEvent(wx.wxEVT_SPLITTER_SASH_POS_CHANGING,sp)
            event.SetSashPosition(position);f.split_sash_pos_changing(event)
            self.assertGreaterEqual(event.GetSashPosition(),available-maximum)
            self.assertLessEqual(event.GetSashPosition(),available-minimum)
        f.split_changing=False

    def test_hidden_sidebar_does_not_leave_a_blank_strip_or_lose_width(self):
        f=self.frame;self.drag(330)
        f.layout_settings_pane.Collapse(True)
        f.hidden(None)
        self.assertFalse(f.viewer_settings_splitter.IsSplit())
        self.assertFalse(f.scrolledWindow_set.IsShown())
        self.assertEqual(f.scrolledWindow_img.Size.width,f.viewer_settings_splitter.ClientSize.width)
        self.assertEqual(f.width_setting,0)
        f.SetSize((1300,800));f.auto_layout(frame_resize=True)
        f.hidden(None)
        self.assertTrue(f.viewer_settings_splitter.IsSplit())
        self.assertEqual(f.width_setting,330)
        self.assertTrue(f.layout_settings_pane.IsCollapsed())

    def test_session_restores_user_width_even_if_saved_while_hidden(self):
        f=self.frame;self.drag(340);f.hidden(None)
        f._save_session_configuration();f._save_window_state()
        data=json.loads(f.output_config_path.read_text(encoding='utf-8'))
        self.assertEqual(data['window_state']['sidebar_width_dip'],f.ToDIP(340))
        other=self.fixture.frame()
        self.assertEqual(other._sidebar_preferred_dip,f.ToDIP(340))
        self.assertEqual(other.width_setting,340)
        self.assertTrue(other.viewer_settings_splitter.IsSplit())

    def test_double_click_resets_to_auto_without_unsplitting_and_persists_reset(self):
        f=self.frame;self.drag(360);f._save_session_configuration()
        event=wx.SplitterEvent(wx.wxEVT_SPLITTER_DOUBLECLICKED,f.viewer_settings_splitter)
        f._sidebar_reset_width(event)
        self.assertIsNone(f._sidebar_preferred_dip)
        self.assertTrue(f.viewer_settings_splitter.IsSplit())
        self.assertEqual(f.width_setting,f._automatic_sidebar_width())
        f._save_session_configuration()
        data=json.loads(f.output_config_path.read_text(encoding='utf-8'))
        self.assertIsNone(data.get('window_state',{}).get('sidebar_width_dip'))

    def test_stored_width_is_converted_to_current_dpi(self):
        f=self.frame;f.SetSize((1500,800));f.auto_layout(frame_resize=True)
        f._sidebar_preferred_dip=300
        with patch.object(f,'FromDIP',side_effect=lambda value:value*2):f._apply_sidebar_width()
        self.assertEqual(f.width_setting,600)
        self.assertEqual(f._sidebar_preferred_dip,300)

    def test_programmatic_resize_does_not_become_a_user_preference(self):
        f=self.frame
        for width in (1100,1300,950):
            f.SetSize((width,700));f.auto_layout(frame_resize=True)
            self.fixture.app.Yield(True)
            self.assertIsNone(f._sidebar_preferred_dip)
            self.assertFalse(f.split_changing)


if __name__=='__main__':unittest.main()
