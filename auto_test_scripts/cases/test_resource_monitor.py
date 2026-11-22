"""Measured rolling CPU/RSS/FPS, subprocess accounting, and mode isolation."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src.resource_monitor import ResourceMonitor, ChildCpuTracker, CHILD_CPU, run_video_process, tracked_video_process


class ResourceMonitorTests(unittest.TestCase):
    def setUp(self):
        self.monitor = ResourceMonitor(start=False)
        self.monitor.cpu_count = 4

    def test_cpu_uses_whole_machine_capacity_and_time_weighted_memory(self):
        self.monitor.record(0, 0, 100)
        self.monitor.record(1, 2, 200)
        self.monitor.record(2, 4, 400)
        result = self.monitor.snapshot(now=2)
        self.assertEqual(result['cpu'], 50.)
        self.assertEqual(result['memory'], 300.)
        self.assertEqual(result['memory_now'], 400)

    def test_rolling_window_clips_partial_samples(self):
        self.monitor.record(0, 0, 0)
        self.monitor.record(8, 8, 100)
        self.monitor.record(12, 16, 300)
        result = self.monitor.snapshot(now=12)
        self.assertAlmostEqual(result['cpu'], 35.)
        self.assertEqual(result['memory'], 180.)
        self.assertEqual(result['seconds'], 10.)

    def test_reset_excludes_old_mode_and_inflight_sample(self):
        epoch = self.monitor.epoch
        self.monitor.record(0, 0, 100, epoch)
        self.monitor.record(1, 4, 100, epoch)
        self.monitor.reset()
        self.monitor.record(2, 8, 100, epoch)
        self.assertIsNone(self.monitor.snapshot(now=2)['cpu'])
        self.monitor.record(3, 12, 100)
        self.monitor.record(4, 13, 200)
        self.assertEqual(self.monitor.snapshot(now=4)['cpu'], 25.)

    def test_fps_counts_actual_adjacent_paints_and_handles_reverse_and_seek(self):
        self.monitor.frame_presented(20, now=1)
        self.monitor.frame_presented(20, now=1.1)
        self.monitor.frame_presented(21, now=1.5)
        self.assertEqual(self.monitor.snapshot(now=1.5)['fps'], 2.)
        self.monitor.reset_playback()
        self.monitor.frame_presented(21, direction=-1, now=2)
        self.monitor.frame_presented(20, direction=-1, now=2.25)
        self.assertEqual(self.monitor.snapshot(now=2.25)['fps'], 4.)
        self.monitor.frame_presented(50, now=3)
        self.assertIsNone(self.monitor.snapshot(now=3)['fps'])

    def test_windows_counter_includes_completed_and_running_cpu(self):
        tracker = ChildCpuTracker()
        tracker.completed = 3.
        tracker.active.add(object())
        with patch('sys.platform', 'win32'), \
             patch('mulimgviewer.src.resource_monitor._windows_cpu_time', return_value=2.):
            self.assertEqual(tracker.total([]), 5.)

    def test_fps_includes_time_waiting_for_next_frame(self):
        self.monitor.frame_presented(20, now=1)
        self.monitor.frame_presented(21, now=1.5)
        self.assertEqual(self.monitor.snapshot(now=2)['fps'], 1.)
        self.assertEqual(self.monitor.snapshot(now=12)['fps'], 0.)

    def test_short_lived_child_cpu_is_counted_after_exit(self):
        before = CHILD_CPU.total([])
        # Windows venv python.exe can be a redirector whose own CPU is zero;
        # measure the actual interpreter, as we measure a direct FFmpeg binary.
        interpreter=getattr(sys,'_base_executable',None) or sys.executable
        result = run_video_process([interpreter, '-c',
            'print(sum(i*i for i in range(2000000)))'], capture_output=True,
            encoding='utf-8', check=True)
        self.assertEqual(result.returncode, 0)
        self.assertGreater(CHILD_CPU.total([]), before)
        self.assertEqual(len(CHILD_CPU.active), 0)

    def test_process_wrapper_preserves_error_reporting(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            run_video_process([sys.executable, '-c', 'import sys; sys.exit(3)'],
                              capture_output=True, check=True)
        self.assertEqual(error.exception.returncode, 3)


    def test_streaming_child_is_reaped_when_consumer_stops_early(self):
        with tracked_video_process([sys.executable,'-c','import time;time.sleep(10)'],
                                   stdout=subprocess.PIPE) as process:
            self.assertIsNone(process.poll())
        self.assertIsNotNone(process.poll())
        self.assertFalse(CHILD_CPU.active)


if __name__ == '__main__':
    unittest.main()
