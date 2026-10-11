"""The lab's own key: backups and lab files only this lab can open.

Each lab has a key (an age X25519 identity, https://age-encryption.org),
made the first time it is needed and kept in lab_keys, encrypted with this
device's own secret like every stored token. What leaves the lab as a file
is locked with it:

  Save the whole lab          the .biomanager file (app/lab_transfer.py)
  Move this lab to a server   the same file, sent with the key over HTTPS
  A desktop's copies          each copy of the lab server it keeps (app/lab_copy.py)
  A lab server's backups      the database dump and the files archive
                              (deploy/backup/backup.sh, with the `age` tool and
                              the files written by export_for_backups)

A file locked with it reads as random bytes to anyone without the key. The
devices that hold the key are this lab's own: the server or desktop that
holds the lab, and the desktops of its admins that join it (a member's
device does not: a backup holds what members don't see, such as other
people's private pages). An admin is shown the key once as the recovery key
(Settings → Your data → Lab key), to keep on paper or in a password manager:
with it, a backup can be opened on a new server when every device is lost.

The key travels with the lab: a lab moved or brought to a new server keeps
it, so the files made before still open there. A lab may hold older keys
(lab_keys rows no longer active) that still open the files they locked.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import pyrage
from pyrage import x25519
from sqlalchemy import select

from .i18n import gettext
from .models import LabKey

MAGIC = b"age-encryption.org/v1\n"
RECOVERY_PREFIX = "AGE-SECRET-KEY-1"


class LockedFileError(ValueError):
    """A locked file no key here opens; the message says what to do."""


def key_id(identity: x25519.Identity) -> str:
    return hashlib.sha256(str(identity.to_public()).encode()).hexdigest()[:16]


def parse_recovery(text: str) -> x25519.Identity:
    """A recovery key as a person typed or pasted it: spaces, line breaks and
    case don't matter."""
    cleaned = "".join((text or "").split()).upper()
    if not cleaned.startswith(RECOVERY_PREFIX):
        raise ValueError(gettext("That isn't a lab recovery key: it starts AGE-SECRET-KEY-1."))
    try:
        return x25519.Identity.from_str(cleaned)
    except Exception as error:   # pyrage raises its own IdentityError; a typo breaks the checksum
        raise ValueError(gettext("That recovery key has a mistake in it: check each letter.")) from error


def current(session, create: bool = True) -> LabKey | None:
    """The key new files are locked with; made (and committed) if the lab has none."""
    row = session.scalar(select(LabKey).where(LabKey.active.is_(True), LabKey.secret != "")
                         .order_by(LabKey.created_at.desc(), LabKey.id.desc()))
    if row is not None or not create:
        return row
    identity = x25519.Identity.generate()
    row = LabKey(key_id=key_id(identity), secret=str(identity), active=True)
    session.add(row)
    session.commit()
    return row


def identity(row: LabKey) -> x25519.Identity:
    return x25519.Identity.from_str(row.secret)


def identities(session) -> list[x25519.Identity]:
    """Every key this lab has had, newest first: each opens what it locked."""
    out = []
    for row in session.scalars(select(LabKey).where(LabKey.secret != "").order_by(LabKey.created_at.desc())):
        try:
            out.append(identity(row))
        except Exception:   # a key stored with another device's secret reads as blank or broken
            continue
    return out


def recipient(session) -> str:
    """The public half of the lab's key (age1…): enough to lock, never to open."""
    return str(identity(current(session)).to_public())


def adopt(session, secret: str | x25519.Identity, active: bool = True) -> LabKey:
    """Keep a key this lab came with (a recovery key typed in, or the key a
    desktop sent with the lab it moved here). The newest active key locks
    from now on."""
    ident = secret if isinstance(secret, x25519.Identity) else parse_recovery(secret)
    kid = key_id(ident)
    row = session.scalar(select(LabKey).where(LabKey.key_id == kid))
    if row is None:
        row = LabKey(key_id=kid, secret=str(ident), active=active, created_at=datetime.utcnow())
        session.add(row)
    else:
        row.secret, row.active = str(ident), row.active or active
    if active:
        for other in session.scalars(select(LabKey).where(LabKey.key_id != kid, LabKey.active.is_(True))):
            other.active = False
    session.commit()
    export_if_asked()
    return row


def recovery_key(session, shown_to: str) -> str:
    """The recovery key, for an admin to keep, with who saw it and when."""
    row = current(session)
    row.recovery_shown_at, row.recovery_shown_to = datetime.utcnow(), shown_to
    session.commit()
    return row.secret


def grouped(secret: str) -> str:
    """The recovery key in groups of six, easier to copy onto paper."""
    body = secret[len(RECOVERY_PREFIX):]
    return RECOVERY_PREFIX + " " + " ".join(body[i:i + 6] for i in range(0, len(body), 6))


# ---------------------------------------------------------------- files

def is_locked(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def lock_file(source: Path, target: Path, recipients: list[str]) -> None:
    """Write `source` to `target`, locked so only these keys' owners open it."""
    keys = [x25519.Recipient.from_str(r) for r in recipients]
    partial = target.with_name(target.name + ".partial")
    pyrage.encrypt_file(str(source), str(partial), keys)
    os.replace(partial, target)


def unlock_file(source: Path, target: Path, keys: list[x25519.Identity]) -> None:
    """Write `source`, locked, to `target` as it was; LockedFileError if none of `keys` opens it."""
    if not keys:
        raise LockedFileError(gettext("This file is locked with its lab's key. Enter the lab's recovery key to open it."))
    partial = target.with_name(target.name + ".partial")
    try:
        pyrage.decrypt_file(str(source), str(partial), keys)
    except Exception as error:    # pyrage.DecryptError: no key matches, or the file is damaged
        partial.unlink(missing_ok=True)
        raise LockedFileError(gettext("This file is locked with another lab's key, or it is damaged. Enter the recovery key of the lab it came from.")) from error
    os.replace(partial, target)


def lock_in_place(path: Path, session) -> None:
    """Lock a file this lab just wrote, with the lab's own key."""
    locked = path.with_name(path.name + ".locked")
    lock_file(path, locked, [recipient(session)])
    os.replace(locked, path)


# ---------------------------------------------------------------- a lab server's backups

def export_if_asked() -> None:
    """Write the key files where BIOMANAGER_LABKEY_DIR says (a lab server)."""
    folder = os.environ.get("BIOMANAGER_LABKEY_DIR", "").strip()
    if not folder:
        return
    from .db import SessionLocal
    with SessionLocal() as s:
        export_for_backups(s, Path(folder))


def export_for_backups(session, folder: Path) -> None:
    """A lab server's backup service locks each backup with the age tool:
    `lab.pub` (the public half, to lock) and `lab.key` (to test-restore and to
    restore). The folder is its own volume, never inside a backup
    (deploy/compose.yaml: labkey), so a backup that leaks does not carry its key."""
    folder.mkdir(parents=True, exist_ok=True)
    row = current(session)
    ident = identity(row)
    keys = "\n".join(str(i) for i in identities(session))
    for name, body in (("lab.pub", str(ident.to_public()) + "\n"), ("lab.key", keys + "\n")):
        target = folder / name
        if target.is_file() and target.read_text(encoding="utf-8") == body:
            continue
        partial = folder / (name + ".partial")
        partial.write_text(body, encoding="utf-8")
        os.chmod(partial, 0o600)
        os.replace(partial, target)
