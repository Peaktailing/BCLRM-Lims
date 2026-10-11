"""The lab's own key: backups and lab files only the lab can open (app/lab_key.py)."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

# tests.base first: it points the app at a throwaway database before anything
# imports the app. Importing app first would open data/biomanager.db.
from tests.base import ROOT as _ROOT, AppTestCase, execute  # isort: skip

from pyrage import x25519  # noqa: E402

from app import lab_key  # noqa: E402
from app.db import SessionLocal  # noqa: E402

ROOT = Path(_ROOT)


class TheKey(AppTestCase):
    def test_a_file_locked_with_it_opens_only_with_it(self):
        with SessionLocal() as s:
            recipient = lab_key.recipient(s)
            keys = lab_key.identities(s)
        with tempfile.TemporaryDirectory() as tmp:
            plain, locked, back = Path(tmp) / "a.db", Path(tmp) / "a.db.age", Path(tmp) / "b.db"
            plain.write_bytes(b"SQLite format 3\0" + b"mice " * 200)
            lab_key.lock_file(plain, locked, [recipient])
            self.assertTrue(lab_key.is_locked(locked))
            self.assertNotIn(b"mice", locked.read_bytes())
            with self.assertRaises(lab_key.LockedFileError):
                lab_key.unlock_file(locked, back, [x25519.Identity.generate()])
            self.assertFalse(back.exists())
            lab_key.unlock_file(locked, back, keys)
            self.assertEqual(back.read_bytes(), plain.read_bytes())

    def test_a_recovery_key_as_a_person_types_it(self):
        with SessionLocal() as s:
            secret = lab_key.current(s).secret
        grouped = lab_key.grouped(secret)
        self.assertIn(" ", grouped)
        self.assertEqual(str(lab_key.parse_recovery(grouped.lower().replace(" ", "\n  "))), secret)
        with self.assertRaises(ValueError):
            lab_key.parse_recovery("not a key")
        with self.assertRaises(ValueError):          # one letter wrong: the checksum catches it
            lab_key.parse_recovery(secret[:-3] + ("A" if secret[-3] != "A" else "B") + secret[-2:])

    def test_adopting_a_key_keeps_the_old_one_for_what_it_locked(self):
        with SessionLocal() as s:
            before = lab_key.current(s).secret
            arrived = x25519.Identity.generate()
            lab_key.adopt(s, str(arrived))
            self.assertEqual(lab_key.current(s).secret, str(arrived))
            self.assertIn(before, {str(i) for i in lab_key.identities(s)})
            lab_key.adopt(s, before)                  # put the suite's key back
            self.assertEqual(lab_key.current(s).secret, before)

    def test_the_backup_service_gets_the_files_it_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "labkey"
            with SessionLocal() as s:
                lab_key.export_for_backups(s, folder)
                recipient, secret = lab_key.recipient(s), lab_key.current(s).secret
            self.assertEqual((folder / "lab.pub").read_text().strip(), recipient)
            self.assertIn(secret, (folder / "lab.key").read_text())
            for name in ("lab.pub", "lab.key"):
                self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)


class ThePage(AppTestCase):
    def test_settings_shows_the_key_to_admins_only(self):
        self.assertIn('id="lab-key"', self.get_ok(self.a, "/settings"))
        self.assertNotIn('id="lab-key"', self.get_ok(self.m, "/settings"))
        self.assertEqual(self.m.get("/settings/lab-key").status_code, 403)

    def test_the_recovery_key_needs_the_admin_s_password_and_is_noted(self):
        from werkzeug.security import generate_password_hash
        PASSWORD = "correct horse battery"
        execute("update users set password_hash=? where username=?", generate_password_hash(PASSWORD), self.admin)
        from tests.base import client_for
        self.a = client_for(self.admin)          # a session made with the new password
        with SessionLocal() as s:
            secret = lab_key.current(s).secret
        wrong = self.post(self.a, "/settings/lab-key", {"action": "show", "password": "wrong"})
        self.assertNotIn(secret[-12:], wrong.get_data(as_text=True))
        self.assertIn("password isn&#39;t right", wrong.get_data(as_text=True))
        right = self.post(self.a, "/settings/lab-key", {"action": "show", "password": PASSWORD})
        self.assertIn(lab_key.grouped(secret), right.get_data(as_text=True))
        with SessionLocal() as s:
            row = lab_key.current(s)
            self.assertEqual(row.recovery_shown_to, self.admin)
            self.assertIsNotNone(row.recovery_shown_at)

    def test_a_recovery_key_typed_in_comes_back(self):
        with SessionLocal() as s:
            before = lab_key.current(s).secret
        self.assertFlash(self.post(self.a, "/settings/lab-key", {"action": "adopt", "recovery_key": "nonsense"}),
                         "isn't a lab recovery key", "error")
        arrived = x25519.Identity.generate()
        r = self.post(self.a, "/settings/lab-key", {"action": "adopt", "recovery_key": lab_key.grouped(str(arrived))})
        self.assertFlash(r, "The lab's key is back", "success")
        with SessionLocal() as s:
            self.assertEqual(lab_key.current(s).secret, str(arrived))
            lab_key.adopt(s, before)


@unittest.skipUnless(shutil.which("age") and shutil.which("bash"), "needs the age tool (as in the backup image)")
class TheBackupScripts(unittest.TestCase):
    """deploy/backup/labkey.sh with the real age tool: what the app locks the
    script opens, and the other way round."""

    def test_the_script_and_the_app_read_each_other(self):
        ident = x25519.Identity.generate()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "labkey").mkdir()
            (tmp / "labkey" / "lab.pub").write_text(str(ident.to_public()) + "\n")
            (tmp / "labkey" / "lab.key").write_text(str(ident) + "\n")
            (tmp / "dump").write_bytes(b"PGDMP" + os.urandom(1000))
            env = {**os.environ, "LABKEY_DIR": str(tmp / "labkey")}
            script = f'. "{ROOT}/deploy/backup/labkey.sh"; labkey_lock "{tmp}/dump"'
            locked = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(locked, f"{tmp}/dump.age")
            self.assertFalse((tmp / "dump").exists())
            lab_key.unlock_file(Path(locked), tmp / "back", [ident])
            self.assertTrue((tmp / "back").read_bytes().startswith(b"PGDMP"))
            script = f'. "{ROOT}/deploy/backup/labkey.sh"; labkey_open "{locked}" "{tmp}/opened"'
            env.pop("LABKEY_DIR")
            env.update(LABKEY_DIR=str(tmp / "nowhere"), BIOMANAGER_RECOVERY_KEY=lab_key.grouped(str(ident)).lower())
            opened = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(Path(opened).read_bytes(), (tmp / "back").read_bytes())


class TheBackupScriptsAreWired(unittest.TestCase):
    def test_backups_are_locked_and_restores_open_them(self):
        backup = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
        self.assertIn('labkey_lock "$plain_dump"', backup)
        self.assertIn('"$BACKUP_ROOT/db/biomanager-*.dump*"', backup)
        for name in ("restore.sh", "restore-test.sh"):
            self.assertIn("labkey_open", (ROOT / "deploy/backup" / name).read_text(encoding="utf-8"))
        self.assertIn("age", (ROOT / "deploy/backup/Dockerfile").read_text(encoding="utf-8"))
        compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
        self.assertEqual(compose.count("labkey:/labkey"), 3)
        self.assertIn("BIOMANAGER_LABKEY_DIR: /labkey", compose)


class ForTheBackups(unittest.TestCase):
    def test_a_folder_it_cant_write_doesnt_stop_the_server(self):
        import os
        import tempfile
        from unittest import mock
        from app import lab_key
        with tempfile.TemporaryDirectory() as tmp:
            locked = os.path.join(tmp, "labkey")
            os.mkdir(locked, 0o500)
            try:
                with mock.patch.dict(os.environ, {"BIOMANAGER_LABKEY_DIR": locked}), \
                        self.assertLogs("app.lab_key", "ERROR") as said:
                    lab_key.export_if_asked()
            finally:
                os.chmod(locked, 0o700)
            self.assertIn("backups are not locked", said.output[0])
