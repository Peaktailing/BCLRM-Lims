"""Devices people use the lab from, each signed in on its own.

  An app joins    the desktop app, the iPhone or the Android app joins the lab
                  as a device: with its person's username and password
                  (POST /api/devices/join), or, for an account that signs in
                  with Google or Microsoft, with a code someone signed in
                  approves under Settings → Devices & copies
                  (POST /api/devices/pair, then GET it with its secret). It gets
                  a device token (bmd_…, only its hash kept), and every request
                  with that token is its person, on that device: the desktop's
                  relay (app/relay.py) and offline sync (app/sync.py) use it.
  A browser       each sign-in in a browser is a device too (its session id,
                  hashed), so it can be signed out alone.

Settings → Devices & copies lists a person's devices (an admin sees
everyone's): what each is, its version, when and from where it was last
used. Signing one out ends it there and then; renaming an app's device
changes its name everywhere. An admin's app also receives the lab's key
(app/lab_key.py), which opens the lab's backups and copies; a member's
device doesn't.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, request, session, url_for
from sqlalchemy import select

from . import security
from .db import SessionLocal
from .i18n import gettext
from .models import DevicePairing, LabDevice, UserAccount

bp = Blueprint("lab_devices", __name__)

TOKEN_PREFIX = "bmd_"
PAIR_PREFIX = "bmp_"
PAIR_MINUTES = 10
SEEN_EVERY = timedelta(minutes=5)       # last_seen is written at most this often
PLATFORMS = ("mac", "windows", "linux", "ios", "android", "web")
join_throttle = security.LoginThrottle(limit=10, window=15 * 60)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _public_id() -> str:
    return "dev_" + secrets.token_urlsafe(9)


def _clean_name(text: str, fallback: str) -> str:
    name = re.sub(r"\s+", " ", (text or "")).strip()[:80]
    return name or fallback


def describe(user_agent: str) -> tuple[str, str]:
    """(platform, a name like "Safari on a Mac") for a browser's sign-in."""
    ua = user_agent or ""
    if "BioManagerAndroid" in ua:
        return "android", gettext("Android app")
    if "iPhone" in ua or "iPad" in ua:
        platform, where = "ios", gettext("an iPhone") if "iPhone" in ua else gettext("an iPad")
    elif "Android" in ua:
        platform, where = "android", gettext("an Android phone")
    elif "Mac OS X" in ua or "Macintosh" in ua:
        platform, where = "mac", gettext("a Mac")
    elif "Windows" in ua:
        platform, where = "windows", gettext("Windows")
    elif "Linux" in ua:
        platform, where = "linux", gettext("Linux")
    else:
        platform, where = "web", gettext("a computer")
    if "Edg/" in ua:
        browser = "Edge"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = gettext("A browser")
    return platform, gettext("%(browser)s on %(where)s", browser=browser, where=where)


# ---------------------------------------------------------------- signing a request in

def bearer() -> str:
    header = request.headers.get("Authorization", "")
    raw = header[7:].strip() if header[:7].lower() == "bearer " else ""
    return raw if raw.startswith(TOKEN_PREFIX) else ""


def authenticate() -> bool:
    """A request with a device token (app.load_current_user): its person on
    that device, g.user and g.device. False when it carries none."""
    raw = bearer()
    if not raw:
        return False
    g.user, g.device = None, None
    now = datetime.utcnow()
    with SessionLocal() as s:
        device = s.scalar(select(LabDevice).where(LabDevice.token_hash == token_hash(raw)))
        if device is None or device.revoked_at is not None:
            return True
        user = s.get(UserAccount, device.user_id_fk)
        if user is None or user.disabled or (user.expires_at is not None and user.expires_at <= now):
            return True
        if device.last_seen_at is None or now - device.last_seen_at > SEEN_EVERY:
            device.last_seen_at, device.last_ip = now, (request.remote_addr or "")[:64]
            version = request.headers.get("X-BioManager-Version", "")[:40]
            if version:
                device.app_version = version
            s.commit()
        s.expunge(user)
        s.expunge(device)
    g.user, g.device = user, device
    return True


def note_browser(user) -> None:
    """A sign-in in a browser, as a device (security.start_session made its sid)."""
    sid = session.get("sid")
    if not sid:
        return
    platform, name = describe(request.headers.get("User-Agent", ""))
    with SessionLocal() as s:
        if s.scalar(select(LabDevice.id).where(LabDevice.token_hash == token_hash(sid))) is None:
            s.add(LabDevice(public_id=_public_id(), user_id_fk=user.id, name=name, platform=platform, kind="browser",
                            user_agent=request.headers.get("User-Agent", "")[:300], token_hash=token_hash(sid),
                            last_seen_at=datetime.utcnow(), last_ip=(request.remote_addr or "")[:64]))
            s.commit()
    session["dev_seen"] = datetime.utcnow().isoformat(timespec="seconds")


def browser_ok(db, user) -> bool:
    """This browser's sign-in, as its device: False once it was signed out
    from the device list. Notes when it was last used (at most every few
    minutes), and makes the device for a sign-in from before devices."""
    sid = session.get("sid")
    if not sid:
        return True
    device = db.scalar(select(LabDevice).where(LabDevice.token_hash == token_hash(sid)))
    if device is None:
        note_browser(user)
        return True
    if device.revoked_at is not None:
        return False
    seen = session.get("dev_seen", "")
    now = datetime.utcnow()
    if not seen or now - datetime.fromisoformat(seen) > SEEN_EVERY:
        with SessionLocal() as s:
            row = s.get(LabDevice, device.id)
            row.last_seen_at, row.last_ip = now, (request.remote_addr or "")[:64]
            s.commit()
        session["dev_seen"] = now.isoformat(timespec="seconds")
    return True


def forget_browser() -> None:
    """Sign out: this browser's device goes from the list."""
    sid = session.get("sid")
    if not sid:
        return
    with SessionLocal() as s:
        device = s.scalar(select(LabDevice).where(LabDevice.token_hash == token_hash(sid)))
        if device is not None:
            s.delete(device)
            s.commit()


# ---------------------------------------------------------------- joining

def _joined(s, user: UserAccount, form: dict) -> dict:
    """Make the device and answer the app: its token, who, the lab, and for
    an admin the lab's key."""
    from . import lab, lab_key
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    platform = form.get("platform") if form.get("platform") in PLATFORMS else "web"
    device = LabDevice(public_id=_public_id(), user_id_fk=user.id, kind="app", platform=platform,
                       name=_clean_name(form.get("name", ""), gettext("A device")),
                       app_version=str(form.get("app_version") or "")[:40], token_hash=token_hash(raw),
                       last_seen_at=datetime.utcnow(), last_ip=(request.remote_addr or "")[:64])
    s.add(device)
    s.commit()
    answer = {"ok": True, "token": raw, "device": device.public_id, "name": device.name,
              "user": {"username": user.username, "name": user.display_name or user.username, "role": user.role},
              "lab": lab.lab_name(s), "recipient": lab_key.recipient(s)}
    if user.role == "admin":
        answer["lab_key"] = lab_key.current(s).secret
    return answer


def _may_join(user) -> str:
    if user is None or user.disabled:
        return gettext("That username and password don't match.")
    if user.expires_at is not None:
        return gettext("A guest pass can't join a device: sign in in a browser instead.")
    return ""


@bp.route("/api/devices/join", methods=["POST"])
def join():
    """An app joins the lab with its person's username and password."""
    body = request.get_json(silent=True) or {}
    key = ("join", request.remote_addr or "")
    if join_throttle.retry_after(key):
        return jsonify({"ok": False, "error": gettext("Too many tries. Wait a few minutes and try again.")}), 429
    username = str(body.get("username") or "").strip()
    with SessionLocal() as s:
        user = s.scalar(select(UserAccount).where(UserAccount.username == username)) if username else None
        if not security.check_password(user, str(body.get("password") or "")):
            join_throttle.failed(key)
            return jsonify({"ok": False, "error": gettext("That username and password don't match.")}), 403
        problem = _may_join(user)
        if problem:
            return jsonify({"ok": False, "error": problem}), 403
        join_throttle.succeeded(key)
        return jsonify(_joined(s, user, body))


APP_AGENTS = ("BioManagerIOS/", "BioManagerAndroid/")


@bp.route("/api/devices/this-app", methods=["POST"])
def this_app():
    """The phone app, signed in through its own page, becomes one of its
    person's devices: the token it syncs with offline (app/sync.py). The
    page asks for it (same-origin, the cross-site check applies), and only
    the app's own window says it is the app. `replaces` is the device it
    was before, if it lost its token: that one is signed out."""
    user = g.get("user")
    if user is None or g.get("device") is not None:
        return jsonify({"ok": False, "error": gettext("Not signed in")}), 401
    if not any(a in request.headers.get("User-Agent", "") for a in APP_AGENTS):
        return jsonify({"ok": False, "error": gettext("Only the BioManager phone app asks for this.")}), 403
    problem = _may_join(user)
    if problem:
        return jsonify({"ok": False, "error": problem}), 403
    body = request.get_json(silent=True) or {}
    with SessionLocal() as s:
        old = s.scalar(select(LabDevice).where(LabDevice.public_id == str(body.get("replaces") or ""),
                                               LabDevice.user_id_fk == user.id, LabDevice.revoked_at.is_(None)))
        if old is not None:
            old.revoked_at, old.revoked_by = datetime.utcnow(), user.username
        answer = _joined(s, user, body)
    answer.pop("lab_key", None)                 # a phone keeps no backups
    return jsonify(answer)


@bp.route("/api/devices/pair", methods=["POST", "GET"])
def pair():
    """An app joins with a code (accounts without a password). POST starts:
    a code to show its person, and a secret the app keeps. GET with the
    secret (Authorization: Pair bmp_…) asks; once approved it answers with
    the token, one time."""
    now = datetime.utcnow()
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        key = ("pair", request.remote_addr or "")
        if join_throttle.retry_after(key):
            return jsonify({"ok": False, "error": gettext("Too many tries. Wait a few minutes and try again.")}), 429
        join_throttle.failed(key)               # every code asked for counts, approved or not
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        secret = PAIR_PREFIX + secrets.token_urlsafe(24)
        with SessionLocal() as s:
            s.add(DevicePairing(code_hash=token_hash(code), secret_hash=token_hash(secret),
                                name=_clean_name(body.get("name", ""), gettext("A device")),
                                platform=body.get("platform") if body.get("platform") in PLATFORMS else "web",
                                app_version=str(body.get("app_version") or "")[:40],
                                expires_at=now + timedelta(minutes=PAIR_MINUTES)))
            s.commit()
        return jsonify({"ok": True, "code": f"{code[:4]}-{code[4:]}", "secret": secret,
                        "expires_in": PAIR_MINUTES * 60})
    header = request.headers.get("Authorization", "")
    secret = header[5:].strip() if header[:5].lower() == "pair " else ""
    with SessionLocal() as s:
        pairing = s.scalar(select(DevicePairing).where(DevicePairing.secret_hash == token_hash(secret))) if secret else None
        if pairing is None or (pairing.expires_at < now and pairing.device_id_fk is None):
            return jsonify({"ok": False, "status": "expired",
                            "error": gettext("That code has expired. Ask for a new one.")}), 404
        if pairing.device_id_fk is None:
            return jsonify({"ok": True, "status": "waiting"})
        answer = dict(_pair_answer(s, pairing))
        s.delete(pairing)                       # handed over once
        s.commit()
        return jsonify(answer)


def _pair_answer(s, pairing: DevicePairing) -> dict:
    from . import lab, lab_key
    device = s.get(LabDevice, pairing.device_id_fk)
    user = s.get(UserAccount, device.user_id_fk)
    answer = {"ok": True, "status": "approved", "token": pairing.token_once, "device": device.public_id,
              "name": device.name, "lab": lab.lab_name(s), "recipient": lab_key.recipient(s),
              "user": {"username": user.username, "name": user.display_name or user.username, "role": user.role}}
    if user.role == "admin":
        answer["lab_key"] = lab_key.current(s).secret
    return answer


@bp.route("/settings/devices/approve", methods=["POST"])
def approve():
    """Someone signed in approves an app's code: it joins as their device."""
    if g.get("user") is None:
        return redirect(url_for("login"))
    code = re.sub(r"[^A-Z0-9]", "", (request.form.get("code") or "").upper())
    now = datetime.utcnow()
    with SessionLocal() as s:
        pairing = s.scalar(select(DevicePairing).where(DevicePairing.code_hash == token_hash(code))) if code else None
        if pairing is None or pairing.expires_at < now or pairing.device_id_fk is not None:
            flash(gettext("No device is waiting with that code. Codes last %(n)s minutes: ask for a new one on the device.", n=PAIR_MINUTES), "error")
            return redirect(url_for("devices.page") + "#your-devices")
        user = s.get(UserAccount, g.user.id)
        problem = _may_join(user)
        if problem:
            flash(problem, "error")
            return redirect(url_for("devices.page") + "#your-devices")
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        device = LabDevice(public_id=_public_id(), user_id_fk=user.id, kind="app", platform=pairing.platform,
                           name=pairing.name, app_version=pairing.app_version, token_hash=token_hash(raw),
                           last_seen_at=now, last_ip=(request.remote_addr or "")[:64])
        s.add(device)
        s.flush()
        pairing.device_id_fk, pairing.approved_by, pairing.token_once = device.id, user.id, raw
        s.commit()
        flash(gettext("%(name)s has joined the lab as your device.", name=device.name), "success")
    return redirect(url_for("devices.page") + "#your-devices")


@bp.route("/api/devices/me", methods=["GET", "POST"])
def me():
    """A joined device: who it is, the lab, and (POST) its name or version now."""
    if g.get("device") is None:
        return jsonify({"ok": False, "error": gettext("This device isn't signed in to the lab any more.")}), 401
    from . import lab, lab_key
    body = request.get_json(silent=True) or {}
    with SessionLocal() as s:
        device = s.get(LabDevice, g.device.id)
        if request.method == "POST":
            if body.get("name"):
                device.name = _clean_name(body["name"], device.name)
            if body.get("app_version"):
                device.app_version = str(body["app_version"])[:40]
            s.commit()
        user = s.get(UserAccount, device.user_id_fk)
        answer = {"ok": True, "device": device.public_id, "name": device.name, "lab": lab.lab_name(s),
                  "recipient": lab_key.recipient(s),
                  "user": {"username": user.username, "name": user.display_name or user.username, "role": user.role}}
        if user.role == "admin":
            answer["lab_key"] = lab_key.current(s).secret
    return jsonify(answer)


@bp.route("/api/devices/leave", methods=["POST"])
def leave():
    """A device signs itself out of the lab."""
    if g.get("device") is None:
        return jsonify({"ok": True})
    with SessionLocal() as s:
        device = s.get(LabDevice, g.device.id)
        device.revoked_at, device.revoked_by = datetime.utcnow(), g.user.username
        s.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- the list

def listing(s, user, everyone: bool = False) -> list[dict]:
    """A person's devices, or (an admin) everyone's, signed in ones first,
    most recently used first."""
    query = select(LabDevice).where(LabDevice.revoked_at.is_(None))
    if not everyone:
        query = query.where(LabDevice.user_id_fk == user.id)
    names = {u.id: u.username for u in s.scalars(select(UserAccount))}
    here_hash = token_hash(session.get("sid", "")) if session.get("sid") else ""
    here_device = g.get("device")
    rows = []
    for d in sorted(s.scalars(query), key=lambda d: d.last_seen_at or d.created_at, reverse=True):
        rows.append({"id": d.public_id, "name": d.name, "kind": d.kind, "platform": d.platform,
                     "version": d.app_version, "owner": names.get(d.user_id_fk, "?"),
                     "seen": d.last_seen_at, "ip": d.last_ip, "synced": d.last_synced_at, "copy": d.last_copy_at,
                     "here": (here_hash and d.token_hash == here_hash) or (here_device is not None and here_device.id == d.id)})
    return rows


def _own_or_admin(s, public_id: str) -> LabDevice:
    if g.get("user") is None:
        abort(403)
    device = s.scalar(select(LabDevice).where(LabDevice.public_id == public_id))
    if device is None:
        abort(404)
    if device.user_id_fk != g.user.id and g.user.role != "admin":
        abort(403)
    return device


@bp.route("/settings/devices/device/<public_id>/rename", methods=["POST"])
def rename(public_id: str):
    with SessionLocal() as s:
        device = _own_or_admin(s, public_id)
        device.name = _clean_name(request.form.get("name", ""), device.name)
        s.commit()
    return redirect(url_for("devices.page") + "#your-devices")


@bp.route("/settings/devices/device/<public_id>/sign-out", methods=["POST"])
def sign_out(public_id: str):
    """Sign a device out: its token, or its browser's sign-in, stops working now."""
    with SessionLocal() as s:
        device = _own_or_admin(s, public_id)
        device.revoked_at, device.revoked_by = datetime.utcnow(), g.user.username
        name = device.name
        s.commit()
    flash(gettext("%(name)s is signed out of the lab.", name=name), "success")
    return redirect(url_for("devices.page") + "#your-devices")


def forget_old(s) -> None:
    """Browser sign-ins long unused, and devices signed out a while ago, leave the list."""
    from flask import current_app
    stale = datetime.utcnow() - current_app.permanent_session_lifetime - timedelta(days=1)
    for d in s.scalars(select(LabDevice).where(
            ((LabDevice.kind == "browser") & (LabDevice.last_seen_at < stale))
            | (LabDevice.revoked_at < datetime.utcnow() - timedelta(days=90)))):
        s.delete(d)
    for p in s.scalars(select(DevicePairing).where(DevicePairing.expires_at < datetime.utcnow() - timedelta(days=1))):
        s.delete(p)
    from . import sync
    sync.forget_old(s)
    s.commit()
