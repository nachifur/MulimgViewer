#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${MULIMGVIEWER_PYTHON:-python3}" "$SCRIPT_DIR/run_tests.py" "$@"
