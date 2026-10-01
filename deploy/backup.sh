#!/bin/sh
# Back up the database and uploaded documents into /backups/<timestamp>/.
set -eu
STAMP=$(date +%Y%m%d-%H%M%S)
DEST=/backups/$STAMP
mkdir -p "$DEST"
pg_dump --no-owner --format=custom --file="$DEST/database.dump" "$DATABASE_URL"
tar -czf "$DEST/documents.tar.gz" -C /data media
echo "Backup written to $DEST"
find /backups -mindepth 1 -maxdepth 1 -type d -mtime +"${BACKUP_KEEP_DAYS:-30}" -exec rm -rf {} +
