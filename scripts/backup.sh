#!/usr/bin/env sh
set -eu

CONTAINER="${CREATOROS_CONTAINER:-creatoros}"
BACKUP_DIR="${CREATOROS_BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

# SQLite's backup API is used inside the running container to avoid copying a
# database while it is being modified.
docker exec "$CONTAINER" python -c 'import os,sqlite3; src=sqlite3.connect(os.getenv("CREATOROS_DB_PATH","/data/creatoros.db")); dst=sqlite3.connect("/tmp/creatoros-backup.db"); src.backup(dst); dst.close(); src.close()'
docker cp "$CONTAINER:/tmp/creatoros-backup.db" "$BACKUP_DIR/creatoros-$STAMP.db"
docker exec "$CONTAINER" rm -f /tmp/creatoros-backup.db

echo "Database backup created: $BACKUP_DIR/creatoros-$STAMP.db"
echo "IMPORTANT: Back up /data/secure_tokens separately and keep it encrypted and private."
