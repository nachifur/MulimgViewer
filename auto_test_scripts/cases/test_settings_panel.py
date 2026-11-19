"""Foldable settings, persistence, and export compression contracts."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
import wx
from mulimgviewer.src.settings_section import SettingsSection
from PIL import Image
import test_configuration as configuration_fixtures
import test_export_modes as export_fixtures
from mulimgviewer.src.export_controller import export_page


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):configuration_fixtures.ConfigurationTests.setUpClass()

    def setUp(self):
        self.fixture=configuration_fixtures.ConfigurationTests();self.fixture.setUp()
        self.frame=self.fixture.frame()

    def tearDown(self):self.fixture.tearDown()

    def test_section_states_survive_session_restart(self):
        f=self.frame
        expected={name:index%2==0 for index,name in enumerate(f._settings_sections())}
        for name,section in f._settings_sections().items():section.Collapse(expected[name])
        f._save_session_configuration()
        restored=self.fixture.frame()
        self.assertEqual(restored._capture_settings_sections(),expected)
        self.assertEqual(self.fixture.read('session_config.json')['settings_sections'],expected)

    def test_section_states_save_load_and_reset_are_independent(self):
        f=self.frame
        defaults=f._gui_section_defaults.copy()
        f.input_settings_pane.Collapse(True);f.save_settings_pane.Collapse(True)
        saved=f._capture_settings_sections()
        f.save_configuration(None)
        f.reset_configuration(None)
        self.assertEqual(f._capture_settings_sections(),defaults)
        self.assertEqual(self.fixture.read('default_config.json')['settings_sections'],defaults)
        self.assertEqual(self.fixture.read('session_config.json')['settings_sections'],defaults)
        self.assertEqual(self.fixture.read()['settings_sections'],saved)
        f.load_configuration(None)
        self.assertEqual(f._capture_settings_sections(),saved)

    def test_missing_and_invalid_section_states_fall_back_to_gui_defaults(self):
        f=self.frame
        f.input_settings_pane.Collapse(True)
        f._restore_settings_sections({'input_settings_pane':'false','save_settings_pane':True})
        self.assertFalse(f.input_settings_pane.IsCollapsed())
        self.assertTrue(f.save_settings_pane.IsCollapsed())
        f._restore_settings_sections(None)
        self.assertEqual(f._capture_settings_sections(),f._gui_section_defaults)

    def test_all_settings_are_inside_fbp_fold_sections(self):
        frame=self.frame
        panes=[child for child in frame.scrolledWindow_set.GetChildren() if isinstance(child,(SettingsSection,wx.CollapsiblePane))]
        self.assertEqual(len(panes),9)
        for name in ('output_directory','out_path_button','save_format','save_quality','choice_output',
                     'auto_save_all','move_file','output_scale','magnifier_out_scale','png_compression','pdf_compression'):
            self.assertTrue(frame.save_settings_pane.GetPane().IsDescendant(getattr(frame,name)),name)
        for name in ('cache_jpg_quality','cache_quality_follow_save','cache_save_format','power_mode'):
            self.assertTrue(frame.performance_settings_pane.GetPane().IsDescendant(getattr(frame,name)),name)
        self.assertEqual(frame.out_path_button.GetLabel(),'Browse...')

    def test_collapse_reflows_only_settings_without_applying_parameters(self):
        frame=self.frame;frame._layout_settings_sections()
        size=tuple(frame.Size);before=frame.scrolledWindow_set.VirtualSize.height
        with patch.object(frame,'refresh') as refresh,patch.object(frame,'show_img_init') as apply:
            frame.layout_settings_pane.Collapse(True);frame._layout_settings_sections()
            self.assertLess(frame.scrolledWindow_set.VirtualSize.height,before)
            self.assertEqual(tuple(frame.Size),size)
            frame.layout_settings_pane.Expand();frame._layout_settings_sections()
            self.assertEqual(frame.scrolledWindow_set.VirtualSize.height,before)
            refresh.assert_not_called();apply.assert_not_called()

    def test_common_sections_are_first_and_fields_fit_sidebar_widths(self):
        f=self.frame
        panes=[child for child in f.scrolledWindow_set.GetChildren() if isinstance(child,(SettingsSection,wx.CollapsiblePane))]
        self.assertEqual(panes,[f.input_settings_pane,f.performance_settings_pane,f.layout_settings_pane,
            f.custom_settings_pane,f.magnifier_settings_pane,f.title_settings_pane,
            f.save_settings_pane,f.colour_settings_pane,f.configuration_settings_pane])
        for width in (280,320,420):
            with self.subTest(sidebar_width=width):
                f.scrolledWindow_set.SetSize((width,700));f._layout_settings_sections()
                for pane in panes:
                    body=pane.GetPane()
                    for widget in body.GetChildren():
                        if not widget.IsShown():continue
                        rect=widget.GetRect()
                        self.assertGreaterEqual(rect.x,0)
                        self.assertLessEqual(rect.x+rect.width,body.ClientSize.width,(pane.GetLabel(),widget.GetName()))
                        if isinstance(widget,wx.StaticText):
                            self.assertGreaterEqual(rect.width,widget.GetTextExtent(widget.GetLabel()).width)
                for before,after in zip(panes,panes[1:]):
                    self.assertLessEqual(before.Position.y+before.Size.height,after.Position.y)
        self.assertEqual(f.gap.GetParent(),f.layout_settings_pane.GetPane())
        self.assertGreater(f.gap.Size.width,220)

    def test_removed_wrapper_panel_supports_startup_configuration_and_hide_restore(self):
        from mulimgviewer.src.configuration import settings_controls
        f=self.frame
        self.assertFalse(hasattr(f,'m_panel4'))
        controls=settings_controls(f)
        for name in ('power_mode','cache_jpg_quality','output_directory','row_col','title_auto','choice_input_mode'):
            self.assertIn(name,controls)
        self.assertNotIn('slider_value',controls)
        panes=[c for c in f.scrolledWindow_set.GetChildren() if isinstance(c,(SettingsSection,wx.CollapsiblePane))]
        f.layout_settings_pane.Collapse(True);f._layout_settings_sections()
        f.hidden(None)
        self.assertTrue(all(not pane.IsShown() for pane in panes))
        f.hidden(None)
        self.assertTrue(all(pane.IsShown() for pane in panes))
        self.assertTrue(f.layout_settings_pane.IsCollapsed())
        self.assertFalse(f.layout_settings_pane.GetPane().IsShown())
        self.assertEqual(f.hidden_flag,0)

    def test_original_panel_name_migrates_legacy_configs_without_losing_values(self):
        from mulimgviewer.src.configuration import read_config,write_config
        f=self.frame
        self.assertFalse(hasattr(f,'show_unit'))
        self.assertEqual(f.show_original_panel.GetLabel(),'Show original panel')
        self.assertEqual(f.show_original_panel.GetParent(),f.custom_settings_pane.GetPane())
        for value in (False,True):
            path=self.fixture.directory/'legacy_original.json'
            write_config(path,{'output':{'show_unit':value}})
            migrated=read_config(path)['output']
            self.assertEqual(migrated['show_original_panel'],value)
            self.assertNotIn('show_unit',migrated)
        path=self.fixture.directory/'legacy_original.json'
        write_config(path,{'output':{'show_unit':True,'show_original_panel':False}})
        self.assertFalse(read_config(path)['output']['show_original_panel'])
        f.show_original_panel.SetValue(False);f.save_configuration(None)
        self.assertFalse(self.fixture.read()['output']['show_original_panel'])
        self.assertNotIn('show_unit',self.fixture.read()['output'])
        f._save_session_configuration()
        other=self.fixture.frame()
        self.assertFalse(other.show_original_panel.GetValue())

    def test_full_width_header_toggles_without_refresh_and_keeps_controls(self):
        f=self.frame;pane=f.input_settings_pane;header=f.input_settings_pane_header
        f._layout_settings_sections()
        for width in (280,320,420):
            f.scrolledWindow_set.SetSize((width,700));f._layout_settings_sections()
            self.assertEqual(header.Size.width,pane.ClientSize.width-2)
            self.assertGreaterEqual(header.Size.height,header.GetTextExtent(header.GetLabel()).height)
        f.interval.ChangeValue('0.25')
        with patch.object(f,'refresh') as refresh,patch.object(f,'show_img_init') as render:
            for expected in (True,False):
                event=wx.CommandEvent(wx.wxEVT_BUTTON,header.GetId());event.SetEventObject(header)
                header.GetEventHandler().ProcessEvent(event)
                self.fixture.app.Yield(True)
                self.assertEqual(pane.IsCollapsed(),expected)
                self.assertEqual(pane.GetPane().IsShown(),not expected)
                self.assertEqual(f.interval.GetValue(),'0.25')
            refresh.assert_not_called();render.assert_not_called()
        self.assertTrue(header.GetFont().GetWeight()>=wx.FONTWEIGHT_BOLD)

    def test_format_options_enable_only_applicable_encoders(self):
        f=self.frame
        for fmt,pdf,expected in ((0,0,(True,False,False)),(1,0,(False,True,False)),
                                  (2,0,(False,False,True)),(2,1,(True,False,True))):
            f.save_format.SetSelection(fmt);f.pdf_compression.SetSelection(pdf);f._sync_save_controls()
            self.assertEqual(tuple(w.IsEnabled() for w in (f.save_quality,f.png_compression,f.pdf_compression)),expected)

    def test_independent_cache_quality_is_staged_until_refresh(self):
        f=self.frame;f.cache_save_format.SetSelection(0)
        f.save_quality.SetValue(83);f.cache_jpg_quality.SetValue(27)
        f.cache_quality_follow_save.SetValue(False);f._sync_save_controls()
        self.assertTrue(f.cache_jpg_quality.IsEnabled());self.assertEqual(f._effective_cache_quality(),27)
        self.assertEqual(f.shared_config.save_quality,100)
        f.cache_quality_follow_save.SetValue(True);f._sync_save_controls()
        self.assertFalse(f.cache_jpg_quality.IsEnabled());self.assertEqual(f._effective_cache_quality(),83)
        self.assertEqual(f.cache_jpg_quality.GetValue(),27)

    def test_output_folder_and_new_options_round_trip_and_reset(self):
        f=self.frame;path=str(self.fixture.directory.parent/'output');Path(path).mkdir()
        f._set_output_directory(path)
        f.png_compression.SetSelection(2);f.pdf_compression.SetSelection(1)
        f.cache_quality_follow_save.SetValue(False);f.cache_jpg_quality.SetValue(37)
        f.save_configuration(None)
        data=self.fixture.read()['output']
        self.assertEqual(data['output_directory'],path)
        self.assertEqual(data['cache_jpg_quality'],37)
        f.output_directory.ChangeValue('');f.load_configuration(None)
        self.assertEqual(f.out_path_str,path)
        self.assertEqual(f.png_compression.GetSelection(),2)
        self.assertEqual(f.pdf_compression.GetSelection(),1)
        self.assertFalse(f.cache_quality_follow_save.GetValue())
        f.reset_configuration(None)
        self.assertEqual(f.out_path_str,'');self.assertEqual(f.png_compression.GetSelection(),1)
        self.assertEqual(f.pdf_compression.GetSelection(),0)
        self.assertTrue(f.cache_quality_follow_save.GetValue())


class ExportCompressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=export_fixtures.ExportModesTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.manager=self.fixture.manager(1,False,False,'original');self.root=self.fixture.root

    def test_png_compression_changes_size_without_changing_pixels(self):
        m=self.manager;sizes=[]
        with Image.new('RGB',(512,256),'white') as image:
            for level in (1,6,9):
                m.png_compression_level=level;path=self.root/f'level_{level}.png'
                m.ImgF.save_img_diff_format(path,image,1);sizes.append(path.stat().st_size)
                with Image.open(path) as saved:self.assertEqual(saved.tobytes(),image.tobytes())
        self.assertGreater(sizes[0],sizes[-1])

    def test_png_recompression_keeps_dpi_text_icc_exif_and_pixels(self):
        from PIL import ImageCms,PngImagePlugin
        from mulimgviewer.src.export_controller import _write_export_file
        m=self.manager;source=self.root/'metadata.png'
        text=PngImagePlugin.PngInfo();text.add_itxt('Description','Original description')
        exif=Image.Exif();exif[37510]=b'ASCII\0\0\0Injected title'
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        with Image.new('RGB',(40,24),'red') as image:
            image.save(source,dpi=(240,240),pnginfo=text,exif=exif,icc_profile=profile)
        with Image.open(source) as image:dpi=image.info['dpi'];pixels=image.tobytes()
        for level in (1,6,9):
            m.png_compression_level=level;target=self.root/f'metadata_level_{level}.png'
            _write_export_file(m,source,target,1)
            with Image.open(target) as image:
                self.assertEqual(image.tobytes(),pixels)
                self.assertEqual(image.info['dpi'],dpi)
                self.assertEqual(image.text['Description'],'Original description')
                self.assertEqual(image.info['icc_profile'],profile)
                self.assertEqual(image.getexif()[37510],exif[37510])

    def test_pdf_modes_cover_composed_selected_and_magnifier_outputs(self):
        m=self.manager;m.layout_params[35]=2
        m.layout_params[17][1]=True
        for compact in (0,1):
            m.pdf_compression=compact
            out=self.root/f'pdf_{compact}';export_page(m,out,6,512*1024**2,1)
            paths=list(out.rglob('*.pdf'));self.assertTrue(paths)
            self.assertTrue(any('magnifier_images' in p.parts for p in paths))
            self.assertTrue(any('select_images' in p.parts for p in paths))
            self.assertTrue(any('composed' in p.parts for p in paths))
            for path in paths:
                self.assertEqual(b'/DCTDecode' in path.read_bytes(),bool(compact),str(path))
                self.assertTrue(path.read_bytes().startswith(b'%PDF'))


    def test_pdf_compact_quality_controls_embedded_raster_size(self):
        import numpy as np
        m=self.manager;m.pdf_compression=1
        m.layout_params.extend([0,25])
        sizes=[]
        with Image.fromarray(np.random.default_rng(7).integers(0,256,(128,128,3),dtype=np.uint8),'RGB') as image:
            for quality in (25,95):
                m.layout_params[42]=quality;path=self.root/f'compact_{quality}.pdf'
                m.ImgF.save_img_diff_format(path,image,2,use_vector_titles=False)
                sizes.append(path.stat().st_size)
        self.assertGreater(sizes[1],sizes[0])

    def test_pdf_compression_preserves_vector_title_commands(self):
        import base64,re,zlib
        m=self.manager;m.layout_params[35]=2;m.layout_params[17][1]=True
        m.layout_params[2]=[3,1]  # Original + magnifier + title must all fit.
        for mode in (0,1):
            m.pdf_compression=mode;out=self.root/f'vector_{mode}'
            export_page(m,out,0,512*1024**2,1)
            data=(out/'image/composed/page_000001.pdf').read_bytes()
            streams=[]
            for encoded in re.findall(rb'stream\r?\n(.*?)endstream',data,re.S):
                try:encoded=base64.a85decode(encoded.strip(),adobe=True)
                except (ValueError,OverflowError):pass
                try:streams.append(zlib.decompress(encoded))
                except zlib.error:pass
            self.assertTrue(any(b' Tj' in stream and b' Tf' in stream for stream in streams),mode)


if __name__=='__main__':unittest.main()
