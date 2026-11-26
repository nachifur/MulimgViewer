#!/bin/bash
set -e
cd "$(dirname "$0")"
prefix=$(pwd -P)
unset PYTHONHOME PYTHONPATH CONDA_PREFIX
export PYTHONNOUSERSITE=1
export PATH="$prefix/bin:$PATH"
. "$prefix/bin/activate"
if [ ! -f "$prefix/.relocated" ]; then
    "$prefix/bin/python" "$prefix/bin/conda-unpack"
    touch "$prefix/.relocated"
fi
cd "$prefix/viewer"
python="$prefix/bin/python"
if [ "$(uname -s)" = Darwin ]; then python="$prefix/bin/pythonw"; fi
if [ "${1:-}" = --self-check ]; then exec "$python" self_check.py; fi
exec "$python" MulimgViewer.py "$@"
