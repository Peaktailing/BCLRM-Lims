"""The desktop's copy of the facility, for working offline through its relay.

While the lab's server can be reached, the desktop keeps what its person
needs offline (the server's snapshot, app/sync.py) and refreshes it from the
change feed every few minutes. When the server can't be reached, the relay
(app/relay.py) shows the offline screens (app/static/offline/) instead of
"can't be reached": they read this copy and add what is done to a queue,
which goes to the server, in order, as soon as it answers again.

Both files are on this computer only, encrypted with its own secret
(security.encrypt_text), in the data folder under offline/<the server>.

  store = Store(server, token)       token: a function giving the device's token now
  store.snapshot(), store.queue()    what the screens read
  store.add(op)                      one change done offline
  store.sync()                       send the queue, then catch up; returns the status
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import security
from .paths import data_dir

EVERY = 5 * 60                  # seconds between refreshes while the server answers
MAX_QUEUE = 2000
# The change feed's tables, and where the snapshot keeps their records.
TABLES = {"mice": "mice", "mouse_cages": "cages", "litters": "litters", "mouse_weights": "weights", "tasks": "tasks",
          "mouse_racks": "racks", "stock_units": "stock_units", "tanks": "tanks"}
FINAL = ("applied", "merged", "held", "refused")      # results that take a change off the queue


class Store:
    def __init__(self, server: str, token, version: str = ""):
        self.server = server.rstrip("/")
        self.token = token
        self.version = version
        self.folder = data_dir() / "offline" / hashlib.sha256(self.server.encode()).hexdigest()[:16]
        self.lock = threading.RLock()
        self._syncing = threading.Lock()

    # ------------------------------------------------------------ the files
    def _path(self, name: str) -> Path:
        return self.folder / f"{name}.enc"

    def _read(self, name: str, empty):
        try:
            text = security.decrypt_text(self._path(name).read_text(encoding="utf-8"))
            return json.loads(text) if text else empty
        except (OSError, ValueError):
            return empty

    def _write(self, name: str, value) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        part = self._path(name).with_suffix(".part")
        part.write_text(security.encrypt_text(json.dumps(value, separators=(",", ":"))), encoding="utf-8")
        part.replace(self._path(name))

    def snapshot(self) -> dict | None:
        with self.lock:
            return self._read("snapshot", None)

    def queue(self) -> list:
        with self.lock:
            return self._read("queue", [])

    def state(self) -> dict:
        with self.lock:
            return self._read("state", {})

    def _set_state(self, **changes) -> dict:
        with self.lock:
            state = {**self.state(), **changes}
            self._write("state", state)
            return state

    def forget(self) -> None:
        """Signed out of the lab: nothing of it stays here."""
        with self.lock:
            for name in ("snapshot", "queue", "state"):
                self._path(name).unlink(missing_ok=True)

    # ------------------------------------------------------------ what the screens do
    def add(self, op: dict) -> int:
        """One change done offline, at the end of the queue; how many wait."""
        if not isinstance(op, dict) or not str(op.get("op") or "").strip() or not op.get("action"):
            raise ValueError("a change is {op, action, target, fields, base}")
        with self.lock:
            queue = self.queue()
            if any(q.get("op") == op["op"] for q in queue):
                return len(queue)
            if len(queue) >= MAX_QUEUE:
                raise ValueError("too many changes are waiting")
            queue.append(op)
            self._write("queue", queue)
            return len(queue)

    def status(self) -> dict:
        snap = self.snapshot()
        state = self.state()
        return {"waiting": len(self.queue()), "taken": (snap or {}).get("taken", ""),
                "cursor": (snap or {}).get("cursor"), "has_copy": snap is not None,
                "last_sync": state.get("last_sync", ""), "error": state.get("error", ""),
                "held": state.get("held", 0), "refused": state.get("refused", [])[-20:],
                "online": state.get("online", False)}

    # ------------------------------------------------------------ talking to the server
    def _call(self, method: str, path: str, body=None, timeout: int = 60) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.server + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token()}", "Accept": "application/json",
            "Content-Type": "application/json", "User-Agent": "BioManager desktop",
            "X-BioManager-Version": self.version})
        with urlopen(req, timeout=timeout) as r:     # noqa: S310 (the lab's server this computer joined)
            return json.loads(r.read().decode() or "{}")

    def sync(self) -> dict:
        """Send what waits, in order; then catch up with the lab. Never two at
        once: one asked for while another runs waits for it, and has its answer."""
        if not self._syncing.acquire(blocking=False):
            if self._syncing.acquire(timeout=300):
                self._syncing.release()
            return self.status()
        try:
            self._push()
            self._catch_up()
            self._set_state(online=True, error="", last_sync=datetime.utcnow().isoformat(timespec="seconds") + "Z")
        except (URLError, OSError, ValueError) as error:
            reason = error.reason if isinstance(error, URLError) and not isinstance(error, HTTPError) else error
            self._set_state(online=False, error=str(reason)[:300])
        finally:
            self._syncing.release()
        return self.status()

    def _push(self) -> None:
        queue = self.queue()
        if not queue:
            return
        sent = queue[:200]
        answer = self._call("POST", "/api/sync/push", {"ops": sent}, timeout=300)
        results = {r.get("op"): r for r in answer.get("results", []) if isinstance(r, dict)}
        done = {op_id for op_id, r in results.items() if r.get("result") in FINAL}
        refused = [{"op": op_id, "action": r.get("action", ""), "message": r.get("message", "")}
                   for op_id, r in results.items() if r.get("result") == "refused"]
        ids = {}
        for r in results.values():
            ids.update(r.get("ids") or {})
        with self.lock:
            # Later changes naming what an applied one made now name the real record.
            remaining = [_rename(q, ids) for q in self.queue() if q.get("op") not in done]
            self._write("queue", remaining)
            state = self.state()
            self._set_state(held=answer.get("held", 0), refused=(state.get("refused", []) + refused)[-50:])

    def _catch_up(self) -> None:
        snap = self.snapshot()
        if snap is not None and isinstance(snap.get("cursor"), int):
            answer = self._call("GET", f"/api/sync/changes?since={snap['cursor']}")
            if not answer.get("reset"):
                with self.lock:
                    snap = self.snapshot() or snap
                    _apply_changes(snap, answer)
                    snap["taken"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                    self._write("snapshot", snap)
                return
        fresh = self._call("GET", "/api/sync/snapshot", timeout=300)
        if fresh.get("ok"):
            with self.lock:
                self._write("snapshot", fresh)


def _rename(value, ids: dict):
    if isinstance(value, str) and value in ids:
        return dict(ids[value])
    if isinstance(value, list):
        return [_rename(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: _rename(v, ids) for k, v in value.items()}
    return value


def _apply_changes(snap: dict, answer: dict) -> None:
    """The change feed's records into the snapshot, and what went out of it."""
    for key, rows in (answer.get("changes") or {}).items():
        current = {r["id"]: r for r in snap.get(key, []) if isinstance(r, dict)}
        for row in rows:
            current[row["id"]] = row
        snap[key] = list(current.values())
    gone: dict[str, set] = {}
    for g in answer.get("gone") or []:
        key = TABLES.get(g.get("table"))
        if key:
            gone.setdefault(key, set()).add(g.get("id"))
    for key, ids in gone.items():
        snap[key] = [r for r in snap.get(key, []) if r.get("id") not in ids]
    snap["cursor"] = answer.get("cursor", snap.get("cursor"))


# ---------------------------------------------------------------- keeping it fresh

_loop: dict = {}


def start_background(store: Store) -> None:
    """Refresh every few minutes while the server answers (one loop per store)."""
    _loop["store"] = store
    if _loop.get("thread") and _loop["thread"].is_alive():
        return

    def run():
        while True:
            current = _loop.get("store")
            if current is None:
                return
            try:
                current.sync()
            except Exception:  # noqa: BLE001 — the loop never stops over one failure
                pass
            time.sleep(EVERY)

    _loop["thread"] = threading.Thread(target=run, name="offline-store", daemon=True)
    _loop["thread"].start()


def stop_background() -> None:
    _loop.pop("store", None)
