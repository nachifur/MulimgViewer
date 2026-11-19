"""Independent Func/XY/One/Unit/magnifier spacing and legacy migration."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from PIL import Image
from mulimgviewer.src.layout_gaps import GROUPS, gap_pair, normalize_gaps
from mulimgviewer.src.configuration import read_config
from mulimgviewer.src.utils_img import ImgManager


class LayoutGapTests(unittest.TestCase):
    def test_each_pair_has_its_own_named_level(self):
        values = [11, 13, 17, 19, 23, 29, 31, 37, 41, 43]
        for index, group in enumerate(GROUPS):
            self.assertEqual(gap_pair(values, group), values[2*index:2*index+2])
        self.assertEqual(normalize_gaps(','.join(map(str, values))), values)

    def test_legacy_eight_values_preserve_all_four_original_pairs(self):
        old = [10, 10, 5, 5, 3, 3, 2, 2]
        self.assertEqual(normalize_gaps(old), [10, 10] + old)
        for index, group in enumerate(GROUPS[1:]):
            self.assertEqual(gap_pair(old, group), old[2*index:2*index+2])
        self.assertEqual(old, [10, 10, 5, 5, 3, 3, 2, 2])

    def test_config_migrates_old_gaps_and_keeps_new_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            for value, expected in (
                    ('10,10,5,5,3,3,2,2', '10,10,10,10,5,5,3,3,2,2'),
                    ('11,13,17,19,23,29,31,37,41,43', '11,13,17,19,23,29,31,37,41,43')):
                path.write_text(json.dumps({'output': {'gap': value}}), encoding='utf-8')
                self.assertEqual(read_config(path)['output']['gap'], expected)

    def test_incomplete_or_non_numeric_gap_settings_are_rejected(self):
        for value in ('1,2', '1,2,3,4,5,6,7,8,9', '1,2,3,4,5,6,7,8,9,no'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_gaps(value)

    def test_real_inner_layout_uses_xy_one_unit_and_magnifier_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(16):
                Image.new('RGB', (32, 24), 'red').save(Path(directory) / f'{index:02d}.png')
            manager = ImgManager()
            manager.init(directory, type=2)
            params = [None] * 41
            params[:7] = [[2, 2], [2, 2], [3, 1],
                [11, 13, 17, 19, 23, 29, 31, 37, 41, 43], [1, 1], [1, 1], [32, 24]]
            params[7:17] = [0, [1, 1], [], [1, 1], False, False, 2, False, False, True]
            params[17] = [False] * 8 + ['12', [], 0, False, False, '']
            params[18:32] = [False, False, False, 0, False, False, False, False, False, False,
                [32, 24], [1, 2], False, [1, 1]]
            params[32:] = [False, '', 0, 1, True, 0, False, '1,1', False]
            manager.layout_params = params
            manager.set_count_per_action(16)
            manager.set_action_count(0)
            manager.get_flist()
            layout, _, _ = manager.stitch_img_init(0, [])
            self.assertEqual(layout[1][1], [23, 29])
            self.assertEqual(layout[2][1], [17, 19])
            baseline = copy.deepcopy(layout)
            params[3][:2] = [101, 103]
            changed, _, _ = manager.stitch_img_init(0, [])
            self.assertEqual(changed[1][1], baseline[1][1])
            self.assertEqual(changed[2][1], baseline[2][1])
            self.assertEqual(changed[0][3], baseline[0][3])
            # Capture the actual magnifier sizing inputs in both preview/save.
            params[18] = True
            original = manager.ImgF.cal_magnifier_size
            for mode in (0, 1):
                with patch.object(manager.ImgF, 'cal_magnifier_size', wraps=original) as sizing:
                    manager.stitch_img_init(mode, [[2, 2, 8, 8, 1, 1, False]])
                    self.assertEqual(sizing.call_args.args[3], [41, 43])
                    self.assertEqual(sizing.call_args.kwargs['img_unit_gap'], [31, 37])
            manager.clear_cache()


if __name__ == '__main__':
    unittest.main()
