#!/usr/bin/env sh
# One refresh of the index: collect, enrich, export, assemble _site/.
# Suitable for cron, systemd timers, or a GitHub Actions schedule.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-src}"
python3 -m aiindex build
