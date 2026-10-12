"""The desktop app joining a lab as a device, and working on it through its relay.

Open your lab (app/door.py) finds the lab's server, then joins it as one of
its person's devices (app/lab_devices.py): with their username and password,
or with a code someone signed in approves. The desktop keeps what it got in
its preferences (the token encrypted with this computer's own secret), keeps
a daily copy of the lab with that token (app/lab_copy.py, locked with the
lab's key), and opens the lab in its window through its relay (app/relay.py),
never the server's pages themselves.

  joined()          the lab this computer joined, or None
  join(...)         sign in and join; pair_start / pair_poll for a code
  start_relay()     the relay for the joined lab, and its copy for working offline; its address
  leave()           sign this computer out of the lab (the relay's Sign out)
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import devices, security
from .db import SessionLocal
from .i18n import gettext

PREF = "joined_lab"
RELAY_PORT = "relay_port"
# Raised when the window should start afresh at a new relay address: its
# browser cache is per address, and 1.8.3's relay sent each stylesheet with a
# second Content-Type the window refused and may have kept.
RELAY_ADDRESS = "relay_address"
RELAY_GENERATION = 2


def _platform() -> str:
    import sys
    return {"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux")


def computer_name() -> str:
    """This computer's own name, as the device's first name."""
    import platform
    import subprocess
    import sys
    if sys.platform == "darwin":
        try:
            name = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True,
                                  timeout=3).stdout.strip()
            if name:
                return name[:80]
        except (OSError, subprocess.SubprocessError):
            pass
    return (platform.node() or gettext("This computer")).split(".")[0][:80]


def joined() -> dict | None:
    """{"server", "token", "device", "name", "lab", "user", "role"} for the lab
    this computer joined, or None."""
    saved = devices._prefs().get(PREF) or {}
    token = security.decrypt_text(saved.get("token", "")) if saved.get("token") else ""
    if not saved.get("server") or not token:
        return None
    return {**saved, "token": token}


def _remember(server: str, answer: dict) -> dict:
    """Keep what joining answered, and use it: the lab's key (an admin's
    computer), and the daily copy of the lab with the device's token."""
    from . import lab_copy, lab_key
    saved = {"server": server.rstrip("/"), "token": security.encrypt_text(answer["token"]),
             "device": answer.get("device", ""), "name": answer.get("name", ""), "lab": answer.get("lab", ""),
             "user": (answer.get("user") or {}).get("username", ""), "role": (answer.get("user") or {}).get("role", "")}
    devices._save_prefs(**{PREF: saved, "window_url": "relay"})
    with SessionLocal() as s:
        if answer.get("lab_key"):
            # In this computer's keyring: it opens the lab's copies and backups;
            # this computer's own lab keeps locking with its own key.
            lab_key.adopt(s, answer["lab_key"], active=False)
        set_setting = lab_copy._settings()[1]
        set_setting(s, lab_copy.SETTING_SERVER, saved["server"])
        set_setting(s, lab_copy.SETTING_KEY, security.encrypt_text(answer["token"]))
        s.commit()
    return joined()


def _post(url: str, body: dict, headers: dict | None = None, method: str = "POST") -> tuple[int, dict]:
    data = json.dumps(body).encode() if method == "POST" else None
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json",
                                                          "User-Agent": "BioManager desktop", **(headers or {})})
    try:
        with urlopen(req, timeout=30) as r:     # noqa: S310 (the lab's address the person typed)
            return r.status, json.loads(r.read().decode() or "{}")
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode() or "{}")
        except ValueError:
            return error.code, {"ok": False, "error": gettext("The server answered %(status)s. Is it a BioManager of the same version?", status=error.code)}


def _about_this_computer() -> dict:
    return {"name": computer_name(), "platform": _platform(), "app_version": devices.version()}


def join(server: str, username: str, password: str) -> dict:
    """Join the lab at `server` with a username and password. Returns
    {"ok": True, ...joined} or {"ok": False, "error"}."""
    from . import lab_copy
    try:
        status, answer = _post(server.rstrip("/") + "/api/devices/join",
                               {"username": username, "password": password, **_about_this_computer()})
    except (URLError, OSError) as error:
        return {"ok": False, "error": lab_copy._reason(error)}
    if status != 200 or not answer.get("ok"):
        return {"ok": False, "error": answer.get("error") or gettext("The lab's server didn't let this computer join.")}
    return {"ok": True, **_remember(server, answer)}


def pair_start(server: str) -> dict:
    """Ask the server for a code to approve; {"ok", "code", "secret"} or an error."""
    from . import lab_copy
    try:
        status, answer = _post(server.rstrip("/") + "/api/devices/pair", _about_this_computer())
    except (URLError, OSError) as error:
        return {"ok": False, "error": lab_copy._reason(error)}
    if status != 200 or not answer.get("ok"):
        return {"ok": False, "error": answer.get("error") or gettext("The lab's server didn't give a code.")}
    return answer


def pair_poll(server: str, secret: str) -> dict:
    """{"status": "waiting"|"approved"|"expired"}; once approved, the computer has joined."""
    from . import lab_copy
    try:
        status, answer = _post(server.rstrip("/") + "/api/devices/pair", {}, {"Authorization": f"Pair {secret}"}, method="GET")
    except (URLError, OSError) as error:
        return {"status": "error", "error": lab_copy._reason(error)}
    if answer.get("status") == "approved" and answer.get("token"):
        _remember(server, answer)
    return answer


def start_relay() -> str:
    """The relay for the joined lab, serving this window; its address ("" if none joined)."""
    from . import relay
    lab = joined()
    if lab is None:
        return ""
    if relay.address() and relay._running.get("relay") and relay._running["relay"].server == lab["server"]:
        return relay.address()
    from . import offline_store
    token = lambda: (joined() or {}).get("token", "")      # noqa: E731
    # This computer's copy of the facility, for the offline screens (app/offline_store.py).
    store = offline_store.Store(lab["server"], token, version=devices.version())
    offline_store.start_background(store)
    instance = relay.Relay(lab["server"], token=token, version=devices.version(), on_leave=_left, store=store)
    prefs = devices._prefs()
    same = prefs.get(RELAY_ADDRESS) == RELAY_GENERATION
    base = relay.start(instance, int(prefs.get(RELAY_PORT) or 0) if same else 0)
    devices._save_prefs(**{RELAY_PORT: int(base.rsplit(":", 1)[-1]), RELAY_ADDRESS: RELAY_GENERATION})
    return base


def _left() -> str:
    """After the relay's Sign out: forget the lab; the window opens this computer's own."""
    forget()
    try:
        import desktop_menu
        return desktop_menu._state.get("local_url") or "/"
    except ImportError:
        return "/"


def forget() -> None:
    from . import lab_copy, offline_store, relay
    lab = joined()
    if lab is not None:
        offline_store.Store(lab["server"], lambda: "").forget()
    offline_store.stop_background()
    devices._save_prefs(**{PREF: {}, "window_url": ""})
    with SessionLocal() as s:
        set_setting = lab_copy._settings()[1]
        set_setting(s, lab_copy.SETTING_KEY, "")
        s.commit()
    relay.stop()
