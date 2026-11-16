"""Loaded input labels, effective ordering and automatic-title consistency."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.index_catalog import IndexCatalog
from mulimgviewer.src.display_modes import loaded_input_mode, auto_title_fields
from mulimgviewer.src.utils_img import ImgManager
from mulimgviewer.src.index_excel import write_index_xlsx
from test_index_excel import sheets


class DisplayModeTests(unittest.TestCase):
    def test_all_loaded_inputs_and_orders_match_excel(self):
        with tempfile.TemporaryDirectory() as root:
            for video in (False, True):
                for kind, choice in ((2,0),(0,1),(1,2),(3,3)):
                    for serial, sequential in ((False,False),(False,True),(True,False)):
                        cfg = SimpleNamespace(video_mode=video, status_input_mode=choice,
                            parallel_to_sequential=serial, real_video_path=['a.mp4','b.mp4'],
                            video_num_list=[3,4], video_fps_list=[10.,10.], skip_frames=0)
                        manager = SimpleNamespace(type=kind, parallel_to_sequential=serial,
                            path_list=['a','b'], count_per_action=2,
                            name_list=[['1.png'],['2.png']] if serial else ['1.png','2.png'])
                        model = IndexCatalog(manager,cfg,sequential)
                        expected = ('Sequential','Parallel auto','Parallel manual','Image File List')[choice]
                        self.assertEqual(model.input_mode,expected)
                        parallel = video or kind in (0,1)
                        order = ('parallel_to_sequential' if serial else
                                 'parallel_sequential' if sequential else 'parallel') if parallel else 'sequential'
                        self.assertEqual(model.order,order)
                        # Metadata sheet must use the same labels as the GUI.
                        path = Path(root)/'index.xlsx'
                        write_index_xlsx(path,model,0)
                        info = dict(sheets(path)['Info'][0])
                        self.assertEqual(info['Input mode'],expected)
                        self.assertEqual(info['Order'],order)

    def test_single_video_is_sequential_even_with_inactive_parallel_options(self):
        cfg = SimpleNamespace(video_mode=True, status_input_mode=3,
            parallel_to_sequential=False, real_video_path=['a.mp4'],
            video_num_list=[3], video_fps_list=[10.],skip_frames=0)
        manager=SimpleNamespace(type=2,parallel_to_sequential=False,
                               path_list=['cache/a'],name_list=[],count_per_action=2)
        model=IndexCatalog(manager,cfg,True)
        self.assertEqual((model.input_mode,model.order),('Image File List','sequential'))

    def test_video_auto_titles_ignore_import_route(self):
        for count in (1,3):
            for serial,sequential in ((False,False),(True,False),(False,True)):
                fields=auto_title_fields(0,True,count,serial,sequential)
                for kind in (1,2,3):
                    self.assertEqual(auto_title_fields(kind,True,count,serial,sequential),fields)

    def test_parallel_video_auto_titles_match_parallel_images(self):
        for kind in (0,1):
            for serial,sequential in ((False,False),(True,False),(False,True)):
                self.assertEqual(auto_title_fields(kind,True,3,serial,sequential),
                                 auto_title_fields(kind,False,3,serial,sequential))
        self.assertEqual(auto_title_fields(1,True,3,False,False),[False,True,True,False,False])

    def test_image_titles_keep_folder_identity_in_file_lists(self):
        self.assertEqual(auto_title_fields(3,False,0,False,False),[False,True,True,True,False])
        self.assertEqual(auto_title_fields(2,False,0,True,True),[False,False,True,True,False])

    def test_image_lists_accept_bom_quotes_spaces_and_relative_paths(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            Image.new('RGB',(8,8)).save(root/'one.png')
            for suffix,text in (('.txt','  "one.png"  \n\none.png\n'),
                                ('.csv','one.png,one.png\n')):
                listing=root/('images'+suffix)
                listing.write_text(text,encoding='utf-8-sig')
                manager=ImgManager();manager.init(str(listing),type=3)
                self.assertEqual(manager.path_list,[str(root/'one.png')]*2)
            listing=root/'empty.csv';listing.write_text('',encoding='utf-8')
            manager.init(str(listing),type=3)
            self.assertEqual(manager.path_list,[])

    def test_painted_input_is_independent_of_new_unpainted_selection(self):
        cfg=SimpleNamespace(video_mode=True,status_input_mode=1)
        manager=SimpleNamespace(type=1,_status_input_mode=3)
        self.assertEqual(loaded_input_mode(manager,cfg),'Parallel auto')
        self.assertEqual(loaded_input_mode(manager,cfg,painted=True),'Image File List')


if __name__ == '__main__':
    unittest.main()
