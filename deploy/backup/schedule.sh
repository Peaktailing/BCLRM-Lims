#!/usr/bin/env bash
# Run a backup at BACKUP_TIME every day (and once at start, so a broken
# configuration shows up now rather than tomorrow night), and a test restore
# on RESTORE_TEST_WEEKDAY (1 = Monday … 7 = Sunday).
#
# The start-up backup is skipped when there is one from the last
# START_SKIP_HOURS: every `docker compose up -d --build` recreates this
# container, and a backup of the just-updated database would otherwise
# become the newest, where "Updating went wrong" (deploy/RUNBOOK.md) looks
# for the one from before the update.
set -uo pipefail
: "${BACKUP_TIME:=02:30}" "${RESTORE_TEST_WEEKDAY:=7}" "${BACKUP_ON_START:=1}" "${START_SKIP_HOURS:=12}"
: "${BACKUP_ROOT:=/backups}"

log() { echo "[$(date -Is)] $*"; }

run_once() {
  backup.sh
  case $? in
    0) ;;
    2) log "OFF-SITE COPY FAILED (local backup kept)" ;;   # backup.sh: 2 means only the off-site copy failed
    *) log "BACKUP FAILED"; return ;;
  esac
  if [ "$(date +%u)" = "$RESTORE_TEST_WEEKDAY" ]; then
    restore-test.sh || log "RESTORE TEST FAILED — a backup could not be restored"
  fi
}

recent_backup() {
  local newest
  newest=$(ls -1t "$BACKUP_ROOT"/db/biomanager-*.dump* 2>/dev/null | head -n 1)
  [ -n "$newest" ] && [ $(( $(date +%s) - $(stat -c %Y "$newest") )) -lt $(( START_SKIP_HOURS * 3600 )) ]
}

if [ "$BACKUP_ON_START" = "1" ]; then
  if recent_backup; then
    log "a backup from the last ${START_SKIP_HOURS} h is there already; none taken at start"
  else
    run_once
  fi
fi

while true; do
  now=$(date +%s)
  next=$(date -d "today $BACKUP_TIME" +%s)
  [ "$next" -le "$now" ] && next=$(date -d "tomorrow $BACKUP_TIME" +%s)
  log "next backup at $(date -d "@$next" -Is)"
  sleep $(( next - now ))
  run_once
done
