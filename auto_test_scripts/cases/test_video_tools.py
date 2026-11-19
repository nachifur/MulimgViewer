"""Executable lookup when an IDE does not inherit an activated Conda PATH."""
import os
import shutil
import sys
import tempfile
import unittest
import contextlib
import io
import runpy
import subprocess
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src.video_tools import resolve_video_tools


class VideoToolTests(unittest.TestCase):
    def checker(self):
        return runpy.run_path(str(Path(__file__).resolve().parents[2]/'tools/check_video_tools.py'))['main']

    def test_check_script_launches_both_tools_with_child_environment(self):
        main=self.checker();commands={'ffmpeg':'encoder','ffprobe':'probe'};env={'PATH':'private libraries'}
        versions=[SimpleNamespace(returncode=0,stdout=name+' version test\n',stderr='') for name in commands]
        with patch.dict(main.__globals__,resolve_video_tools=lambda:(commands,env)), \
                patch('subprocess.run',side_effect=versions) as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(),0)
        self.assertEqual([call.args[0] for call in run.call_args_list],[['encoder','-version'],['probe','-version']])
        self.assertTrue(all(call.kwargs['env'] is env for call in run.call_args_list))

    def test_check_script_returns_failure_for_missing_blocked_and_hung_tools(self):
        main=self.checker()
        with patch.dict(main.__globals__,resolve_video_tools=lambda:(_ for _ in ()).throw(FileNotFoundError('missing ffprobe'))), \
                contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main(),1)
            self.assertIn('missing ffprobe',errors.getvalue())
        for failure in (PermissionError('execution denied'),subprocess.TimeoutExpired('ffprobe',15)):
            with patch.dict(main.__globals__,resolve_video_tools=lambda:({'ffprobe':'probe'},{})), \
                    patch('subprocess.run',side_effect=failure),contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(),1)
                self.assertIn('FAILED',errors.getvalue())

    def test_current_python_environment_precedes_path_and_portable_tools(self):
        directory=self.prefix/('Library/bin' if sys.platform.startswith('win') else 'bin')
        expected={name:self.command(directory,name) for name in ('ffmpeg','ffprobe')}
        other=self.root/'other'
        for name in expected:self.command(other,name)
        with patch('sys.prefix',str(self.prefix)),self.environment(str(other)), \
                patch('mulimgviewer.src.video_tools.application_video_tools_dir',return_value=other):
            tools,_=resolve_video_tools()
        self.assertEqual(tools,expected)

    def test_explicit_overrides_precede_the_interpreter_environment(self):
        directory=self.prefix/('Library/bin' if sys.platform.startswith('win') else 'bin')
        for name in ('ffmpeg','ffprobe'):self.command(directory,name)
        expected={name:self.command(self.root/'override',name) for name in ('ffmpeg','ffprobe')}
        with patch('sys.prefix',str(self.prefix)),self.environment(),patch.dict(os.environ,
                FFMPEG_BINARY=expected['ffmpeg'],FFPROBE_BINARY=expected['ffprobe']):
            tools,_=resolve_video_tools()
        self.assertEqual(tools,expected)

    def test_windows_linux_and_macos_find_their_native_executable_names(self):
        for platform,folder,suffix in (('win32','Library/bin','.exe'),('linux','bin',''),('darwin','bin','')):
            with self.subTest(platform=platform):
                expected={name:str((self.prefix/folder/(name+suffix)).resolve()) for name in ('ffmpeg','ffprobe')}
                available=set(expected.values())
                def which(command):
                    return str(Path(command).resolve()) if os.path.isabs(command) and str(Path(command).resolve()) in available else None
                with patch('sys.platform',platform),patch('sys.prefix',str(self.prefix)),self.environment(), \
                        patch('mulimgviewer.src.video_tools.shutil.which',side_effect=which):
                    tools,_=resolve_video_tools()
                self.assertEqual(tools,expected)

    def test_stale_conda_prefix_does_not_override_running_python(self):
        for name in ('ffmpeg','ffprobe'):self.command(self.root/'different/Library/bin',name)
        with patch('sys.prefix',str(self.prefix)),patch('sys.base_prefix',str(self.prefix)),self.environment(), \
                patch.dict(os.environ,CONDA_PREFIX=str(self.root/'different')):
            with self.assertRaisesRegex(FileNotFoundError,'conda install'):
                resolve_video_tools()

    def test_application_local_tools_work_without_path_or_conda_binaries(self):
        directory=self.root/'application/tools/ffmpeg/bin'
        expected={name:self.command(directory,name) for name in ('ffmpeg','ffprobe')}
        with patch('sys.prefix',str(self.prefix)),self.environment(), \
                patch('mulimgviewer.src.video_tools.application_video_tools_dir',return_value=directory):
            tools,env=resolve_video_tools()
            self.assertEqual(tools,expected)
            self.assertEqual(os.environ['PATH'],'')
            self.assertIn(str(directory),env['PATH'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows runners can expose TEMP through an 8.3 alias; compare the
        # same canonical paths as the resolver instead of rejecting that alias.
        self.root = Path(self.temp.name).resolve()
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

    def test_interpreter_native_bin_works_with_empty_path(self):
        directory = self.prefix / ('Library/bin' if sys.platform.startswith('win') else 'bin')
        expected = {name: self.command(directory, name) for name in ('ffmpeg', 'ffprobe')}
        with patch('sys.prefix', str(self.prefix)), self.environment():
            tools, env = resolve_video_tools()
            self.assertEqual(os.environ['PATH'], '')
        self.assertEqual(tools, expected)
        self.assertIn(directory.resolve(), [Path(p).resolve() for p in env['PATH'].split(os.pathsep) if p])

    def test_conda_cache_restores_lookup_for_missing_environment_executable(self):
        native='Library/bin' if sys.platform.startswith('win') else 'bin'
        expected = dict(ffprobe=self.command(self.prefix / native, 'ffprobe'))
        record = self.prefix / 'conda-meta' / 'ffmpeg-8.1-build.json'
        record.parent.mkdir()
        record.write_text('{}', encoding='utf-8')
        directory = self.root / 'pkgs' / record.stem / native
        expected['ffmpeg'] = self.command(directory, 'ffmpeg')
        with patch('sys.prefix', str(self.prefix)), self.environment():
            tools, env = resolve_video_tools()
        self.assertEqual(tools, expected)
        self.assertIn(directory.resolve(), [Path(p).resolve() for p in env['PATH'].split(os.pathsep) if p])

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
