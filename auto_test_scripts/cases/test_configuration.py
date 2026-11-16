"""Real GUI configuration startup, migration, save/load and reset regressions."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import wx
from mulimgviewer.src.main import MulimgViewer
from mulimgviewer.src.configuration import synchronize, write_config, migrate_config_roles
from mulimgviewer.src.utils import get_resource_path
from mulimgviewer.src.path_select import _PATH_SELECT_STATE


class ConfigurationViewer(MulimgViewer):
    def check_version(self):
        pass

    def _restore_window_state(self):
        pass


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.temp.name)
        self.directory = Path(self.temp.name) / 'configs'
        self.frames = []
        def resources(name):
            return str(self.directory) if str(name) == 'configs' else get_resource_path(name)
        self.patch = patch('mulimgviewer.src.main.get_resource_path', side_effect=resources)
        self.patch.start()
        self.config_patch = patch('mulimgviewer.src.configuration_controller.get_resource_path', side_effect=resources)
        self.config_patch.start()

    def test_old_save_shortcuts_migrate_to_single_escape_pause_action(self):
        from mulimgviewer.src.configuration import read_config
        self.directory.mkdir()
        path=self.directory/'legacy_hotkeys.json'
        write_config(path,{'output':{},'hotkeys':{'pause_save':'F8','cancel_save':'ESC','save_img':'CTRL+S'}})
        value=read_config(path)['hotkeys']
        self.assertNotIn('pause_save',value);self.assertNotIn('cancel_save',value)
        self.assertEqual(value['pause_tasks'],'ESC')
        self.assertEqual(value['save_img'],'CTRL+S')
        frame=self.frame();frame.apply_hotkeys({'pause_save':'F8','cancel_save':'ESC'})
        self.assertEqual(frame.hotkeys['pause_tasks'],'ESC')
        self.assertNotIn('F8',frame.hotkeys.values())

    def test_auto_cache_format_round_trips_without_changing_legacy_choices(self):
        frame=self.frame()
        self.assertEqual(list(frame.cache_save_format.GetItems()),['jpg','png','auto'])
        for value in (0,1,2):
            frame.cache_save_format.SetSelection(value)
            frame.save_configuration(None)
            self.assertEqual(self.read()['output']['cache_save_format'],value)
            frame.cache_save_format.SetSelection((value+1)%3)
            frame.load_configuration(None)
            self.assertEqual(frame.cache_save_format.GetSelection(),value)
        frame._save_session_configuration()
        self.assertEqual(self.frame().cache_save_format.GetSelection(),2)

    def test_save_format_legacy_order_migrates_once_and_new_order_round_trips(self):
        from mulimgviewer.src.configuration import read_config
        self.directory.mkdir()
        for old,current in ((0,1),(1,2),(2,0)):
            for flat in (False,True):
                path=self.directory/f'legacy_{old}_{flat}.json'
                value={'save_format':old} if flat else {'output':{'save_format':old}}
                path.write_text(json.dumps(value),encoding='utf-8')
                migrated=read_config(path)
                self.assertEqual(migrated['output']['save_format'],current)
                write_config(path,migrated)
                self.assertEqual(read_config(path)['output']['save_format'],current)
        for current in (0,1,2):
            path=self.directory/f'new_{current}.json'
            write_config(path,{'output':{'save_format':current}})
            self.assertEqual(read_config(path)['output']['save_format'],current)

    def frame(self):
        frame = ConfigurationViewer(None, lambda *a, **k: None, lambda *a, **k: None)
        frame.Hide()
        self.frames.append(frame)
        return frame

    def tearDown(self):
        for frame in self.frames:
            frame._is_closing = True
            frame.play_timer.Stop()
            frame._cancel_pending_frame_wait()
            frame.image_pipeline.close()
            pipeline = frame.image_pipeline
            for pool in (pipeline.coordinator, pipeline.pool, pipeline.display, *pipeline.retired_pools):
                if pool:
                    pool.shutdown(wait=True)
            frame.resource_monitor.close()
            frame.resource_monitor.thread.join(timeout=2)
            frame.memory_reclaimer.close()
            frame.memory_reclaimer.executor.shutdown(wait=True)
            vm = frame.video_manager
            vm._cache_executor.shutdown(wait=True)
            vm.shutdown()
            for pool in (vm.executor, vm.stitch_executor, vm._maintenance_executor, vm._display_executor):
                pool.shutdown(wait=True)
            pipeline.processing.cleanup_future.result(timeout=5)
            frame.Destroy()
        self.app.Yield(True)
        self.config_patch.stop()
        self.patch.stop()
        os.chdir(self.previous)
        self.temp.cleanup()

    def read(self, name='userdef_config.json'):
        return json.loads((self.directory / name).read_text(encoding='utf-8'))

    def test_first_launch_creates_both_files_from_gui(self):
        frame = self.frame()
        saved, factory = self.read(), self.read('default_config.json')
        self.assertEqual(saved, factory)
        for key in ('video_mode', 'interval', 'skip_frames', 'power_mode', 'cache_frames',
                    'keep_magnifer_size', 'title_position', 'colourPicker_gap'):
            self.assertIn(key, saved['output'])
        self.assertFalse(saved['output']['video_mode'])
        self.assertEqual(saved['output']['interval'], '1.0')
        self.assertNotIn('slider_value', saved['output'])
        self.assertEqual(saved['output']['choice_input_mode'],0)
        self.assertEqual(frame.choice_input_mode.GetStringSelection(),'Sequential')
        self.assertNotIn('custom_algorithm_input', saved['output'])
        self.assertEqual(frame.shared_config.video_mode, frame.video_mode.GetValue())

    def test_video_mode_save_then_restart_restores_ui_runtime_and_path_selection(self):
        frame = self.frame()
        frame.video_mode.SetValue(True)
        frame.on_enable_video_mode(None)
        frame.interval.ChangeValue('0.12')
        frame._interval_user_edited = True
        frame.row_col13.ChangeValue('3')
        frame.save_configuration(None)
        self.assertTrue(self.read()['output']['video_mode'])
        self.assertEqual(self.read()['output']['skip_frames'], '3')
        frame._save_session_configuration()
        restarted = self.frame()
        self.assertTrue(restarted.video_mode.GetValue())
        self.assertTrue(restarted.shared_config.video_mode)
        self.assertTrue(_PATH_SELECT_STATE['video_mode'])
        self.assertEqual(restarted.shared_config.manual_interval, .12)
        self.assertEqual(restarted.shared_config.skip_frames, 3)

    def test_existing_values_preserved_missing_values_added_to_both_files(self):
        write_config(self.directory / 'default_config.json', {
            'output': {'row_col': '4,6', 'power_mode': 4},
            'exif_display': {'Make': False}, 'window_state': {'w': 900}, 'future': {'x': 2}})
        write_config(self.directory / 'userdef_config.json', {'output': {'row_col': '2,2'}})
        frame = self.frame()
        self.assertEqual(frame.row_col.GetValue(), '4,6')
        self.assertEqual(frame.shared_config.power_mode, 4)
        self.assertEqual(self.read()['future'], {'x': 2})
        self.assertEqual(self.read()['exif_display'], {'Make': False})
        for name in ('default_config.json', 'userdef_config.json'):
            self.assertIn('video_mode', self.read(name)['output'])
        self.assertEqual(self.read('default_config.json')['output']['row_col'], '2,2')
        frame.save_configuration(None)
        self.assertEqual(self.read()['window_state'], {'w': 900})

    def test_reset_uses_factory_values_and_persists_them(self):
        frame = self.frame()
        factory = self.read('default_config.json')
        frame.video_mode.SetValue(True)
        frame.on_enable_video_mode(None)
        frame.row_col.ChangeValue('10,10')
        frame.choice_input_mode.SetSelection(2)
        frame.save_configuration(None)
        snapshot = self.read()
        frame.reset_configuration(None)
        self.assertEqual(self.read(), snapshot)
        self.assertEqual(frame.choice_input_mode.GetStringSelection(),'Sequential')
        self.assertEqual(self.read('session_config.json')['output']['choice_input_mode'],0)
        self.assertEqual(self.read('session_config.json'), factory)
        self.assertFalse(frame.video_mode.GetValue())
        self.assertFalse(frame.shared_config.video_mode)
        self.assertFalse(_PATH_SELECT_STATE['video_mode'])
        self.assertEqual(frame.row_col.GetValue(), factory['output']['row_col'])
        restarted = self.frame()
        self.assertFalse(restarted.video_mode.GetValue())
        self.assertEqual(restarted.choice_input_mode.GetSelection(),0)

    def test_load_restores_saved_values_without_saving_current_edits(self):
        frame = self.frame()
        frame.row_col.ChangeValue('4,6')
        frame.save_configuration(None)
        saved = self.read()
        frame.row_col.ChangeValue('10,10')
        frame.load_configuration(None)
        self.assertEqual(frame.row_col.GetValue(), '4,6')
        self.assertEqual(self.read(), saved)

    def test_new_gui_control_is_added_without_replacing_existing_defaults(self):
        frame = self.frame()
        original = self.read('default_config.json')['output']['row_col']
        defaults = dict(frame._gui_config_defaults, new_checkbox=True)
        synchronize(self.directory, defaults, frame.get_default_hotkeys())
        for name in ('default_config.json', 'userdef_config.json'):
            self.assertTrue(self.read(name)['output']['new_checkbox'])
        self.assertEqual(self.read('default_config.json')['output']['row_col'], original)

    def test_legacy_aliases_migrate_and_partial_config_does_not_crash(self):
        write_config(self.directory / 'default_config.json', {'output': {
            'm_checkBox33': True, 'row_col12': '5', 'row_col1': '.2', 'row_col13': '2'}})
        frame = self.frame()
        self.assertTrue(frame.shared_config.video_mode)
        self.assertEqual(frame.shared_config.cache_num, 5)
        self.assertEqual(frame.shared_config.skip_frames, 2)
        self.assertEqual(frame.shared_config.manual_interval, .2)
        self.assertTrue(self.read()['output']['video_mode'])
        frame.save_configuration(None)
        self.assertEqual(self.read()['output']['cache_frames'], '5')

    def test_corrupt_json_preserved_and_recovered_from_gui_defaults(self):
        self.directory.mkdir()
        (self.directory / 'default_config.json').write_text('{broken', encoding='utf-8')
        frame = self.frame()
        backups = list(self.directory.glob('default_config.json.invalid-*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), '{broken')
        self.assertEqual(self.read()['output']['video_mode'], False)
        self.assertEqual(frame.shared_config.power_mode, 2)

    def test_flat_legacy_config_preserves_hotkeys_and_extra_sections(self):
        write_config(self.directory / 'default_config.json', {
            'row_col': '2,3', 'hotkeys': {'next_img': 'CTRL+J'},
            'exif_display': {'Make': False}})
        frame = self.frame()
        self.assertEqual(frame.row_col.GetValue(), '2,3')
        self.assertEqual(frame.hotkeys['next_img'], 'CTRL+J')
        self.assertEqual(self.read()['exif_display'], {'Make': False})

    def test_auto_pacing_does_not_replace_saved_manual_interval(self):
        frame = self.frame()
        frame.video_mode.SetValue(True)
        frame.on_enable_video_mode(None)
        frame.interval.ChangeValue('0.01')
        frame._interval_user_edited = True
        frame._commit_video_settings()
        frame.shared_config.interval_recommend = .3
        frame.shared_config.interval = .3
        frame.interval.ChangeValue('0.3')
        frame.save_configuration(None)
        self.assertEqual(self.read()['output']['interval'], '0.01')

    def test_future_gui_control_is_discovered_and_synced_to_both_configs(self):
        frame = self.frame()
        from mulimgviewer.gui.main_gui import MulimgViewerGui
        initialize = MulimgViewerGui.__init__
        def upgraded(owner, *args, **kwargs):
            initialize(owner, *args, **kwargs)
            owner.future_option = wx.CheckBox(owner.m_panel4, label='Future option')
            owner.future_option.SetValue(True)
        with patch.object(MulimgViewerGui, '__init__', upgraded):
            upgraded_frame = self.frame()
        self.assertTrue(upgraded_frame.future_option.GetValue())
        for name in ('default_config.json', 'userdef_config.json'):
            self.assertTrue(self.read(name)['output']['future_option'])

    def test_legacy_roles_are_swapped_once_and_never_swap_back(self):
        write_config(self.directory / 'default_config.json', {'output': {'row_col': '4,6', 'video_mode': True}})
        write_config(self.directory / 'userdef_config.json', {'output': {'row_col': '2,2', 'video_mode': False}})
        first = self.frame()
        self.assertEqual(first.row_col.GetValue(), '4,6')
        self.assertTrue(first.shared_config.video_mode)
        self.assertEqual(self.read('default_config.json')['output']['row_col'], '2,2')
        saved = self.read()
        restarted = self.frame()
        self.assertEqual(self.read(), saved)
        self.assertTrue(restarted.shared_config.video_mode)
        self.assertFalse((self.directory / '.config_roles_migration.json').exists())

    def test_interrupted_role_migration_resumes_without_losing_either_document(self):
        write_config(self.directory / 'default_config.json', {'output': {'row_col': '4,6'}})
        write_config(self.directory / 'userdef_config.json', {'output': {'row_col': '2,2'}})
        replace = os.replace
        def interrupted(source, destination):
            if Path(destination).name == 'userdef_config.json':
                raise OSError('interrupted migration')
            return replace(source, destination)
        with patch('mulimgviewer.src.configuration.os.replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                migrate_config_roles(self.directory)
        self.assertTrue((self.directory / '.config_roles_migration.json').exists())
        frame = self.frame()
        self.assertEqual(frame.row_col.GetValue(), '4,6')
        self.assertEqual(self.read('default_config.json')['output']['row_col'], '2,2')
        self.assertFalse((self.directory / '.config_roles_migration.json').exists())

    def test_exit_without_manual_save_restores_latest_parameters(self):
        frame = self.frame()
        manual = self.read()
        frame.row_col.ChangeValue('7,8')
        frame.choice_input_mode.SetSelection(2)
        frame.power_mode.SetSelection(3)
        frame.cache_frames.ChangeValue('5')
        frame.video_mode.SetValue(True)
        frame.on_enable_video_mode(None)
        frame.interval.ChangeValue('.02')
        frame._interval_user_edited = True
        frame._save_session_configuration()
        frame._save_window_state()
        self.assertEqual(self.read(), manual)
        restarted = self.frame()
        self.assertEqual(restarted.row_col.GetValue(), '7,8')
        self.assertEqual(restarted.choice_input_mode.GetSelection(),2)
        self.assertEqual(self.read('session_config.json')['output']['choice_input_mode'],2)
        self.assertEqual(restarted.shared_config.power_mode, 4)
        self.assertEqual(restarted.shared_config.cache_num, 5)
        self.assertTrue(restarted.shared_config.video_mode)
        self.assertEqual(restarted.shared_config.manual_interval, .02)
        self.assertIn('window_state', self.read('session_config.json'))

    def test_manual_snapshot_survives_later_edits_exit_restart_and_load(self):
        frame = self.frame()
        frame.row_col.ChangeValue('4,6')
        frame.choice_input_mode.SetSelection(1)
        frame.save_configuration(None)
        manual = self.read()
        frame.row_col.ChangeValue('10,10')
        frame.choice_input_mode.SetSelection(3)
        frame._save_session_configuration()
        restarted = self.frame()
        self.assertEqual(restarted.row_col.GetValue(), '10,10')
        self.assertEqual(restarted.choice_input_mode.GetSelection(),3)
        self.assertEqual(self.read(), manual)
        restarted.load_configuration(None)
        self.assertEqual(restarted.row_col.GetValue(), '4,6')
        self.assertEqual(restarted.choice_input_mode.GetSelection(),1)
        self.assertEqual(self.read(), manual)
        restarted._save_session_configuration()
        self.assertEqual(self.frame().row_col.GetValue(), '4,6')

    def test_close_calls_session_save_without_calling_manual_save(self):
        frame = self.frame()
        with patch.object(frame, '_save_session_configuration') as automatic, \
                patch.object(frame, 'save_configuration') as manual, \
                patch.object(frame, '_save_window_state'), \
                patch.object(frame.video_manager, 'shutdown'), \
                patch.object(frame, '_shutdown_image_stitch_executor'), \
                patch.object(frame, 'Destroy'), patch('wx.Exit'):
            frame.close(None)
        automatic.assert_called_once_with()
        manual.assert_not_called()

    def test_latest_session_new_gui_values_are_also_backfilled(self):
        frame = self.frame()
        defaults = dict(frame._gui_config_defaults, new_option=True)
        synchronize(self.directory, defaults, frame.get_default_hotkeys())
        self.assertTrue(self.read('session_config.json')['output']['new_option'])

    def test_generated_gui_buttons_and_video_checkbox_bind_mixin_handlers(self):
        frame = self.frame()
        def click(control, event_type=wx.EVT_BUTTON):
            event = wx.CommandEvent(event_type.typeId, control.GetId())
            event.SetEventObject(control)
            self.assertTrue(control.GetEventHandler().ProcessEvent(event))
        frame.video_mode.SetValue(True)
        click(frame.video_mode, wx.EVT_CHECKBOX)
        self.assertTrue(frame.shared_config.video_mode)
        frame.row_col.ChangeValue('4,6')
        click(frame.save_config_button)
        self.assertEqual(self.read()['output']['row_col'], '4,6')
        frame.row_col.ChangeValue('10,10')
        click(frame.load_config_button)
        self.assertEqual(frame.row_col.GetValue(), '4,6')
        click(frame.reset_config_button)
        self.assertEqual(frame.row_col.GetValue(), self.read('default_config.json')['output']['row_col'])
        self.assertEqual(self.read()['output']['row_col'], '4,6')
        self.assertFalse(frame.shared_config.video_mode)

    def test_atomic_save_failure_preserves_original_and_removes_temporary(self):
        frame = self.frame()
        path = self.directory / 'userdef_config.json'
        original = path.read_bytes()
        with patch('mulimgviewer.src.configuration.os.replace', side_effect=OSError('blocked')):
            with self.assertRaises(OSError):
                write_config(path, {'output': {'video_mode': True}})
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(list(self.directory.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
