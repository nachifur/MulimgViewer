"""Source-position regressions independent of disk scanning and native GUI layout."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src.status_info import ImageSourceIndex, selection_info, status_widths


class StatusInfoTests(unittest.TestCase):
    def image(self, kind, paths, names, displayed, sequential=False):
        model = SimpleNamespace(type=kind, path_list=paths, name_list=names,
            parallel_to_sequential=sequential, flist=displayed,
            xy_grids_id_list=[1, 0], count_per_action=1, action_count=0)
        model._status_source_index = ImageSourceIndex(model)
        return model

    def test_image_input_modes_and_layout_order(self):
        cases = [(2, ['a'], ['0.png', '1.png'], ['a/0.png', 'a/1.png'], 'Image 2/2 | Folder 1/1'),
                 (0, ['b', 'a'], ['0.png', '1.png'], ['b/1.png', 'a/1.png'], 'Image 2/2 | Folder 2/2'),
                 (1, ['b', 'a'], ['0.png', '1.png'], ['b/0.png', 'a/0.png'], 'Image 1/2 | Folder 2/2'),
                 (3, ['b/z.png', 'a/z.png'], ['z.png', 'z.png'], ['b/z.png', 'a/z.png'], 'Image 2/2 | Folder 2/2')]
        for kind, paths, names, displayed, expected in cases:
            with self.subTest(mode=kind):
                model = self.image(kind, paths, names, displayed)
                info = selection_info(model, SimpleNamespace(video_mode=False))
                self.assertEqual(info['position'], expected)
                self.assertEqual(info['source'], str(Path(displayed[1]).absolute()))

    def test_flattened_parallel_and_different_folder_lengths(self):
        model = self.image(1, ['b', 'a'], [['1.png'], ['9.png', '7.png']], ['a/7.png', 'b/1.png'], True)
        self.assertEqual(selection_info(model, SimpleNamespace(video_mode=False), 1)['position'],
                         'Image 2/2 | Folder 2/2')

    def test_file_list_duplicate_paths_use_displayed_occurrence(self):
        model = self.image(3, ['a/x.png', 'a/x.png'], ['x.png', 'x.png'], ['a/x.png'])
        model.xy_grids_id_list = [0]
        model.action_count = 1
        self.assertEqual(selection_info(model, SimpleNamespace(video_mode=False))['position'],
                         'Image 2/2 | Folder 1/1')

    def test_video_modes_skips_clamped_short_video_and_layout_order(self):
        model = SimpleNamespace(flist=['cache/a.jpeg', 'cache/b.jpeg'], xy_grids_id_list=[1, 0],
            _status_video_sources=((0, 7), (1, 2)), _status_video_paths=('a/one.mp4', 'b/two.mp4'),
            _status_video_counts=(100, 3), _status_video_fps=(30, 10), _status_video_step=3)
        info = selection_info(model, SimpleNamespace(video_mode=True))
        self.assertEqual(info['position'], 'Frame 3/3 | Video 2/2')
        self.assertEqual(info['timestamp'], '00:00:00.600')
        self.assertEqual(info['source'], str(Path('b/two.mp4').absolute()))
        self.assertIn('original frame 7', info['detail'])

    def test_missing_and_blank_cells_have_no_invented_source(self):
        model = SimpleNamespace(flist=[], xy_grids_id_list=[])
        self.assertIsNone(selection_info(model, SimpleNamespace(video_mode=True)))
        model.flist=['a.png']; model.xy_grids_id_list=[-1]
        self.assertIsNone(selection_info(model, SimpleNamespace(video_mode=False)))

    def test_custom_function_variants_resolve_original_and_blank_is_unselected(self):
        model = self.image(1, ['a', 'b'], ['x.png'], ['a/x.png', 'b/x.png'])
        model.xy_grids_id_list = [0, 1, 2]
        model._status_source_slots = (1, -1, 0)
        cfg = SimpleNamespace(video_mode=False)
        self.assertEqual(selection_info(model, cfg, 0)['position'], 'Image 1/1 | Folder 2/2')
        self.assertIsNone(selection_info(model, cfg, 1))
        self.assertEqual(selection_info(model, cfg, 2)['position'], 'Image 1/1 | Folder 1/2')

    def test_video_lists_support_relative_csv_paths_and_skip_missing_entries(self):
        import tempfile
        from mulimgviewer.src.video_tools import read_video_file_list
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a,b.mp4').write_bytes(b'fixture')
            (root / 'second.mov').write_bytes(b'fixture')
            listing = root / 'list.csv'
            listing.write_text('"a,b.mp4",second.mov,missing.mp4\n', encoding='utf-8-sig')
            self.assertEqual(read_video_file_list(listing),
                             [str((root / 'a,b.mp4').absolute()), str((root / 'second.mov').absolute())])

    def test_image_file_list_relative_paths_resolve_beside_list(self):
        import tempfile
        from PIL import Image
        from mulimgviewer.src.utils_img import ImgManager
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB',(8,8)).save(root/'image.png')
            listing=root/'list.txt'
            listing.write_text('image.png\n',encoding='utf-8')
            manager=ImgManager()
            manager.init(str(listing),type=3)
            self.assertEqual(manager.path_list,[str(root/'image.png')])
            manager.set_count_per_action(1)
            manager.get_flist()
            manager.xy_grids_id_list=[0]
            info=selection_info(manager,SimpleNamespace(video_mode=False))
            self.assertEqual(info['source'],str(root/'image.png'))

    def test_narrow_and_wide_windows_keep_all_four_fields(self):
        for width in (320, 600, 1200, 2400):
            for measured in ([120, 400, 200, 100], [600, 1000, 3000, 4000]):
                result = status_widths(width, measured)
                self.assertEqual(sum(result), width)
                self.assertTrue(all(value > 0 for value in result))
                self.assertGreater(result[1], result[0])


if __name__ == '__main__':
    unittest.main()
