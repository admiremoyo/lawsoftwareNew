#!/bin/sh
# Restore a backup made by backup.sh (stop the web service first):
#   docker compose stop web && docker compose exec backup /deploy/restore.sh /backups/<timestamp>
set -eu
SRC=${1:?usage: restore.sh /backups/<timestamp>}
echo "This REPLACES the current database and documents with $SRC. Type RESTORE to continue:"
read answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled"; exit 1; }
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$SRC/database.dump"
rm -rf /data/media/* && tar -xzf "$SRC/documents.tar.gz" -C /data
echo "Restore complete."
