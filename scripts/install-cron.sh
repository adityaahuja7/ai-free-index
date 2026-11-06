#!/usr/bin/env sh
# Install a daily 06:15 refresh in the current user's crontab (idempotent).
set -eu
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LINE="15 6 * * * cd $ROOT && ./scripts/refresh.sh >> $ROOT/data/refresh.log 2>&1"
if crontab -l 2>/dev/null | grep -Fq "$ROOT/scripts/refresh.sh"; then
  echo "cron entry already present"
else
  (crontab -l 2>/dev/null; echo "$LINE") | crontab -
  echo "installed: $LINE"
fi
