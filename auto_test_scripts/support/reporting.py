"""Portable unittest results, including subcases and asynchronous exceptions."""
import html
import json
import time
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.current = None

    def startTest(self, test):
        super().startTest(test)
        self.current = dict(id=test.id(), status='passed', seconds=0., details='', subcases=[])
        self.records.append(self.current)
        self.started = time.monotonic()

    def stopTest(self, test):
        self.current['seconds'] = round(time.monotonic() - self.started, 4)
        super().stopTest(test)
        self.current = None

    def record(self, test, status, details):
        record = self.current
        if record is None:
            record = dict(id=test.id(), status=status, seconds=0., details='', subcases=[])
            self.records.append(record)
        record.update(status=status, details=details)

    def addError(self, test, error):
        super().addError(test, error)
        self.record(test, 'error', self._exc_info_to_string(error, test))

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.record(test, 'failed', self._exc_info_to_string(error, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'skipped', reason)

    def addExpectedFailure(self, test, error):
        super().addExpectedFailure(test, error)
        self.record(test, 'expected_failure', self._exc_info_to_string(error, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'failed', 'Unexpected success: remove or review expectedFailure')

    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        details = '' if error is None else self._exc_info_to_string(error, test)
        self.current['subcases'].append(dict(id=subtest.id(), status='passed' if error is None else 'failed', details=details))
        if error is not None:self.current.update(status='failed', details=details)


def write_reports(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    records = [record for module in report['modules'] for record in module['cases']]
    failed = [record for record in records if record['status'] in ('failed', 'error')]
    skipped = [record for record in records if record['status'] in ('skipped', 'expected_failure')]
    root = ET.Element('testsuite', name='MulimgViewer regression', tests=str(len(records)),
        failures=str(len(failed)), skipped=str(len(skipped)), time=str(report['seconds']))
    for module in report['modules']:
        for record in module['cases']:
            case = ET.SubElement(root, 'testcase', classname=module['name'], name=record['id'], time=str(record['seconds']))
            if record['status'] in ('failed', 'error'):
                detail = record['details'] + '\n' + '\n'.join(s['id']+'\n'+s['details'] for s in record['subcases'] if s['status'] != 'passed')
                ET.SubElement(case, 'failure', message=record['status']).text = detail
            elif record['status'] in ('skipped', 'expected_failure'):
                ET.SubElement(case, 'skipped', message=record['details'])
        if module.get('infrastructure_error'):
            case = ET.SubElement(root, 'testcase', classname=module['name'], name='test infrastructure')
            ET.SubElement(case, 'error').text = module['infrastructure_error']
            root.set('tests', str(int(root.get('tests'))+1))
            root.set('errors', str(int(root.get('errors', '0'))+1))
    ET.ElementTree(root).write(directory/'junit.xml', encoding='utf-8', xml_declaration=True)
    esc = lambda value: html.escape(str(value))
    rows = []
    for module in report['modules']:
        rows.append('<h2>'+esc(module['name'])+' — '+esc(module['status'])+'</h2><a href="'+esc(module['name'])+'.log">Module log</a>')
        if module.get('infrastructure_error'):rows.append('<pre>'+esc(module['infrastructure_error'])+'</pre>')
        for record in module['cases']:
            text = record['details']
            subfailed = [s for s in record['subcases'] if s['status'] != 'passed']
            text += '\n'.join(s['id']+'\n'+s['details'] for s in subfailed)
            subcases='<details><summary>Subcase parameters</summary>'+''.join('<pre>'+esc(s['status']+' '+s['id'])+'</pre>' for s in record['subcases'])+'</details>' if record['subcases'] else ''
            rows.append('<details class="'+esc(record['status'])+'"><summary>'+esc(record['status'].upper())+' · '+esc(record['id'])+' · '+str(record['seconds'])+' s · subcases: '+str(len(record['subcases']))+'</summary><pre>'+esc(text or 'OK')+'</pre>'+subcases+'</details>')
    header = '<!doctype html><meta charset="utf-8"><title>MulimgViewer regression report</title><style>body{font:15px system-ui;margin:2em;max-width:1300px}summary{padding:.5em;cursor:pointer}.failed,.error{background:#ffe0e0}.skipped,.expected_failure{background:#fff1c0}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{margin-top:2em}</style>'
    summary = '<h1>'+esc(report['status'])+' · MulimgViewer regression</h1><pre>'+esc(json.dumps({k:v for k,v in report.items() if k!='modules'}, ensure_ascii=False, indent=2))+'</pre>'
    summary+='<h2>Feature coverage</h2>'+''.join('<p><strong>'+esc(f['status'])+'</strong> · '+esc(f['label'])+'</p>' for f in report.get('features',{}).values())
    (directory/'report.html').write_text(header+summary+''.join(rows), encoding='utf-8')
    lines = ['# MulimgViewer regression: '+report['status'], '', 'Commit: `'+report['revision'].get('commit', 'unknown')+'`',
        '', 'Tests: '+str(len(records))+'; failures/errors: '+str(len(failed))+'; skipped: '+str(len(skipped)),
        '', 'See report.html for details and junit.xml for CI integration.', '', '## Failed cases', '']
    lines += ['- `'+r['id']+'`' for r in failed] or ['None.']
    lines += ['', '## Infrastructure errors', '']
    lines += ['- '+m['name']+': '+m['infrastructure_error'] for m in report['modules'] if m.get('infrastructure_error')] or ['None.']
    lines += ['', '## Skipped cases', '']
    lines += ['- `'+r['id']+'`: '+r['details'] for r in skipped] or ['None.']
    (directory/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
