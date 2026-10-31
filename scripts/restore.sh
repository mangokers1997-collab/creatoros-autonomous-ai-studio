#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: $0 path/to/creatoros-backup.db" >&2
  exit 2
fi

CONTAINER="${CREATOROS_CONTAINER:-creatoros}"
docker cp "$1" "$CONTAINER:/tmp/creatoros-restore.db"
docker exec "$CONTAINER" python -c 'import os,sqlite3; p=os.getenv("CREATOROS_DB_PATH","/data/creatoros.db"); src=sqlite3.connect("/tmp/creatoros-restore.db"); dst=sqlite3.connect(p); src.backup(dst); dst.close(); src.close()'
docker exec "$CONTAINER" rm -f /tmp/creatoros-restore.db
echo "Database restored. Restart the service before using it."
