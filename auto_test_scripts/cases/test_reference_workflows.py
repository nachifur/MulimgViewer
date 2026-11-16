"""Real GUI input -> display -> background export, using checked-in tiny media."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

HOME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HOME),str(HOME.parent/'src')]
import wx
from PIL import Image
import test_video_gui_async as gui_fixtures
from support.fixture_recipe import expected_pair

ASSETS=HOME/'assets'


class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        # Reuse lifecycle helpers, not inherited test cases. All output/cache
        # paths belong to this temporary viewer, never the developer's session.
        self.fixture=gui_fixtures.VideoGuiAsyncTests(methodName='runTest')
        self.fixture.setUpClass();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.frame=self.fixture.frame

    def workflow(self,video,mode):
        frame=self.frame;cfg=frame.shared_config
        frame.video_mode.SetValue(video);cfg.video_mode=video;cfg.batch_idx=0
        for name,value in dict(row_col='1,2',row_col_one_img='1,1',row_col_img_unit='1,1',
                gap='0,0,0,0,0,0,0,0',show_scale='1,1',output_scale='1,1',img_resolution='64,48').items():
            getattr(frame,name).ChangeValue(value)
        frame.title_show.SetValue(False);frame.show_custom_func.SetValue(False);frame.show_all_func.SetValue(False)
        frame.parallel_to_sequential.SetValue(False);frame.parallel_sequential.SetValue(False)
        frame.cache_save_format.SetSelection(1);frame.auto_save_all.SetValue(False)
        frame.choice_input_mode.SetSelection(mode)
        if mode==2:
            if video:
                cfg.real_video_path=[str(p) for p in sorted((ASSETS/'videos').glob('*.mp4'))]
                cfg.input_mode=1;frame._commit_video_settings()
                self.assertTrue(frame.video_manager.select_video(type=-1))
            else:
                frame.ImgManager.init([str(p) for p in sorted((ASSETS/'images').iterdir())],type=1)
                frame.show_img_init();frame.ImgManager.set_action_count(0);frame.show_img()
        else:
            if mode==3:path=ASSETS/'lists'/('videos.txt' if video else 'images.txt')
            elif mode==1:path=ASSETS/('videos' if video else 'images')
            else:path=ASSETS/('videos/source_001.mp4' if video else 'images/source_001')
            dialog=Mock();dialog.ShowModal.return_value=wx.ID_OK;dialog.GetPath.return_value=str(path)
            with patch.object(wx,'DirDialog',return_value=dialog),patch.object(wx,'FileDialog',return_value=dialog):
                frame.open_all_img(None)
        frame.choice_input_mode.SetSelection(mode)
        self.fixture.pump_until(lambda:getattr(frame,'_status_display_batch',None)==0 and frame.show_bmp_in_panel is not None)
        native=frame.show_bmp_in_panel.convert('RGB')
        self.addCleanup(native.close)
        with expected_pair(1,0,1 if mode==0 else 2,1 if mode==0 else 0) as expected:
            self.assertEqual(native.size,expected.size)
            self.assertEqual(native.tobytes(),expected.tobytes())
        # Every output combination is exercised through the actual Save handler.
        frame.xy_magnifier=[[4,4,20,20,1.,1.,False]]
        frame.color_list=[wx.Colour(255,0,0,255)]
        frame.refresh(None)
        if video:
            self.fixture.pump_until(lambda:bool(getattr(frame,'_video_display_key',None))
                and frame._video_display_key[0]==0 and frame._video_display_key[-1]==frame.video_manager._window_token)
        else:
            self.fixture.pump_until(lambda:frame.image_pipeline.displayed_key is not None
                and frame.image_pipeline.displayed_key[0]==frame.image_pipeline.generation)
        frame.auto_save_all.SetValue(False)
        for formats,suffix in ((0,'.jpg'),(1,'.png'),(2,'.pdf')):
            for output in range(7):
                with self.subTest(video=video,input_mode=mode,format=suffix,output=output):
                    folder=Path(f'workflow_{formats}_{output}').absolute();folder.mkdir()
                    frame.out_path_str=str(folder);frame.choice_output.SetSelection(output);frame.save_format.SetSelection(formats)
                    frame.save_img(None)
                    self.fixture.pump_until(lambda:not frame._export_active and frame._export_future.done(),timeout=20)
                    self.assertEqual(frame._export_status,'Save: success')
                    root=folder/('video' if video else 'image');algorithm=root/'algorithms/original';bits=output+1
                    self.assertEqual(bool(list((root/'composed').glob('*'+suffix))),bool(bits&1))
                    self.assertEqual(bool(list((algorithm/'stitch_images').glob('*'+suffix))),bool(bits&1))
                    self.assertEqual(bool(list((algorithm/'select_images').rglob('*'+suffix))),bool(bits&2))
                    self.assertEqual(bool(list((algorithm/'magnifier_images').rglob('*'+suffix))),bool(bits&4))
                    self.assertEqual(bool(list((algorithm/'origin_img_with_box').rglob('*'+suffix))),bool(bits&4))
                    files=list(root.rglob('*'+suffix));self.assertTrue(files)
                    for path in files:
                        if suffix=='.pdf':self.assertTrue(path.read_bytes().startswith(b'%PDF-'))
                        else:
                            with Image.open(path) as image:
                                self.assertEqual(image.format,'JPEG' if suffix=='.jpg' else 'PNG');image.verify()


def case(video,mode):
    def run(self):self.workflow(video,mode)
    run.__doc__=f'{"Video" if video else "Image"}: {("Sequential","Parallel auto","Parallel manual","File List")[mode]}, 7 outputs x 3 formats.'
    return run


for video in (False,True):
    for mode in range(4):setattr(ReferenceWorkflowTests,f'test_{"video" if video else "image"}_input_{mode}_all_outputs_and_formats',case(video,mode))


if __name__=='__main__':unittest.main()
