"""Ensure failed tests, subcases and missing prerequisites cannot produce green reports."""
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from urllib.request import urlopen
from unittest.mock import patch
import xml.etree.ElementTree as ET

HOME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HOME))
from support.reporting import RecordedResult, write_reports
import run_tests


class ReportingTests(unittest.TestCase):
    def test_package_link_opens_native_archive_with_special_characters(self):
        report_archive = runpy.run_path(str(HOME.parent / 'tools/package_desktop.py'))['report_archive']
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / '发布 #1%.tar.xz'
            archive.write_bytes(b'archive')
            output = io.StringIO()
            with patch('sys.stdout', output):
                report_archive(archive)
            _, path, link = output.getvalue().splitlines()
            self.assertEqual(path, 'Path: ' + str(archive.resolve()))
            self.assertTrue(link.startswith('Link: file://'))
            with urlopen(link[len('Link: '):]) as stream:
                self.assertEqual(stream.read(), b'archive')

    def test_console_summary_includes_case_id_and_exception_reason(self):
        module=dict(name='probe',status='failed',cases=[dict(id='probe.test_case',status='error',
            details='Traceback (most recent call last):\nValueError: short-path probe')])
        output=io.StringIO()
        with patch('sys.stdout',output):run_tests.print_module_result(module)
        self.assertIn('probe.test_case',output.getvalue())
        self.assertIn('ValueError: short-path probe',output.getvalue())

    def test_failed_subcase_is_visible_in_json_html_and_junit(self):
        class Probe(unittest.TestCase):
            def runTest(self):
                for mode in ('good','<bad>'):
                    with self.subTest(mode=mode):self.assertEqual(mode,'good')
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(Probe())
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.records[0]['status'],'failed')
        self.assertEqual([s['status'] for s in result.records[0]['subcases']],['passed','failed'])
        with tempfile.TemporaryDirectory() as directory:
            report=dict(status='FAILED',seconds=1.,revision={'commit':'probe'},modules=[dict(name='probe',status='failed',cases=result.records)])
            write_reports(directory,report)
            root=Path(directory)
            self.assertEqual(json.loads((root/'report.json').read_text(encoding='utf-8'))['status'],'FAILED')
            self.assertIn('&lt;bad&gt;',(root/'report.html').read_text(encoding='utf-8'))
            xml=ET.parse(root/'junit.xml');self.assertEqual(len(xml.findall('.//failure')),1)
            self.assertIn('<bad>',xml.find('.//failure').text)

    def test_setup_error_is_recorded_even_without_start_test(self):
        class Probe(unittest.TestCase):
            @classmethod
            def setUpClass(cls):raise RuntimeError('setup probe')
            def test_never_runs(self):pass
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Probe))
        self.assertFalse(result.wasSuccessful());self.assertEqual(result.records[0]['status'],'error')
        self.assertIn('setup probe',result.records[0]['details'])

    def test_missing_dependencies_produce_a_failed_report_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'cases').mkdir();(root/'cases/test_probe.py').write_text('',encoding='utf-8')
            with patch.object(run_tests,'HOME',root),patch.object(sys,'argv',['run_tests.py']),\
                 patch.object(run_tests,'preflight',side_effect=RuntimeError('missing codec')),\
                 patch.object(run_tests,'revision',return_value={'commit':'probe'}),patch('sys.stdout',io.StringIO()):
                self.assertEqual(run_tests.main(),1)
            report=json.loads(next((root/'reports').glob('*/report.json')).read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'FAILED');self.assertIn('missing codec',report['modules'][0]['infrastructure_error'])
            xml=ET.parse(next((root/'reports').glob('*/junit.xml')))
            self.assertEqual(xml.getroot().get('errors'),'1')

    def test_empty_selection_is_an_error_not_a_passing_run(self):
        with patch.object(sys,'argv',['run_tests.py','--module','does_not_exist']),patch('sys.stderr',io.StringIO()):
            with self.assertRaises(SystemExit) as raised:run_tests.main()
        self.assertNotEqual(raised.exception.code,0)

    def test_worker_catches_background_errors_and_rejects_empty_case_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'report_probe.py').write_text(
                'import threading,unittest\n'
                'class Probe(unittest.TestCase):\n'
                ' def test_background(self):\n'
                '  def fail():raise RuntimeError("background failure probe")\n'
                '  thread=threading.Thread(target=fail);thread.start();thread.join()\n',encoding='utf-8')
            env=os.environ.copy();env['PYTHONPATH']=str(root)+os.pathsep+env.get('PYTHONPATH','')
            for empty in (False,True):
                result=root/f'result_{empty}.json'
                command=[sys.executable,str(HOME/'support/worker.py'),'report_probe',str(result)]
                if empty:command+=['--case','*no_such_case*']
                process=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=15)
                self.assertNotEqual(process.returncode,0)
                report=json.loads(result.read_text(encoding='utf-8'))
                self.assertEqual(report['status'],'failed')
                self.assertIn('No tests matched' if empty else 'background failure probe',report['infrastructure_error'])


if __name__=='__main__':unittest.main()
