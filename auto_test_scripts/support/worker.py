"""Run one module in an isolated process and always serialize its result."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import sys
import threading
import traceback
import unittest

HOME = Path(__file__).resolve().parents[1]
ROOT = HOME.parent
sys.path[:0] = [str(HOME), str(HOME/'cases'), str(ROOT/'src'), str(ROOT/'src/mulimgviewer/src')]
from support.reporting import RecordedResult


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):yield from flatten(item)
        else:yield item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('module')
    parser.add_argument('result', type=Path)
    parser.add_argument('--case', action='append', default=[])
    args = parser.parse_args()
    asynchronous = []
    def uncaught(kind, value, tb):
        asynchronous.append(''.join(traceback.format_exception(kind, value, tb)))
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = uncaught
    threading.excepthook = lambda args: uncaught(args.exc_type, args.exc_value, args.exc_traceback)
    sys.unraisablehook = lambda args: uncaught(args.exc_type, args.exc_value, args.exc_traceback)
    suite = unittest.defaultTestLoader.loadTestsFromName(args.module)
    if args.case:
        suite = unittest.TestSuite(test for test in flatten(suite) if any(fnmatch.fnmatch(test.id(), pattern) for pattern in args.case))
    count = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    payload = dict(name=args.module, cases=result.records, discovered=count,
        status='passed' if result.wasSuccessful() and count and not asynchronous else 'failed',
        infrastructure_error='\n'.join(asynchronous) or ('' if count else 'No tests matched; this is not a successful test run.'))
    args.result.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if payload['status']=='passed' else 1


if __name__ == '__main__':sys.exit(main())
