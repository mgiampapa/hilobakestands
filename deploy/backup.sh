#!/usr/bin/env bash
# Nightly SQLite snapshot. Keeps 14 days locally.
# SPEC 5a calls for a copy to a second machine — pull these from the home box
# via scp/rsync cron, e.g.:
#   rsync -az oracle:/var/backups/hilobakestands/ ~/backups/hilobakestands/
set -euo pipefail
DB=/opt/hilobakestands/data/db.sqlite3
DEST=/var/backups/hilobakestands
STAMP=$(date +%Y%m%d-%H%M)
sqlite3 "$DB" ".backup '$DEST/db-$STAMP.sqlite3'"
gzip "$DEST/db-$STAMP.sqlite3"
find "$DEST" -name 'db-*.sqlite3.gz' -mtime +14 -delete
cp -r /opt/hilobakestands/media "$DEST/media-latest" 2>/dev/null || true
