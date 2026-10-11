#!/usr/bin/env bash
# Put a backup back. Stop the app first (docker compose stop app).
#
#   restore.sh /backups/db/biomanager-X.dump.age [/backups/files/biomanager-files-X.tar.gz.age]
#
# A backup locked with the lab's key (.age) is opened with the key in
# /labkey, or with the lab's recovery key given as BIOMANAGER_RECOVERY_KEY
# (a new server, before the lab is back: labkey.sh).
#
# Nothing is deleted: the current database is renamed biomanager_before_<time>
# and the current files are moved into /appdata/.before-restore-<time>/, so a
# wrong restore can itself be undone.
set -euo pipefail
: "${APPDATA_DIR:=/appdata}" "${PGDATABASE:=biomanager}"
# shellcheck source=labkey.sh
. "$(dirname "$0")/labkey.sh"
dump=${1:?usage: restore.sh DUMP [FILES_TARBALL]}
files=${2:-}
stamp=$(date -u +%Y%m%d%H%M%S)
opened=$(mktemp -d)
trap 'rm -rf -- "$opened"' EXIT
[ -f "$dump" ] || { echo "no such dump: $dump — nothing was changed"; exit 1; }
dump=$(labkey_open "$dump" "$opened/db.dump") || { echo "nothing was changed"; exit 1; }
if [ -n "$files" ]; then
  [ -f "$files" ] || { echo "no such files archive: $files — nothing was changed"; exit 1; }
  files=$(labkey_open "$files" "$opened/files.tar.gz") || { echo "nothing was changed"; exit 1; }
fi
# Both backups are checked before anything changes: a mistyped files path
# found only after the database was replaced left the app with no files
# (and a new signing key).
[ -f "$dump" ] || { echo "no such dump: $dump — nothing was changed"; exit 1; }
pg_restore --list "$dump" > /dev/null || { echo "$dump is not a readable backup — nothing was changed"; exit 1; }
if [ -n "$files" ]; then
  [ -f "$files" ] || { echo "no such files archive: $files — nothing was changed"; exit 1; }
  tar -tzf "$files" > /dev/null || { echo "$files is not a readable archive — nothing was changed"; exit 1; }
fi

others=$(psql -XAtd postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE' AND pid <> pg_backend_pid()")
if [ "$others" != "0" ]; then
  echo "$others connection(s) to $PGDATABASE are open. Stop the app first: docker compose stop app"
  exit 1
fi

kept="${PGDATABASE}_before_${stamp}"
psql -XAtd postgres -c "ALTER DATABASE \"$PGDATABASE\" RENAME TO \"$kept\""
createdb "$PGDATABASE"
if ! pg_restore --no-owner --exit-on-error --dbname="$PGDATABASE" "$dump"; then
  echo "Restore failed; putting the previous database back."
  dropdb "$PGDATABASE"
  psql -XAtd postgres -c "ALTER DATABASE \"$kept\" RENAME TO \"$PGDATABASE\""
  exit 1
fi
echo "database restored from $(basename "$dump"); the previous one is kept as $kept"

if [ -n "$files" ]; then
  aside="$APPDATA_DIR/.before-restore-$stamp"
  mkdir -p "$aside"
  find "$APPDATA_DIR" -mindepth 1 -maxdepth 1 ! -name '.before-restore-*' -exec mv -t "$aside" {} +
  if ! tar -C "$APPDATA_DIR" -xzf "$files"; then
    echo "Unpacking the files failed; putting the previous ones back (the database restore stands)."
    find "$APPDATA_DIR" -mindepth 1 -maxdepth 1 ! -name '.before-restore-*' -exec rm -rf {} +
    find "$aside" -mindepth 1 -maxdepth 1 -exec mv -t "$APPDATA_DIR" {} +
    exit 1
  fi
  echo "files restored from $(basename "$files"); the previous ones are in $aside"
fi
echo "Start the app again: docker compose start app"
