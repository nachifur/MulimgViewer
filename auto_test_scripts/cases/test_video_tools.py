"""Executable lookup when an IDE does not inherit an activated Conda PATH."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src.video_tools import resolve_video_tools


class VideoToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'envs' / 'viewer'
        self.prefix.mkdir(parents=True)
        real_which = shutil.which
        def local_which(command):
            # Host /usr/bin or Homebrew installations must not mask the fake
            # missing-installation/cache scenarios on Linux and macOS runners.
            if os.path.isabs(command):
                try:
                    Path(command).relative_to(self.root)
                except ValueError:
                    return None
            return real_which(command)
        lookup = patch('mulimgviewer.src.video_tools.shutil.which', side_effect=local_which)
        lookup.start()
        self.addCleanup(lookup.stop)

    def command(self, directory, name):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name + ('.exe' if os.name == 'nt' else ''))
        path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        path.chmod(0o755)
        return str(path.resolve())

    def environment(self, path=''):
        return patch.dict(os.environ, dict(PATH=path, CONDA_PREFIX=str(self.prefix),
            FFMPEG_BINARY='', FFPROBE_BINARY=''))

    def test_interpreter_library_bin_works_with_empty_path(self):
        directory = self.prefix / 'Library' / 'bin'
        expected = {name: self.command(directory, name) for name in ('ffmpeg', 'ffprobe')}
        with patch('sys.prefix', str(self.prefix)), self.environment():
            tools, env = resolve_video_tools()
            self.assertEqual(os.environ['PATH'], '')
        self.assertEqual(tools, expected)
        self.assertIn(str(directory), env['PATH'])

    def test_conda_cache_restores_lookup_for_missing_environment_executable(self):
        expected = dict(ffprobe=self.command(self.prefix / 'Library' / 'bin', 'ffprobe'))
        record = self.prefix / 'conda-meta' / 'ffmpeg-8.1-build.json'
        record.parent.mkdir()
        record.write_text('{}', encoding='utf-8')
        directory = self.root / 'pkgs' / record.stem / 'Library' / 'bin'
        expected['ffmpeg'] = self.command(directory, 'ffmpeg')
        with patch('sys.prefix', str(self.prefix)), self.environment():
            tools, env = resolve_video_tools()
        self.assertEqual(tools, expected)
        self.assertIn(str(directory), env['PATH'])

    def test_path_has_priority_over_package_cache(self):
        directory = self.root / 'preferred'
        expected = {name: self.command(directory, name) for name in ('ffmpeg', 'ffprobe')}
        with patch('sys.prefix', str(self.prefix)), self.environment(str(directory)):
            tools, _ = resolve_video_tools()
        self.assertEqual(tools, expected)

    def test_explicit_invalid_override_has_actionable_error(self):
        with self.environment(), patch.dict(os.environ, FFMPEG_BINARY=str(self.root / 'missing.exe')):
            with self.assertRaisesRegex(FileNotFoundError, 'FFMPEG_BINARY'):
                resolve_video_tools()

