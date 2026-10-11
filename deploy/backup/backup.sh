#!/usr/bin/env bash
# One backup: the database and the app's data volume, each checked before
# it is kept; local copies pruned to KEEP_LOCAL; sent off-site when
# RESTIC_REPOSITORY is set. Exit 0: all done; 1: no backup; 2: the local
# backup is done but the off-site copy failed. Works outside Docker too, with the usual
# PGHOST/PGUSER/PGPASSWORD/PGDATABASE and APPDATA_DIR set.
set -euo pipefail
: "${BACKUP_ROOT:=/backups}" "${APPDATA_DIR:=/appdata}" "${KEEP_LOCAL:=30}"
log() { echo "[$(date -Is)] $*"; }
# shellcheck source=labkey.sh
. "$(dirname "$0")/labkey.sh"

# A dump of the wrong (or an empty) database would look like a backup.
if ! accounts=$(psql -XAtc "SELECT count(*) FROM users" 2>/dev/null); then
  log "$PGDATABASE on $PGHOST has no BioManager tables — wrong database, or the app has never started. No backup taken."
  exit 1
fi
# A lab with no accounts has nothing to keep, and a copy of it must never
# become the newest backup: on a replacement server, before its restore,
# that copy would go off-site and "restore latest" would bring back an
# empty lab.
if [ "${accounts:-0}" -eq 0 ]; then
  log "no accounts in $PGDATABASE yet: nothing to back up (and nothing sent off-site)."
  exit 0
fi

umask 077
trap 'rm -f -- "${dump:-}.partial" "${files:-}.partial"' EXIT   # a failed step leaves no half-written file
stamp=$(date -u +%Y%m%d-%H%M%SZ)
mkdir -p "$BACKUP_ROOT/db" "$BACKUP_ROOT/files"
dump="$BACKUP_ROOT/db/biomanager-$stamp.dump"
files="$BACKUP_ROOT/files/biomanager-files-$stamp.tar.gz"

# A consistent snapshot even while people are working: pg_dump reads one
# transaction. Written under a temporary name, so a half-written file is
# never mistaken for a backup.
pg_dump --format=custom --compress=6 --no-owner --file="$dump.partial"
pg_restore --list "$dump.partial" > /dev/null   # readable, table of contents intact
mv "$dump.partial" "$dump"

if ! tar -C "$APPDATA_DIR" --exclude="./.before-restore-*" -czf "$files.partial" . \
    || ! tar -tzf "$files.partial" > /dev/null; then
  rm -f -- "$dump"
  log "could not archive the app's files in $APPDATA_DIR. No backup taken."
  exit 1
fi
mv "$files.partial" "$files"

# Locked with the lab's key (labkey.sh): a backup that leaks, here or
# off-site, can't be read without it.
plain_dump=$dump plain_files=$files
if ! dump=$(labkey_lock "$plain_dump") || ! files=$(labkey_lock "$plain_files"); then
  for f in "$plain_dump" "$plain_files"; do rm -f -- "$f" "$f.age" "$f.age.partial"; done
  log "could not lock the backup with the lab's key. No backup taken."
  exit 1
fi
case "$dump" in *.age) ;; *) log "the lab's key isn't here yet ($LABKEY_DIR): this backup is not locked" ;; esac

log "backed up: $(basename "$dump") ($(du -h "$dump" | cut -f1)), $(basename "$files") ($(du -h "$files" | cut -f1))"

prune() {  # keep the newest KEEP_LOCAL files matching $1
  ls -1t $1 2>/dev/null | tail -n +$(( KEEP_LOCAL + 1 )) | while read -r old; do rm -f -- "$old"; done
}
prune "$BACKUP_ROOT/db/biomanager-*.dump*"
prune "$BACKUP_ROOT/files/biomanager-files-*.tar.gz*"

# Off-site: a failure here does not undo the local backup (it is recorded
# above as a success), but it is reported on its own: exit status 2, and no
# fresh last-offsite for the watchdog.
# restic retries an unreachable server for a long time; these limits make an
# outage fail in minutes (and get reported) instead of stalling the night.
: "${OFFSITE_CONNECT_TIMEOUT:=120}" "${OFFSITE_BACKUP_TIMEOUT:=3600}"
offsite() {
  local err rc
  err=$(timeout "$OFFSITE_CONNECT_TIMEOUT" restic cat config 2>&1 > /dev/null)
  rc=$?
  # restic's exit codes (0.17+) say why it could not open the repository;
  # its messages do not (every failure ends "Is there a repository…?").
  case $rc in
    0) ;;
    10) log "creating the off-site repository at $RESTIC_REPOSITORY"
        timeout "$OFFSITE_CONNECT_TIMEOUT" restic init > /dev/null || return 1 ;;
    12) log "cannot open the off-site repository: wrong RESTIC_PASSWORD"; return 1 ;;
    124) log "cannot open the off-site repository: no answer within ${OFFSITE_CONNECT_TIMEOUT}s"; return 1 ;;
    *) log "cannot open the off-site repository: $(echo "$err" | grep -v '^Is there a repository' | tail -n 1)"; return 1 ;;
  esac
  timeout "$OFFSITE_BACKUP_TIMEOUT" restic backup --quiet --tag biomanager --host biomanager "$dump" "$files" || return 1
  # Grouped by host and tag: each snapshot's paths carry its own time, so
  # restic's default grouping (host and paths) put every snapshot alone in
  # its group, and nothing was ever forgotten.
  timeout "$OFFSITE_BACKUP_TIMEOUT" restic forget --quiet --tag biomanager --host biomanager --group-by host,tags \
    --keep-daily 30 --keep-weekly 12 --keep-monthly 24 --prune \
    || log "off-site pruning failed (the new copy was made; old ones are kept)"
  log "sent off-site to $RESTIC_REPOSITORY"
}

date -u +%s > "$BACKUP_ROOT/last-success"

status=0
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
  if offsite; then
    date -u +%s > "$BACKUP_ROOT/last-offsite"
  else
    log "OFF-SITE COPY FAILED: the local backup above is fine"
    status=2
  fi
fi

if [ "$status" = 0 ] && [ -n "${HEALTHCHECK_PING_URL:-}" ]; then
  curl -fsS -m 10 --retry 3 "$HEALTHCHECK_PING_URL" > /dev/null || log "could not ping $HEALTHCHECK_PING_URL"
fi
exit "$status"
