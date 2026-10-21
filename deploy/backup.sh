#!/bin/sh
# Daily backup of the database and photos. Keeps 30 days. Run from cron as root.
set -eu
APP=/opt/dairyerp
OUT=$APP/backups
STAMP=$(date +%Y%m%d_%H%M)
mkdir -p "$OUT"
# sqlite3 .backup makes a safe copy even while the server is writing
sqlite3 "$APP/data/dairy_erp.db" ".backup '$OUT/dairy_erp_$STAMP.db'"
gzip -f "$OUT/dairy_erp_$STAMP.db"
tar -czf "$OUT/uploads_$STAMP.tar.gz" -C "$APP/data" uploads
find "$OUT" -name 'dairy_erp_*.db.gz' -mtime +30 -delete
find "$OUT" -name 'uploads_*.tar.gz' -mtime +30 -delete
