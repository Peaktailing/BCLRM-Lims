#!/usr/bin/env bash
# Copy the server's nightly backups to this Mac, so a copy lives somewhere
# other than the cloud VM. Run daily by launchd (install.sh); by hand:
#   ~/Library/Application\ Support/BioManager/pull-backups.sh
#
# Over SSH (Tailscale) as the `biomanager` host in ~/.ssh/config, from the
# server's BACKUP_DIR at /opt/biomanager/backups. A server with other names
# sets them when installing: BIOMANAGER_SSH_HOST=<host in ~/.ssh/config>
# BIOMANAGER_SERVER_BACKUPS=<its BACKUP_DIR, e.g.
# /opt/biomanager/Biomanager/deploy/backups> deploy/mac/install.sh. Only new
# files are copied and nothing is deleted because the server deleted it, so
# a damaged or compromised server cannot empty this copy. Each new database
# dump is checked readable (a dump locked with the lab's key, .age, is checked
# to be a whole locked file: only the lab's key opens it). The newest KEEP are kept.
#
# A macOS notification says when it fails, or when the server's newest
# backup is more than STALE_HOURS old: the server's own alerts cannot
# report that the server is gone.
set -uo pipefail
export PATH=/opt/homebrew/bin:/opt/homebrew/opt/postgresql@16/bin:/usr/bin:/bin:/usr/sbin:/sbin

HOST=${BIOMANAGER_SSH_HOST:-biomanager}
FROM=${BIOMANAGER_SERVER_BACKUPS:-/opt/biomanager/backups}
DEST=${BIOMANAGER_MAC_BACKUPS:-$HOME/BioManagerBackups}
KEEP=${KEEP:-30}
STALE_HOURS=${STALE_HOURS:-48}
LOG="$DEST/pull.log"

mkdir -p "$DEST/db" "$DEST/files" && chmod 700 "$DEST"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\" sound name \"Basso\"" >/dev/null 2>&1 || true; }
fail() { log "FAILED: $1"; notify "BioManager backup copy failed" "$1"; exit 1; }

had=$(mktemp)
trap 'rm -f "$had"' EXIT
ls -1 "$DEST/db" | sort > "$had"

for kind in db files; do
  rsync -rt --ignore-existing --chmod=Du=rwx,Dgo=,Fu=rw,Fgo= \
        -e "ssh -o BatchMode=yes -o ConnectTimeout=30" --rsync-path="sudo rsync" \
        "$HOST:$FROM/$kind/" "$DEST/$kind/" 2>> "$LOG" \
    || fail "Could not copy from the server. Is Tailscale on? Details: $LOG"
done

# Every dump that arrived this run must be readable.
new_dumps=$(ls -1 "$DEST/db" | sort | comm -13 "$had" -)
for dump in $new_dumps; do
  case "$dump" in
    *.age) [ "$(head -c 21 "$DEST/db/$dump")" = "age-encryption.org/v1" ] && [ "$(wc -c < "$DEST/db/$dump")" -gt 200 ] ;;
    *) ! command -v pg_restore >/dev/null || pg_restore --list "$DEST/db/$dump" > /dev/null 2>&1 ;;
  esac || { log "UNREADABLE: $dump"; notify "BioManager backup copy" "A copied backup is unreadable: $dump"; }
done

# Keep the newest KEEP of each (names sort by date).
prune() { local total; total=$(ls -1 "$1" | wc -l); [ "$total" -gt "$KEEP" ] || return 0
          ls -1 "$1" | sort | head -n $(( total - KEEP )) | while read -r old; do rm -f -- "$1/$old"; done; }
prune "$DEST/db"; prune "$DEST/files"

newest=$(ls -1 "$DEST/db" | sort | tail -n 1)
[ -n "$newest" ] || fail "No backups on the server yet."
# biomanager-20260925-194531Z.dump(.age) -> 2026-09-25 19:45:31 UTC
stamp=$(echo "$newest" | sed -E 's/biomanager-([0-9]{8})-([0-9]{6})Z\.dump(\.age)?/\1\2/')
taken=$(date -j -u -f "%Y%m%d%H%M%S" "$stamp" +%s 2>/dev/null || echo 0)
age=$(( ($(date +%s) - taken) / 3600 ))
if [ "$age" -ge "$STALE_HOURS" ]; then
  log "STALE: newest backup $newest is $age hours old"
  notify "BioManager backups have stopped" "The newest backup on the server is $age hours old."
fi
log "ok: $(echo "$new_dumps" | grep -c .) new, newest $newest (${age} h old), $(du -sh "$DEST" | cut -f1) kept in $DEST"
