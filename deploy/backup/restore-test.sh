#!/usr/bin/env bash
# Prove a backup can be restored: load it into a scratch database, check the
# tables have rows, check the files archive reads, then drop the scratch
# copy. An untested backup is a hope, not a backup.
#
#   restore-test.sh                          the newest backup
#   restore-test.sh /backups/db/<file>.dump  that one (and its files archive)
set -euo pipefail
: "${BACKUP_ROOT:=/backups}"
log() { echo "[$(date -Is)] $*"; }
# shellcheck source=labkey.sh
. "$(dirname "$0")/labkey.sh"

if [ -n "${1:-}" ]; then
  dump=$1
  [ -f "$dump" ] || { log "no such dump: $dump"; exit 1; }
  stamp=$(basename "$dump"); stamp=${stamp%.age}; stamp=${stamp%.dump}; stamp=${stamp#biomanager-}
  files=$(ls -1 "$BACKUP_ROOT/files/biomanager-files-$stamp.tar.gz"* | head -n 1)
else
  dump=$(ls -1t "$BACKUP_ROOT"/db/biomanager-*.dump* | head -n 1)
  files=$(ls -1t "$BACKUP_ROOT"/files/biomanager-files-*.tar.gz* | head -n 1)
fi
scratch="biomanager_restore_test"
named=$(basename "$dump")
opened=$(mktemp -d)

dropdb --if-exists "$scratch"
createdb "$scratch"
trap 'dropdb --if-exists "$scratch"; rm -rf -- "$opened"' EXIT
# A locked backup is opened with the lab's key: the test proves the key opens it too.
dump=$(labkey_open "$dump" "$opened/db.dump") || { log "RESTORE TEST FAILED: $named could not be opened with the lab's key"; exit 1; }
files=$(labkey_open "$files" "$opened/files.tar.gz") || { log "RESTORE TEST FAILED: its files archive could not be opened with the lab's key"; exit 1; }

pg_restore --no-owner --exit-on-error --dbname="$scratch" "$dump"

# Every table the live database has must come back, and a table that has
# rows now must not come back empty. (Counts can differ a little: people
# keep working after the dump was taken.)
live_tables=$(psql -XAtc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
restored_tables=$(psql -XAtd "$scratch" -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
if [ "$restored_tables" -lt "$live_tables" ]; then
  log "restored database has $restored_tables tables, the live one $live_tables"
  exit 1
fi
report=""
for table in users mice strains plasmids organisms audit_log; do
  live=$(psql -XAtc "SELECT count(*) FROM $table")
  restored=$(psql -XAtd "$scratch" -c "SELECT count(*) FROM $table")
  if [ "$live" -gt 0 ] && [ "$restored" -eq 0 ]; then
    log "$table has $live rows but none in the restored copy"
    exit 1
  fi
  report="$report $table=$restored/$live"
done
tar -tzf "$files" > /dev/null

date -u +%s > "$BACKUP_ROOT/last-restore-test"
log "restore test passed for $named (restored/live:$report)"

# The off-site copy, read back with the repository password: the check that
# matters on the day this server is gone. restic check reads a fifth of the
# stored data each week, so over a few weeks all of it gets read.
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
  timeout 3600 restic check --read-data-subset=20% > /dev/null 2>&1 \
    || { log "OFF-SITE CHECK FAILED: restic check found a problem in $RESTIC_REPOSITORY"; exit 1; }
  away=$(mktemp -d)
  trap 'dropdb --if-exists "$scratch"; rm -rf -- "$away" "$opened"' EXIT
  timeout 3600 restic restore latest --tag biomanager --host biomanager --target "$away" --include '*.dump*' > /dev/null \
    || { log "OFF-SITE RESTORE FAILED: could not restore the latest snapshot"; exit 1; }
  offsite_dump=$(find "$away" -name 'biomanager-*.dump*' | head -n 1)
  [ -n "$offsite_dump" ] && offsite_dump=$(labkey_open "$offsite_dump" "$away/opened.dump") \
    && pg_restore --list "$offsite_dump" > /dev/null \
    || { log "OFF-SITE RESTORE FAILED: the restored dump is missing or unreadable"; exit 1; }
  date -u +%s > "$BACKUP_ROOT/last-offsite-test"
  log "off-site copy readable: $(basename "$offsite_dump") restored from $RESTIC_REPOSITORY"
fi
