"""Devices that join the lab, each signed in on its own (app/lab_devices.py)."""
from __future__ import annotations

from werkzeug.security import generate_password_hash

# tests.base first: it points the app at a throwaway database before anything
# imports the app. Importing app first would open data/biomanager.db.
from tests.base import AppTestCase, app, client_for, execute, make_user, one, rows, uniq  # isort: skip

PASSWORD = "lab bench 42"


def with_password(username: str) -> str:
    execute("update users set password_hash=? where username=?", generate_password_hash(PASSWORD), username)
    return username


class Joining(AppTestCase):
    def join(self, username, password=PASSWORD, **extra):
        c = app.test_client()
        return c.post("/api/devices/join", json={"username": username, "password": password,
                                                  "name": "Lab iMac", "platform": "mac", "app_version": "1.6.0", **extra})

    def test_an_app_joins_with_a_password_and_its_token_signs_it_in(self):
        who = with_password(make_user(uniq("tech")))
        r = self.join(who)
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertTrue(body["token"].startswith("bmd_"))
        self.assertEqual((body["user"]["username"], body["name"]), (who, "Lab iMac"))
        self.assertTrue(body["recipient"].startswith("age1"))
        self.assertNotIn("lab_key", body)                    # a member's device doesn't hold the lab's key
        page = app.test_client().get("/home", headers={"Authorization": f"Bearer {body['token']}"})
        self.assertEqual(page.status_code, 200)
        self.assertIn(who, page.get_data(as_text=True))
        self.assertEqual(one("select platform from lab_devices where public_id=?", body["device"]), "mac")

    def test_an_admin_s_device_gets_the_lab_s_key(self):
        from app import lab_key
        from app.db import SessionLocal
        boss = with_password(make_user(uniq("pi"), role="admin"))
        body = self.join(boss).get_json()
        with SessionLocal() as s:
            self.assertEqual(body["lab_key"], lab_key.current(s).secret)

    def test_a_wrong_password_or_a_guest_pass_is_refused(self):
        who = with_password(make_user(uniq("tech")))
        self.assertEqual(self.join(who, password="nope").status_code, 403)
        self.assertEqual(self.join(uniq("nobody")).status_code, 403)
        guest = with_password(make_user(uniq("guest")))
        execute("update users set expires_at='2999-01-01 00:00:00' where username=?", guest)
        r = self.join(guest)
        self.assertEqual(r.status_code, 403)
        self.assertIn("guest pass", r.get_json()["error"])

    def test_a_device_token_changes_records_without_the_cross_site_check(self):
        who = with_password(make_user(uniq("tech")))
        token = self.join(who).get_json()["token"]
        c = app.test_client()
        r = c.post("/colony/cages/create", data={"cage_id": uniq("C")}, headers={"Authorization": f"Bearer {token}",
                                                                              "Origin": "http://127.0.0.1:5999"})
        self.assertIn(r.status_code, (200, 302))
        self.assertEqual(one("select owner from mouse_cages order by id desc limit 1"), who)


class Pairing(AppTestCase):
    def test_a_code_approved_by_someone_signed_in(self):
        c = app.test_client()
        start = c.post("/api/devices/pair", json={"name": "Bench iPhone", "platform": "ios"}).get_json()
        code, secret = start["code"], start["secret"]
        self.assertRegex(code, r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")
        asking = {"Authorization": f"Pair {secret}"}
        self.assertEqual(c.get("/api/devices/pair", headers=asking).get_json()["status"], "waiting")
        r = self.post(self.m, "/settings/devices/approve", {"code": code.lower()})
        self.assertFlash(r, "Bench iPhone has joined the lab", "success")
        done = c.get("/api/devices/pair", headers=asking).get_json()
        self.assertEqual((done["status"], done["user"]["username"]), ("approved", self.member))
        self.assertEqual(c.get("/home", headers={"Authorization": f"Bearer {done['token']}"}).status_code, 200)
        self.assertEqual(c.get("/api/devices/pair", headers=asking).status_code, 404)    # handed over once

    def test_a_wrong_code_is_refused(self):
        self.assertFlash(self.post(self.m, "/settings/devices/approve", {"code": "ZZZZ-ZZZZ"}), "No device is waiting", "error")


class TheList(AppTestCase):
    def test_a_browser_sign_in_is_a_device_and_can_be_signed_out_from_another(self):
        who = with_password(make_user(uniq("tech")))
        laptop, desk = app.test_client(), app.test_client()
        for c in (laptop, desk):
            c.post("/login", data={"username": who, "password": PASSWORD},
                   headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15"})
        self.assertEqual(laptop.get("/home").status_code, 200)
        page = desk.get("/settings/devices").get_data(as_text=True)
        self.assertIn("Safari on a Mac", page)
        self.assertIn("this device", page)
        ids = [r for (r,) in rows(
            "select public_id from lab_devices where kind='browser' and user_id_fk=(select id from users where username=?) "
            "order by id", who)]
        self.assertEqual(len(ids), 2)
        desk.post(f"/settings/devices/device/{ids[0]}/sign-out")
        self.assertNotEqual(laptop.get("/home").status_code, 200)     # signed out there
        self.assertEqual(desk.get("/home").status_code, 200)

    def test_renaming_and_signing_out_an_app(self):
        who = with_password(make_user(uniq("tech")))
        body = app.test_client().post("/api/devices/join", json={"username": who, "password": PASSWORD,
                                                                  "name": "iMac", "platform": "mac"}).get_json()
        me = client_for(who)
        me.post(f"/settings/devices/device/{body['device']}/rename", data={"name": "Bench iMac"})
        self.assertIn('value="Bench iMac"', me.get("/settings/devices").get_data(as_text=True))
        me.post(f"/settings/devices/device/{body['device']}/sign-out")
        token = {"Authorization": f"Bearer {body['token']}"}
        self.assertNotEqual(app.test_client().get("/home", headers=token).status_code, 200)

    def test_someone_else_s_device_is_theirs_unless_you_are_an_admin(self):
        who = with_password(make_user(uniq("tech")))
        body = app.test_client().post("/api/devices/join", json={"username": who, "password": PASSWORD}).get_json()
        self.assertEqual(self.m.post(f"/settings/devices/device/{body['device']}/sign-out").status_code, 403)
        self.assertIn(body["device"], self.get_ok(self.a, "/settings/devices"))


class Copies(AppTestCase):
    def test_a_joined_admin_device_takes_its_copy_with_its_token(self):
        boss = with_password(make_user(uniq("pi"), role="admin"))
        body = app.test_client().post("/api/devices/join", json={"username": boss, "password": PASSWORD}).get_json()
        auth = {"Authorization": f"Bearer {body['token']}"}
        c = app.test_client()
        r = c.get("/api/lab-copy/snapshot", headers=auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["X-BioManager-Lab-Recipient"], body["recipient"])
        self.assertEqual(c.get("/api/lab-copy/snapshot", headers=auth).status_code, 429)   # one every two minutes
        self.assertIsNotNone(one("select last_copy_at from lab_devices where public_id=?", body["device"]))
        self.assertEqual(c.get("/api/lab-copy/files", headers=auth).status_code, 200)


class ThePhoneApp(AppTestCase):
    def test_the_app_signed_in_through_its_page_gets_a_token_of_its_own(self):
        app_agent = {"User-Agent": "Mozilla/5.0 (iPhone) AppleWebKit BioManagerIOS/0.2.0"}
        r = self.m.post("/api/devices/this-app", json={"name": "Bench iPhone", "platform": "ios"}, headers=app_agent)
        self.assertEqual(r.status_code, 200, r.get_json())
        first = r.get_json()
        self.assertTrue(first["token"].startswith("bmd_"))
        self.assertNotIn("lab_key", first)
        token = {"Authorization": f"Bearer {first['token']}"}
        self.assertEqual(app.test_client().get("/api/sync/snapshot", headers=token).status_code, 200)
        # Lost its token: the one it was is signed out.
        again = self.m.post("/api/devices/this-app", json={"name": "Bench iPhone", "platform": "ios",
                                                           "replaces": first["device"]}, headers=app_agent).get_json()
        self.assertIsNotNone(one("select revoked_at from lab_devices where public_id=?", first["device"]))
        self.assertNotEqual(app.test_client().get("/api/sync/snapshot", headers=token).status_code, 200)
        self.assertTrue(again["token"].startswith("bmd_"))

    def test_only_the_app_s_own_window_asks(self):
        self.assertEqual(self.m.post("/api/devices/this-app", json={}).status_code, 403)
        self.assertEqual(app.test_client().post("/api/devices/this-app", json={},
                                                headers={"User-Agent": "BioManagerIOS/1"}).status_code, 401)
