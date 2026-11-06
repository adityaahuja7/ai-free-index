#!/usr/bin/env sh
# Build the index and serve the dashboard locally.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-src}"
python3 -m aiindex serve --build --open "$@"
