"""About and manual-source windows: layout, editing, apply/cancel and mode safety."""
import copy
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import wx
from mulimgviewer.src.about import About
from mulimgviewer.src.path_select import PathSelectFrame, _PATH_SELECT_STATE, on_video_mode_change
from mulimgviewer.gui.virtual_index_list import VirtualIndexList


class AuxiliaryWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.state = copy.deepcopy(_PATH_SELECT_STATE)
        _PATH_SELECT_STATE.update(video_mode=False, last_manual_paths=[])
        self.windows = []
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        for window in self.windows:
            if not window.IsBeingDeleted():
                window.Destroy()
        self.app.Yield(True)
        _PATH_SELECT_STATE.clear()
        _PATH_SELECT_STATE.update(self.state)
        self.temporary.cleanup()

    def selector(self, **kwargs):
        callback = Mock()
        frame = PathSelectFrame(None, callback, lambda: 1, **kwargs)
        self.windows.append(frame)
        return frame, callback

    def folder(self, name):
        path = self.root / name
        path.mkdir()
        return str(path)

    def test_about_shows_actual_runtime_and_read_only_copyable_details(self):
        frame = About(None, 'test-version')
        self.windows.append(frame)
        text = frame.about_txt.GetValue()
        for value in ('test-version', platform.python_version(), platform.system(), wx.VERSION_STRING):
            self.assertIn(value, text)
        self.assertFalse(frame.about_txt.IsEditable())
        self.assertEqual(frame.project_link.GetURL(), 'https://github.com/nachifur/MulimgViewer')
        frame.about_txt.SetSelection(0, 7)
        self.assertTrue(frame.about_txt.GetStringSelection())

    def test_about_description_and_formats_use_the_same_labeled_format(self):
        frame = About(None, 'test')
        self.windows.append(frame)
        text = frame.about_txt.GetValue()
        for label in ('Description', 'Image formats', 'Video decoding'):
            self.assertIn(label + ': ', text)
            style = wx.richtext.RichTextAttr()
            self.assertTrue(frame.about_txt.GetStyle(text.index(label + ': '), style))
            self.assertEqual(style.GetFontWeight(), wx.FONTWEIGHT_BOLD)
        self.assertNotIn('\n\nCompare', text)

    def test_selector_uses_one_hint_for_mode_and_validation_without_a_menu(self):
        frame, callback = self.selector()
        self.assertIsNone(frame.GetMenuBar())
        self.assertIn('Esc', frame.cancel_button.GetToolTip().GetTip())
        self.assertIn('Ctrl+Enter', frame.apply_button.GetToolTip().GetTip())
        for name in ('source_heading', 'selection_feedback', 'selection_menu_bar'):
            self.assertFalse(hasattr(frame, name))
        self.assertIn('folder per line', frame.source_hint.GetLabel())
        frame.refresh_txt([str(self.root / 'missing')])
        self.assertFalse(frame._finalize_and_return())
        self.assertIn('existing image folder', frame.source_hint.GetLabel())
        frame.refresh_txt([])
        self.assertIn('folder per line', frame.source_hint.GetLabel())
        on_video_mode_change(True)
        frame.set_video_manager(Mock(), SimpleNamespace(video_mode=True))
        self.assertIn('video per line', frame.source_hint.GetLabel())
        # An accelerator must not apply or close an empty list.
        event = wx.CommandEvent(wx.wxEVT_MENU, frame.apply_button.GetId())
        event.SetEventObject(frame)
        frame.GetEventHandler().ProcessEvent(event)
        callback.assert_not_called()

    def test_about_title_style_and_compact_size_follow_fbp(self):
        frame = About(None, 'test')
        self.windows.append(frame)
        self.assertFalse(hasattr(frame, 'product_subtitle'))
        self.assertEqual(frame.product_title.GetFont().GetPointSize(), 14)
        self.assertEqual(frame.product_title.GetFont().GetWeight(), wx.FONTWEIGHT_BOLD)
        self.assertEqual(frame.Size.height, 380)
        self.assertEqual(frame.GetMinSize().height, 280)

    def test_about_update_highlights_release_without_a_red_background(self):
        frame = About(None, '1.0', update=True, new_version='2.0')
        self.windows.append(frame)
        self.assertIn('New version available: 2.0', frame.about_txt.GetValue())
        self.assertEqual(frame.releases_link.GetLabel(), 'Get new version')
        self.assertNotEqual(frame.releases_link.GetBackgroundColour(), wx.Colour(255, 0, 0))

    def test_about_details_grow_and_footer_remains_visible(self):
        frame = About(None, 'test')
        self.windows.append(frame)
        heights = []
        for size in ((440, 340), (700, 560), (480, 360)):
            frame.SetClientSize(size);frame.Layout()
            heights.append(frame.about_txt.Size.height)
            self.assertLessEqual(frame.close_button.Position.y + frame.close_button.Size.height, frame.ClientSize.height)
            self.assertLessEqual(frame.about_txt.Position.x + frame.about_txt.Size.width, frame.ClientSize.width)
        self.assertGreater(heights[1], heights[0])
        self.assertLess(heights[2], heights[1])

    def test_selector_editor_grows_and_shrinks_without_covering_footer(self):
        frame, _ = self.selector()
        heights = []
        for size in ((460, 340), (760, 600), (500, 360)):
            frame.SetClientSize(size);frame.Layout()
            heights.append(frame.paths_text.Size.height)
            self.assertLessEqual(frame.apply_button.Position.y + frame.apply_button.Size.height, frame.ClientSize.height)
            self.assertLessEqual(frame.paths_text.Position.x + frame.paths_text.Size.width, frame.ClientSize.width)
        self.assertGreater(heights[1], heights[0])
        self.assertLess(heights[2], heights[1])

    def test_empty_list_disables_destructive_actions_and_shows_count(self):
        frame, _ = self.selector()
        self.assertEqual(frame.source_count.GetLabel(), '0 sources')
        self.assertFalse(frame.apply_button.IsEnabled())
        self.assertFalse(frame.button_clear_all.IsEnabled())
        frame.refresh_txt([self.folder('a')])
        self.assertEqual(frame.source_count.GetLabel(), '1 source')
        self.assertTrue(frame.apply_button.IsEnabled())
        frame.clear_last_path(None)
        self.assertEqual(frame.source_count.GetLabel(), '0 sources')

    def test_pasted_paths_keep_order_trim_quotes_and_preserve_duplicates(self):
        frame, callback = self.selector()
        first, second = self.folder('first'), self.folder('second')
        frame.paths_text.SetValue(f'  "{second}"  \n\n{first}\n{second}\n')
        self.assertEqual(frame._paths(), [second, first, second])
        self.assertTrue(frame._finalize_and_return())
        callback.assert_called_once_with(0, input_path=[second, first, second])
        self.assertEqual(_PATH_SELECT_STATE['last_manual_paths'], [second, first, second])

    def test_browse_appends_and_cancel_does_not_apply_or_change_last_selection(self):
        original = self.folder('original')
        added = self.folder('added')
        _PATH_SELECT_STATE['last_manual_paths'] = [original]
        frame, callback = self.selector()
        with patch.object(wx, 'DirDialog') as dialog:
            dialog.return_value.ShowModal.return_value = wx.ID_OK
            dialog.return_value.GetPath.return_value = added
            event = wx.CommandEvent(wx.wxEVT_BUTTON, frame.browse_button.GetId())
            event.SetEventObject(frame.browse_button)
            frame.browse_button.GetEventHandler().ProcessEvent(event)
            dialog.return_value.Destroy.assert_called_once()
        self.assertEqual(frame._paths(), [original, added])
        self.assertEqual(_PATH_SELECT_STATE['last_manual_paths'], [original])
        frame.on_cancel(None)
        callback.assert_called_once_with(0)
        self.assertEqual(_PATH_SELECT_STATE['last_manual_paths'], [original])

    def test_video_browse_supports_all_decoder_extensions_and_remembers_folder(self):
        on_video_mode_change(True)
        frame, _ = self.selector()
        paths = [str(self.root / 'one.webm'), str(self.root / 'two.rmvb')]
        with patch.object(wx, 'FileDialog') as dialog:
            dialog.return_value.ShowModal.return_value = wx.ID_OK
            dialog.return_value.GetPaths.return_value = paths
            frame.on_browse(None)
            self.assertIn('*.webm', dialog.call_args.kwargs['wildcard'])
            self.assertIn('*.rmvb', dialog.call_args.kwargs['wildcard'])
            dialog.return_value.Destroy.assert_called_once()
        self.assertEqual(frame._paths(), paths)
        self.assertEqual(frame._last_video_dir, str(self.root))
        self.assertEqual(frame.GetTitle(), 'Parallel video sources')

    def test_invalid_image_folder_is_explained_and_does_not_replace_input(self):
        frame, callback = self.selector()
        frame.refresh_txt([str(self.root / 'missing')])
        self.assertFalse(frame._finalize_and_return())
        callback.assert_not_called()
        self.assertIn('existing image folder', frame.source_hint.GetLabel())
        self.assertFalse(frame.IsBeingDeleted())

    def test_video_apply_waits_for_manager_and_keeps_rejected_selection_editable(self):
        on_video_mode_change(True)
        frame, callback = self.selector()
        frame.refresh_txt(['clip.mp4'])
        self.assertFalse(frame._finalize_and_return())
        manager = Mock();manager.select_video.return_value = []
        frame.set_video_manager(manager, SimpleNamespace(video_mode=True))
        self.assertFalse(frame._finalize_and_return())
        self.assertEqual(frame._paths(), ['clip.mp4'])
        callback.assert_not_called()
        manager.select_video.assert_called_once_with(type=-1, paths=['clip.mp4'])
        self.assertFalse(frame.IsBeingDeleted())

    def test_existing_repeated_video_sources_remain_separate_sources(self):
        on_video_mode_change(True)
        frame, _ = self.selector()
        paths = ['clip.mp4', 'clip.mp4']
        manager = Mock();manager.select_video.return_value = paths
        frame.set_video_manager(manager, SimpleNamespace(video_mode=True, real_video_path=paths))
        self.assertEqual(frame._paths(), paths)
        self.assertEqual(frame.source_count.GetLabel(), '2 sources')
        self.assertTrue(frame._finalize_and_return())
        manager.select_video.assert_called_once_with(type=-1, paths=paths)

    def test_clear_shortcuts_preserve_standard_text_selection_and_undo(self):
        frame, _ = self.selector()
        self.assertIsNone(frame.GetMenuBar())
        keys = [(flags, key) for flags, key, _ in frame._selection_accelerators]
        self.assertNotIn((wx.ACCEL_CTRL, ord('A')), keys)
        self.assertNotIn((wx.ACCEL_CTRL, ord('Z')), keys)
        self.assertIn((wx.ACCEL_NORMAL, wx.WXK_ESCAPE), keys)
        event = wx.CommandEvent(wx.wxEVT_MENU, frame.cancel_button.GetId())
        event.SetEventObject(frame)
        frame.GetEventHandler().ProcessEvent(event)

    def test_apply_and_cancel_buttons_are_connected_in_fbp(self):
        for button_name in ('apply_button', 'cancel_button'):
            with self.subTest(button=button_name):
                frame, callback = self.selector()
                folder = self.folder(button_name)
                frame.refresh_txt([folder])
                button = getattr(frame, button_name)
                event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
                event.SetEventObject(button)
                button.GetEventHandler().ProcessEvent(event)
                if button_name == 'apply_button':
                    callback.assert_called_once_with(0, input_path=[folder])
                else:
                    callback.assert_called_once_with(0)

    def test_force_close_does_not_get_stuck_on_invalid_paths(self):
        frame, callback = self.selector()
        frame.refresh_txt([str(self.root / 'missing')])
        with patch.object(frame, 'Destroy', wraps=frame.Destroy) as destroy:
            frame.Close(force=True)
            destroy.assert_called_once()
        callback.assert_not_called()

    def test_native_close_still_applies_existing_manual_workflow(self):
        frame, callback = self.selector()
        folder = self.folder('close')
        frame.refresh_txt([folder])
        frame.Close()
        callback.assert_called_once_with(0, input_path=[folder])

    def test_virtual_index_list_fetches_only_requested_row(self):
        frame = wx.Frame(None)
        self.windows.append(frame)
        control = VirtualIndexList(frame, style=wx.LC_REPORT | wx.LC_VIRTUAL)
        control.get_row = Mock(return_value=('source', 'frame'))
        self.assertEqual(control.OnGetItemText(123, 1), 'frame')
        control.get_row.assert_called_once_with(123)
        self.assertEqual(control.OnGetItemText(123, 9), '')


if __name__ == '__main__':
    unittest.main()
