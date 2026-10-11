#!/usr/bin/env bash
# The lab's key, for backups (app/lab_key.py). Sourced by backup.sh,
# restore.sh and restore-test.sh.
#
# The app writes the key into its own volume, mounted here at /labkey (never
# inside a backup): lab.pub, its public half, locks each backup with the
# age tool; lab.key opens them again, for the weekly test restore and for
# restore.sh. On a new server, before the lab is back, give restore.sh the
# lab's recovery key instead:
#   docker compose --profile restore run --rm -e BIOMANAGER_RECOVERY_KEY='AGE-SECRET-KEY-1…' restore …
: "${LABKEY_DIR:=/labkey}"

# Lock $1 with the lab's key, as $1.age, and remove the open file. Prints the
# new name; prints $1 unchanged when there is no key yet (an app that never
# started, or from before the lab's key).
labkey_lock() {
  local file=$1
  if [ ! -s "$LABKEY_DIR/lab.pub" ]; then
    echo "$file"
    return 0
  fi
  age -R "$LABKEY_DIR/lab.pub" -o "$file.age.partial" "$file" && mv "$file.age.partial" "$file.age" && rm -f -- "$file"
  echo "$file.age"
}

# The identities that may open a locked backup: the recovery key given to
# this command, then the lab's own keys.
labkey_identities() {
  local ids
  ids=$(mktemp)
  chmod 600 "$ids"
  if [ -n "${BIOMANAGER_RECOVERY_KEY:-}" ]; then
    echo "$BIOMANAGER_RECOVERY_KEY" | tr -d ' \t' | tr '[:lower:]' '[:upper:]' >> "$ids"
  fi
  if [ -s "$LABKEY_DIR/lab.key" ]; then
    cat "$LABKEY_DIR/lab.key" >> "$ids"
  fi
  echo "$ids"
}

# Open $1 into $2 if it is locked (ends in .age); otherwise $2 is $1 itself.
# Prints the path to read.
labkey_open() {
  local file=$1 target=$2 ids
  case "$file" in
    *.age) ;;
    *) echo "$file"; return 0 ;;
  esac
  ids=$(labkey_identities)
  if [ ! -s "$ids" ]; then
    rm -f -- "$ids"
    echo "$file is locked with the lab's key, and no key is here. Give the lab's recovery key: -e BIOMANAGER_RECOVERY_KEY='AGE-SECRET-KEY-1…'" >&2
    return 1
  fi
  if ! age -d -i "$ids" -o "$target" "$file"; then
    rm -f -- "$ids" "$target"
    echo "$file could not be opened: it is locked with another lab's key, or it is damaged." >&2
    return 1
  fi
  rm -f -- "$ids"
  echo "$target"
}
