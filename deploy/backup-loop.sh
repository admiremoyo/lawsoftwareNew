#!/bin/sh
# Runs backup.sh once a day at BACKUP_HOUR (server time, default 01:00).
set -u
while true; do
  now=$(date +%s)
  target=$(date -d "$(date +%Y-%m-%d) ${BACKUP_HOUR:-01}:00" +%s)
  [ "$target" -le "$now" ] && target=$((target + 86400))
  sleep $((target - now))
  /deploy/backup.sh || echo "BACKUP FAILED" >&2
done
