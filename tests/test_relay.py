"""The desktop joining a lab as a device and working through its relay
(app/desktop_join.py, app/relay.py), against a real server on this computer."""
from __future__ import annotations

import http.client
import logging
import threading
from unittest import mock

from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

# tests.base first: it points the app at a throwaway database before anything
# imports the app. Importing app first would open data/biomanager.db.
from tests.base import AppTestCase, app, execute, make_user, one, uniq  # isort: skip

PASSWORD = "lab bench 42"
logging.getLogger("werkzeug").setLevel(logging.ERROR)       # each request, twice: the relay's and the server's


class LabServer:
    """The app served on a free port, as a lab's server would be."""

    def __enter__(self):
        self.server = make_server("127.0.0.1", 0, app, threaded=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()


def ask(base: str, method: str, path: str, headers: dict | None = None, body: bytes | None = None):
    host = base.split("//", 1)[1]
    conn = http.client.HTTPConnection(host, timeout=15)
    try:
        conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


class Relay(AppTestCase):
    def setUp(self):
        super().setUp()
        from app import desktop_join
        self.addCleanup(desktop_join.forget)
        self.who = make_user(uniq("tech"))
        execute("update users set password_hash=? where username=?", generate_password_hash(PASSWORD), self.who)

    def test_the_desktop_joins_and_its_window_works_on_the_lab_through_the_relay(self):
        from app import desktop_join, devices
        with LabServer() as lab:
            result = desktop_join.join(lab.url, self.who, PASSWORD)
            self.assertTrue(result["ok"], result)
            self.assertEqual(devices.window_url(), "relay")
            self.assertEqual(one("select kind from lab_devices where public_id=?", result["device"]), "app")
            base = desktop_join.start_relay()
            self.assertTrue(base.startswith("http://127.0.0.1:"))
            status, _, page = ask(base, "GET", "/home", {"Accept": "text/html"})
            self.assertEqual(status, 200)
            self.assertIn(self.who, page)                      # signed in as its person, by the device's token
            # A change from the window's own pages goes through; from another site it doesn't.
            cage = uniq("C")
            form = f"cage_id={cage}".encode()
            own = {"Content-Type": "application/x-www-form-urlencoded", "Origin": base}
            status, headers, _ = ask(base, "POST", "/colony/cages/create", own, form)
            self.assertIn(status, (200, 302, 303))
            self.assertEqual(one("select owner from mouse_cages where cage_id=?", cage), self.who)
            if "Location" in headers:
                self.assertFalse(headers["Location"].startswith(lab.url))   # back at the relay, never the server
            status, _, _ = ask(base, "POST", "/colony/cages/create",
                               {**own, "Origin": "https://elsewhere.example"}, f"cage_id={uniq('C')}".encode())
            self.assertEqual(status, 403)

    def test_only_this_computer_s_window_is_served(self):
        from app import desktop_join
        with LabServer() as lab:
            desktop_join.join(lab.url, self.who, PASSWORD)
            base = desktop_join.start_relay()
            port = base.rsplit(":", 1)[1]
            status, _, _ = ask(base, "GET", "/home", {"Host": f"attacker.example:{port}"})
            self.assertEqual(status, 421)

    def test_sign_out_signs_the_computer_out_of_the_lab(self):
        from app import desktop_join, devices
        with LabServer() as lab:
            joined = desktop_join.join(lab.url, self.who, PASSWORD)
            base = desktop_join.start_relay()
            status, headers, _ = ask(base, "GET", "/logout")
            self.assertEqual((status, headers["Location"]), (303, "/_relay/leave"))
            status, _, page = ask(base, "GET", "/_relay/leave", {"Accept": "text/html"})
            self.assertIn("Sign this computer out of the lab?", page)
            with mock.patch.dict("sys.modules", {"desktop_menu": mock.Mock(_state={"local_url": "http://127.0.0.1:1/"})}):
                status, headers, _ = ask(base, "POST", "/_relay/leave", {"Sec-Fetch-Site": "same-origin"})
            self.assertEqual((status, headers["Location"]), (303, "http://127.0.0.1:1/"))
            self.assertIsNotNone(one("select revoked_at from lab_devices where public_id=?", joined["device"]))
            self.assertIsNone(desktop_join.joined())
            self.assertEqual(devices.window_url(), "")

    def test_a_server_out_of_reach_says_so(self):
        from app import desktop_join
        with LabServer() as lab:
            desktop_join.join(lab.url, self.who, PASSWORD)
        base = desktop_join.start_relay()                     # the server has gone
        status, _, page = ask(base, "GET", "/home", {"Accept": "text/html"})
        self.assertEqual(status, 503)
        self.assertIn("The lab's server can't be reached", page)
        status, _, body = ask(base, "GET", "/_relay/status")
        self.assertEqual((status, body), (200, '{"online": false}'))

    def test_a_wrong_password_joins_nothing(self):
        from app import desktop_join
        with LabServer() as lab:
            result = desktop_join.join(lab.url, self.who, "nope")
        self.assertFalse(result["ok"])
        self.assertIsNone(desktop_join.joined())


class OpenYourLab(AppTestCase):
    """Open your lab joins the lab; the window then opens the relay."""

    def setUp(self):
        super().setUp()
        from app import desktop_join
        self.addCleanup(desktop_join.forget)

    def test_joining_from_open_your_lab_opens_the_relay(self):
        from app import desktop_join, door
        who = make_user(uniq("tech"))
        execute("update users set password_hash=? where username=?", generate_password_hash(PASSWORD), who)
        with LabServer() as lab, mock.patch("app.devices.on_this_computer", return_value=True):
            c = app.test_client()
            found = {"url": lab.url, "name": "Rivera Lab", "host": lab.url.split("//")[1]}
            with mock.patch.object(door, "find_lab", return_value=found):
                html = c.get("/open-lab?address=" + found["host"]).get_data(as_text=True)
            self.assertIn("Join the lab", html)
            html = c.post("/open-lab", data={"action": "join", "username": who, "password": PASSWORD}).get_data(as_text=True)
            relay = desktop_join.start_relay()
            self.assertIn(relay, html)                         # the window goes to the relay, not the server
            self.assertNotIn(lab.url + "/", html)
