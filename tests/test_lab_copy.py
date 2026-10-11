"""Copies of the lab on every computer (app/lab_copy.py): the keys, the
snapshot the server hands out, and the desktop app keeping copies."""
from __future__ import annotations

import io
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

from tests.base import AppTestCase, app, client_for, execute, flash_text, location, make_user, one, uniq, user_id

INTERNET = {"X-BioManager-Entry": "internet"}


def set_permission(on: bool) -> None:
    from app import lab
    from app.db import SessionLocal
    with SessionLocal() as s:
        lab._set_flag(s, "members_keep_copies", on)
        s.commit()


class CopyCase(AppTestCase):

    def setUp(self):
        super().setUp()
        from app import lab_copy
        lab_copy.key_throttle.reset()
        set_permission(False)
        self.addCleanup(set_permission, False)

    def make_key(self, client=None, label=None) -> str:
        r = (client or self.a).post("/settings/lab-copies", data={"label": label or uniq("Computer ")})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        return re.search(r'id="lab-copy-key"[^>]*>(bmk_[a-z0-9]+)<', r.get_data(as_text=True)).group(1)

    def api(self, path, key, headers=None):
        return app.test_client().get(path, headers={"Authorization": f"Bearer {key}", **(headers or {})})

    def fresh(self, key):
        """Let this key take another snapshot straight away."""
        from app.lab_copy import key_hash
        execute("update lab_copy_keys set last_used_at=NULL where key_hash=?", key_hash(key))


# ======================================================================= keys

class KeyTests(CopyCase):

    def test_an_admin_makes_a_key_shown_once_and_kept_only_as_a_hash(self):
        label = uniq("Lab iMac ")
        key = self.make_key(label=label)
        self.assertTrue(key.startswith("bmk_") and len(key) == 36)
        stored = one("select key_hash from lab_copy_keys where label=?", label)
        self.assertNotIn(key, stored)
        self.assertNotIn(key, self.get_ok(self.a, "/settings"))
        self.assertIn(label, self.get_ok(self.a, "/settings"))

    def test_members_need_lab_setup_to_allow_it(self):
        member = client_for(make_user(uniq("member")))
        self.assertEqual(member.post("/settings/lab-copies", data={"label": "Laptop"}).status_code, 403)
        self.assertNotIn("Copies of the lab on your computers", self.get_ok(member, "/settings"))
        set_permission(True)
        key = self.make_key(self.m)
        self.assertEqual(self.api("/api/lab-copy/files", key).status_code, 200)
        set_permission(False)
        self.assertEqual(self.api("/api/lab-copy/files", key).status_code, 403)

    def test_a_key_needs_a_computer_name(self):
        r = self.post(self.a, "/settings/lab-copies", data={"label": " "})
        self.assertIn("Say which computer", flash_text(r))

    def test_admins_see_every_computer_members_only_their_own(self):
        set_permission(True)
        mine = uniq("Member laptop ")
        self.make_key(self.m, mine)
        theirs = uniq("Admin desktop ")
        self.make_key(self.a, theirs)
        admin_page, member_page = self.get_ok(self.a, "/settings"), self.get_ok(self.m, "/settings")
        self.assertIn(mine, admin_page)
        self.assertIn(theirs, admin_page)
        self.assertIn(mine, member_page)
        self.assertNotIn(theirs, member_page)

    def test_a_revoked_key_stops_working(self):
        label = uniq("Old PC ")
        key = self.make_key(label=label)
        kid = one("select id from lab_copy_keys where label=?", label)
        self.post(self.a, f"/settings/lab-copies/{kid}/revoke")
        r = self.api("/api/lab-copy/snapshot", key)
        self.assertEqual(r.status_code, 401)
        self.assertIn("revoked", r.get_json()["error"])

    def test_someone_else_cannot_revoke_a_key(self):
        label = uniq("Admin box ")
        self.make_key(label=label)
        kid = one("select id from lab_copy_keys where label=?", label)
        self.assertEqual(self.m.post(f"/settings/lab-copies/{kid}/revoke").status_code, 404)

    def test_disabling_an_account_revokes_its_keys_for_good(self):
        admin2 = make_user(uniq("admin"), role="admin")
        key = self.make_key(client_for(admin2))
        self.post(self.a, f"/admin/users/{user_id(admin2)}/disable")
        self.post(self.a, f"/admin/users/{user_id(admin2)}/disable")      # enabled again
        self.assertEqual(self.api("/api/lab-copy/files", key).status_code, 401)

    def test_a_disabled_account_s_keys_stop_working(self):
        admin2 = make_user(uniq("admin"), role="admin")
        key = self.make_key(client_for(admin2))
        execute("update users set disabled=? where username=?", True, admin2)
        self.assertEqual(self.api("/api/lab-copy/files", key).status_code, 401)


# ======================================================================= the snapshot

class SnapshotTests(CopyCase):

    def test_no_key_or_a_wrong_key_gets_nothing(self):
        self.assertEqual(app.test_client().get("/api/lab-copy/snapshot").status_code, 401)
        self.assertEqual(self.api("/api/lab-copy/snapshot", "bmk_" + "x" * 32).status_code, 401)

    def test_the_snapshot_is_the_whole_database_as_a_sqlite_file(self):
        mouse_owner = self.member
        key = self.make_key()
        r = self.api("/api/lab-copy/snapshot", key)
        self.assertEqual(r.status_code, 200)
        data = r.get_data()
        import hashlib
        self.assertEqual(hashlib.sha256(data).hexdigest(), r.headers["X-BioManager-SHA256"])
        rows = json.loads(r.headers["X-BioManager-Rows"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copy.db"
            path.write_bytes(data)
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                users = {u for (u,) in con.execute("select username from users")}
                self.assertIn(self.admin, users)
                self.assertIn(mouse_owner, users)
                self.assertEqual(con.execute("select count(*) from users").fetchone()[0], rows["users"])
                self.assertEqual(con.execute("select count(*) from mice").fetchone()[0], one("select count(*) from mice"))
                self.assertEqual(con.execute("select count(*) from inventory_items").fetchone()[0],
                                 one("select count(*) from inventory_items"))

    def test_stored_secrets_are_blanked(self):
        from app.db import SessionLocal
        from app.models import GoogleCalendarLink
        with SessionLocal() as s:
            s.add(GoogleCalendarLink(owner=self.admin, refresh_token="very-secret-refresh", access_token="also-secret"))
            s.commit()
        r = self.api("/api/lab-copy/snapshot", self.make_key())
        self.assertNotIn(b"very-secret-refresh", r.get_data())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copy.db"
            path.write_bytes(r.get_data())
            e = create_engine(f"sqlite:///{path}")
            with e.connect() as c:
                tokens = c.execute(text("select refresh_token, access_token from google_calendar_links")).all()
            e.dispose()
        self.assertTrue(tokens)
        from app.security import decrypt_text
        self.assertTrue(all((decrypt_text(a) or "") == "" and (decrypt_text(b) or "") == "" for a, b in tokens))

    def test_one_snapshot_every_few_minutes_per_key(self):
        key = self.make_key()
        self.assertEqual(self.api("/api/lab-copy/snapshot", key).status_code, 200)
        self.assertEqual(self.api("/api/lab-copy/snapshot", key).status_code, 429)
        self.fresh(key)
        self.assertEqual(self.api("/api/lab-copy/snapshot", key).status_code, 200)

    def test_the_server_records_when_each_computer_last_copied(self):
        label = uniq("Freezer PC ")
        key = self.make_key(label=label)
        self.api("/api/lab-copy/snapshot", key)
        self.assertIsNotNone(one("select last_used_at from lab_copy_keys where label=?", label))
        self.assertGreater(one("select last_bytes from lab_copy_keys where label=?", label), 0)

    def test_keys_are_refused_from_the_internet(self):
        r = self.api("/api/lab-copy/snapshot", self.make_key(), headers=INTERNET)
        self.assertEqual((r.status_code, location(r)), (302, "/guest"))

    def test_uploaded_files_are_listed_and_served_but_nothing_outside_them(self):
        from app.paths import uploads_dir
        name = f"{uniq('copytest')}.txt"
        (uploads_dir() / name).write_text("gel image")
        self.addCleanup((uploads_dir() / name).unlink)
        key = self.make_key()
        listing = self.api("/api/lab-copy/files", key).get_json()["files"]
        self.assertIn({"path": name, "size": 9}, listing)
        self.assertEqual(self.api(f"/api/lab-copy/files/{name}", key).get_data(as_text=True), "gel image")
        self.assertEqual(self.api("/api/lab-copy/files/../../app.py", key).status_code, 404)

    def test_wrong_keys_are_throttled_but_the_lab_s_own_keys_still_work(self):
        from app import lab_copy
        for _ in range(lab_copy.key_throttle.limit):
            self.api("/api/lab-copy/files", "bmk_" + "y" * 32)
        self.assertEqual(self.api("/api/lab-copy/files", "bmk_" + "z" * 32).status_code, 429)
        self.assertEqual(self.api("/api/lab-copy/files", self.make_key()).status_code, 200)

    def test_a_guest_may_not_keep_a_copy(self):
        set_permission(True)
        guest = make_user(uniq("guest"))
        execute("update users set expires_at=? where username=?", datetime.utcnow() + timedelta(days=3), guest)
        self.assertEqual(client_for(guest).post("/settings/lab-copies", data={"label": "Laptop"}).status_code, 403)
        member = make_user(uniq("member"))
        key = self.make_key(client_for(member))
        execute("update users set expires_at=? where username=?", datetime.utcnow() + timedelta(days=3), member)
        self.assertEqual(self.api("/api/lab-copy/snapshot", key).status_code, 403)


# ======================================================================= a member's copy

class MemberCopyTests(CopyCase):
    """An admin's copy is the whole lab; a member's holds what they can see."""

    def setUp(self):
        super().setUp()
        set_permission(True)
        from app.db import SessionLocal
        from app.models import (ApiToken, Feedback, InventoryItem, InventoryModule, NotebookPage, NotebookShare,
                                NotebookTab, NotebookVersion, NotificationRecord)
        from app.paths import uploads_dir
        self.secret_file, self.shared_file = f"{uniq('private')}.png", f"{uniq('shared')}.png"
        for name in (self.secret_file, self.shared_file):
            (uploads_dir() / name).write_text("image")
            self.addCleanup((uploads_dir() / name).unlink)
        self.member_name = make_user(uniq("member"))
        self.words = {w: uniq(w) for w in ("private", "shared", "own", "personal", "feedback", "note", "batch", "oldkey",
                                           "todo-own", "todo-lab", "todo-theirs", "todo-group", "todo-other-group",
                                           "event-theirs", "event-lab")}
        with SessionLocal() as s:
            tab = NotebookTab(owner_username=self.admin, title=uniq("Admin topic "))
            mine = NotebookTab(owner_username=self.member_name, title=uniq("Member topic "))
            s.add_all([tab, mine])
            s.flush()
            private = NotebookPage(tab_id_fk=tab.id, title=self.words["private"],
                                   body=f'<img src="/static/uploads/{self.secret_file}">')
            shared = NotebookPage(tab_id_fk=tab.id, title=self.words["shared"],
                                  body=f'<img src="/static/uploads/{self.shared_file}">')
            own = NotebookPage(tab_id_fk=mine.id, title=self.words["own"])
            s.add_all([private, shared, own])
            s.flush()
            s.add(NotebookVersion(page_id_fk=private.id, title=self.words["private"], body="old"))
            s.add(NotebookShare(page_id_fk=shared.id, username="*", role="view"))
            module = InventoryModule(key=uniq("admin-personal-"), label="Admin's", private_to=self.admin)
            s.add(module)
            s.flush()
            s.add(InventoryItem(module_id_fk=module.id, name=self.words["personal"]))
            from app.models import BatchRecord, DatabaseAlias
            s.add(BatchRecord(description=f"add primer pair {self.words['batch']}", actor=self.admin))
            s.add(DatabaseAlias(kind="inventory", old_key=self.words["oldkey"], module_id=module.id))
            s.add(Feedback(username=self.admin, text=self.words["feedback"]))
            s.add(NotificationRecord(recipient_username=self.admin, title=self.words["note"]))
            s.add(ApiToken(user_id_fk=user_id(self.admin), label="script", token_hash=uniq("hash")))
            # To-dos and events: someone else's personal ones are theirs alone.
            from datetime import date
            from app.models import CalendarEvent, LabGroup, LabGroupMember, NotebookEntry, TaskItem
            in_it, not_in = LabGroup(name=uniq("Group ")), LabGroup(name=uniq("Group "))
            s.add_all([in_it, not_in])
            s.flush()
            s.add(LabGroupMember(group_id_fk=in_it.id, username=self.member_name))
            s.add_all([TaskItem(title=self.words["todo-own"], owner=self.member_name),
                       TaskItem(title=self.words["todo-lab"], owner=self.admin, is_shared=True),
                       TaskItem(title=self.words["todo-theirs"], owner=self.admin, is_shared=False),
                       TaskItem(title=self.words["todo-group"], owner=self.admin, is_shared=True, share_group_id=in_it.id),
                       TaskItem(title=self.words["todo-other-group"], owner=self.admin, is_shared=True,
                                share_group_id=not_in.id)])
            theirs = CalendarEvent(title=self.words["event-theirs"], event_date=date.today(), owner=self.admin,
                                   is_shared=False)
            s.add_all([theirs, CalendarEvent(title=self.words["event-lab"], event_date=date.today(), owner=self.admin)])
            s.flush()
            s.add(NotebookEntry(title=uniq("entry "), event_id_fk=theirs.id))
            s.commit()
        self.key = self.make_key(client_for(self.member_name))

    def copy(self, key):
        r = self.api("/api/lab-copy/snapshot", key)
        self.assertEqual(r.status_code, 200)
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp)
        path = Path(tmp) / "copy.db"
        path.write_bytes(r.get_data())
        return sqlite3.connect(path)

    def test_a_member_s_copy_holds_what_they_see(self):
        with self.copy(self.key) as con:
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            titles = {t for (t,) in con.execute("select title from notebook_pages")}
            self.assertIn(self.words["own"], titles)
            self.assertIn(self.words["shared"], titles)
            self.assertNotIn(self.words["private"], titles)
            self.assertNotIn(self.words["private"], {t for (t,) in con.execute("select title from notebook_versions")})
            self.assertEqual({h for (h,) in con.execute("select password_hash from users")}, {""})
            for table in ("api_tokens", "lab_copy_keys", "guest_passes", "user_identities", "feedback", "audit_log"):
                self.assertEqual(con.execute(f"select count(*) from {table}").fetchone()[0], 0, table)
            self.assertNotIn(self.words["personal"], {n for (n,) in con.execute("select name from inventory_items")})
            self.assertNotIn(self.words["note"], {t for (t,) in con.execute("select title from notifications")})
            # Someone else's Batch history, and old addresses of their personal databases.
            self.assertFalse(any(self.words["batch"] in d for (d,) in con.execute("select description from batches")))
            self.assertNotIn(self.words["oldkey"], {k for (k,) in con.execute("select old_key from database_aliases")})
            self.assertEqual(con.execute("select count(*) from mice").fetchone()[0], one("select count(*) from mice"))
            todos = {t for (t,) in con.execute("select title from tasks")}
            self.assertTrue({self.words["todo-own"], self.words["todo-lab"], self.words["todo-group"]} <= todos)
            self.assertNotIn(self.words["todo-theirs"], todos)
            self.assertNotIn(self.words["todo-other-group"], todos)
            events = {t for (t,) in con.execute("select title from calendar_events")}
            self.assertIn(self.words["event-lab"], events)
            self.assertNotIn(self.words["event-theirs"], events)

    def test_an_admin_s_copy_is_the_whole_lab(self):
        with self.copy(self.make_key()) as con:
            titles = {t for (t,) in con.execute("select title from notebook_pages")}
            self.assertTrue({self.words["private"], self.words["shared"], self.words["own"]} <= titles)
            self.assertIn(self.words["feedback"], {t for (t,) in con.execute("select text from feedback")})
            self.assertEqual(con.execute("select count(*) from users where password_hash=''").fetchone()[0], 0)

    def test_a_member_gets_only_the_files_their_copy_names(self):
        listing = {f["path"] for f in self.api("/api/lab-copy/files", self.key).get_json()["files"]}
        self.assertIn(self.shared_file, listing)
        self.assertNotIn(self.secret_file, listing)
        self.assertEqual(self.api(f"/api/lab-copy/files/{self.shared_file}", self.key).status_code, 200)
        self.assertEqual(self.api(f"/api/lab-copy/files/{self.secret_file}", self.key).status_code, 404)
        admin = {f["path"] for f in self.api("/api/lab-copy/files", self.make_key()).get_json()["files"]}
        self.assertIn(self.secret_file, admin)

    def test_every_table_of_someone_s_own_rows_is_decided_for_a_member_s_copy(self):
        from app import lab_copy
        from app.db import Base
        decided = (set(lab_copy.ADMIN_ONLY) | set(lab_copy.OWN_ROWS) | set(lab_copy.PAGE_ROWS)
                   | set(lab_copy.PERSONAL_DATABASES) | set(lab_copy.MEMBER_SEES_WHOLE) | set(lab_copy.OWN_OR_SHARED))
        personal = {"user_id_fk", "recipient_username", "owner_username", "private_to", "password_hash", "page_id_fk"}
        for table in Base.metadata.sorted_tables:
            names = {c.name for c in table.columns}
            in_personal_db = any(fk.parent.name == "module_id_fk" and fk.column.table.name in lab_copy.PERSONAL_DATABASES
                                 for fk in table.foreign_keys)
            secret = any(isinstance(c.type, __import__("app.models").models.EncryptedText) for c in table.columns)
            # An owner whose row can be personal (not shared) is someone's own too.
            own_unless_shared = {"owner", "is_shared"} <= names and table.name not in lab_copy.EDIT_SHARED_ONLY
            if (names & personal or secret or own_unless_shared) and not in_personal_db:
                self.assertIn(table.name, decided, f"{table.name}: decide what a member's copy keeps (app/lab_copy.py)")


# ======================================================================= the desktop app

class _Response:
    def __init__(self, r):
        self._body = io.BytesIO(r.get_data())
        self.headers = r.headers

    def read(self, *a):
        return self._body.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_open(url, key, timeout=300, tamper=None):
    """The desktop app's request, answered by this test's server."""
    r = app.test_client().get(urlsplit(url).path, headers={"Authorization": f"Bearer {key}"})
    if r.status_code >= 400:
        raise HTTPError(url, r.status_code, "refused", r.headers, io.BytesIO(r.get_data()))
    resp = _Response(r)
    if tamper and urlsplit(url).path.endswith("/snapshot"):
        tamper(resp)
    return resp


class DesktopTests(CopyCase):

    def setUp(self):
        super().setUp()
        app.config["LOCAL_SETUP"] = True
        self.addCleanup(app.config.pop, "LOCAL_SETUP", None)
        execute("delete from app_settings where key like 'lab_copy_%'")
        self.server = f"https://{uniq('lab')}.example.ts.net"
        self.key = self.make_key()
        # Settings as the desktop app's own form saves them.
        with mock.patch("app.lab_copy.threading.Thread"):
            self.post(self.a, "/lab-copy/configure", data={"server": self.server, "key": self.key, "keep": "3"})

    def pull(self, tamper=None):
        from app import lab_copy
        with mock.patch.object(lab_copy, "_open", lambda url, key, timeout=300: fake_open(url, key, timeout, tamper)):
            with app.app_context():
                return lab_copy.pull()

    def folder(self) -> Path:
        from app import lab_copy
        return lab_copy.copies_dir(self.server)

    def test_a_copy_arrives_checked_with_its_uploaded_files(self):
        from app.paths import uploads_dir
        name = f"{uniq('mirror')}.txt"
        (uploads_dir() / name).write_text("plasmid map")
        self.addCleanup((uploads_dir() / name).unlink)
        result = self.pull()
        self.assertTrue(result["ok"], result)
        from app import lab_copy, lab_key
        from app.db import SessionLocal
        [db] = list((self.folder() / "db").glob("biomanager-*.db.age"))
        # Kept locked with the lab's key: a leaked copy is unreadable.
        self.assertTrue(lab_key.is_locked(db))
        self.assertEqual(list((self.folder() / "db").glob("biomanager-*.db")), [])
        self.assertTrue(lab_key.is_locked(self.folder() / "uploads" / (name + ".age")))
        self.assertFalse((self.folder() / "uploads" / name).exists())
        with SessionLocal() as s:
            keys = lab_key.identities(s)
        with tempfile.TemporaryDirectory() as tmp:
            opened = lab_copy.open_copy(db, Path(tmp) / "copy.db", keys)
            with sqlite3.connect(opened) as con:
                self.assertIn(self.admin, {u for (u,) in con.execute("select username from users")})
            files = lab_copy.open_uploads(self.server, Path(tmp) / "uploads", keys)
            self.assertEqual((files / name).read_text(), "plasmid map")
        info = json.loads(lab_copy._sidecar(db).read_text())
        self.assertEqual(info["server"], self.server)
        self.assertTrue(info["locked"])
        # A second copy doesn't fetch the unchanged file again.
        self.fresh(self.key)
        self.assertEqual(self.pull()["files_fetched"], 0)
        page = self.get_ok(self.a, "/settings")
        self.assertIn("Last copy:", page)
        self.assertIn(db.name, page)

    def test_only_the_newest_copies_are_kept(self):
        from app import lab_copy
        taken = iter(["20260101-000000", "20260102-000000", "20260103-000000", "20260104-000000"])

        def stamp(resp):
            resp.headers = {**dict(resp.headers), "X-BioManager-Taken": next(taken)}
        for _ in range(4):
            self.fresh(self.key)
            self.assertTrue(self.pull(tamper=stamp)["ok"])
        names = sorted(p.name for p in (self.folder() / "db").glob("biomanager-*.db.age"))
        self.assertEqual(names, [f"biomanager-2026010{d}-000000Z.db.age" for d in (2, 3, 4)])
        self.assertEqual(len(lab_copy.list_copies(self.server)), 3)

    def test_a_damaged_copy_is_thrown_away(self):
        def corrupt(resp):
            resp.headers = {**dict(resp.headers), "X-BioManager-SHA256": "0" * 64}
        result = self.pull(tamper=corrupt)
        self.assertFalse(result["ok"])
        self.assertIn("damaged", result["error"])
        self.assertEqual(list((self.folder() / "db").glob("*.db")), [])
        self.assertEqual(list(self.folder().glob(".incoming-*")), [])

    def test_a_revoked_key_is_explained(self):
        execute("update lab_copy_keys set revoked_at=CURRENT_TIMESTAMP")
        result = self.pull()
        self.assertFalse(result["ok"])
        self.assertIn("revoked", result["error"])
        self.assertIn("The last copy failed", self.get_ok(self.a, "/settings"))

    def test_the_key_is_stored_encrypted(self):
        stored = one("select value from app_settings where key='lab_copy_key'")
        self.assertNotIn(self.key, stored)

    def test_a_copy_is_due_once_a_day(self):
        from app import lab_copy
        with app.app_context():
            self.assertTrue(lab_copy.due())
            self.pull()
            self.assertFalse(lab_copy.due())

    def test_the_desktop_card_is_only_in_the_desktop_app(self):
        self.assertIn('id="lab-copy"', self.get_ok(self.a, "/settings"))
        app.config.pop("LOCAL_SETUP")
        self.assertNotIn('id="lab-copy"', self.get_ok(self.a, "/settings"))
        self.assertEqual(self.a.post("/lab-copy/now").status_code, 404)


# ======================================================================= a copy rebuilds a server

from tests.base import ON_POSTGRES, POSTGRES_URL  # noqa: E402


@unittest.skipUnless(ON_POSTGRES, "needs a PostgreSQL server (BIOMANAGER_TEST_DATABASE_URL)")
class RestoreFromACopy(CopyCase):
    """A snapshot goes into a new, empty server with migrate-to-postgres,
    as the guide's "Moving from the app to a server" says."""

    def test_a_copy_loads_into_a_fresh_postgres_database(self):
        import os
        import subprocess
        import sys

        import psycopg
        from tests.base import ROOT
        r = self.api("/api/lab-copy/snapshot", self.make_key())
        target = f"biomanager_restore_{uniq('t')}".lower()
        admin_url = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(f'CREATE DATABASE "{target}"')
        target_url = admin_url.rsplit("/", 1)[0] + "/" + target

        def drop():
            with psycopg.connect(admin_url, autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)')
        self.addCleanup(drop)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            copy.write_bytes(r.get_data())
            p = subprocess.run([sys.executable, str(Path(ROOT) / "scripts" / "migrate-to-postgres.py"), str(copy), target_url],
                               cwd=ROOT, capture_output=True, text=True, timeout=300,
                               env={**os.environ, "SECRET_KEY": "k" * 40})
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        with psycopg.connect(target_url) as c:
            restored = c.execute("select count(*) from users").fetchone()[0]
        self.assertEqual(restored, one("select count(*) from users"))


if __name__ == "__main__":
    unittest.main()
