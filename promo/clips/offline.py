"""Working offline: the facility with no signal, then a clash decided.

The phone segment is the offline screens themselves (app/static/offline/),
opened from the demo lab's /static/offline/ so the site's copy of the app's
files carries their stylesheet. Their store answers as the desktop's relay
does (/_relay/store, app/relay.py), from the demo lab's own snapshot
(/api/sync/snapshot), with the server out of reach: what is recorded waits.
The desktop segment is Needs your decision, with a change made offline that
clashed with one made meanwhile (prepared through /api/sync/push).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

CHOSEN: dict = {}


def post_json(api, url, body):
    r = api.post(url, data=json.dumps(body), headers={"Content-Type": "application/json"})
    if not r.ok:
        raise RuntimeError(f"{url}: {r.status} {r.text()[:200]}")
    return r.json()


def make_offline(api, base):
    """A Breeding cage with mice, for the phone; and a held change, for Needs
    your decision: the phone saw a mouse as one thing, someone set it to
    another meanwhile, and the phone's "died" clashes."""
    snap = api.get(f"{base}/api/sync/snapshot").json()
    living = {}
    for m in snap["mice"]:
        if not m["date_of_death"] and m["cage"]:
            living.setdefault(m["cage"], []).append(m)
    cages = sorted((c for c in snap["cages"] if c["edit"] and living.get(c["id"])),
                   key=lambda c: -len(living[c["id"]]))
    cage = cages[0]
    api.post(f"{base}/colony/cages/{cage['id']}/update", form={"purpose": "Breeding"}, headers={"X-Autosave": "1"})
    CHOSEN["cage"] = cage["cage_id"]
    # Another cage's mouse, for the clash.
    other = next(m for c in cages[1:] for m in living[c["id"]])
    saw = {"v": other["v"], "status": other["status"]}
    meanwhile = "experiment" if other["status"] != "experiment" else "breeder"
    api.post(f"{base}/colony/mice/{other['id']}/update", form={"status": meanwhile}, headers={"X-Autosave": "1"})
    answer = post_json(api, f"{base}/api/sync/push", {"ops": [{
        "op": uuid.uuid4().hex, "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": "mice_died", "fields": {"mice": [{"kind": "mouse", "id": other["id"]}], "reason": "found dead"},
        "base": {f"mouse:{other['id']}": saw}}]})
    if answer["results"][0]["result"] != "held":
        raise RuntimeError(f"the clash wasn't held: {answer}")


def offline_phone(d):
    base = d.base
    snap = d.page.request.get(f"{base}/api/sync/snapshot").json()
    snap["taken"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    queue: list = []

    def status():
        return {"waiting": len(queue), "taken": snap["taken"], "has_copy": True, "held": 0, "refused": [],
                "online": False}

    def answer(route, body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def relay(route):
        req = route.request
        path = req.url[len(base):].split("?")[0]
        if path == "/_relay/store/queue":
            queue.append(json.loads(req.post_data or "{}"))
            return answer(route, {"ok": True, "waiting": len(queue)})
        if path == "/_relay/store":
            return answer(route, {"snapshot": snap, "queue": queue, "status": status()})
        if path == "/_relay/sync":
            return answer(route, {"ok": True, "status": status()})
        return answer(route, {"online": False, "store": status()})

    d.page.context.route(f"{base}/_relay/**", relay)
    zh = getattr(d, "lang", "en") == "zh"
    words = json.loads((ROOT / "app/translations/zh/js-offline.json").read_text(encoding="utf-8")) if zh else {}
    d.page.context.route(f"{base}/_offline/strings.json",
                         lambda route: answer(route, {"lang": "zh" if zh else "en", "words": words}))
    d.goto("/static/offline/index.html", settle=1.0)
    d.start()
    d.wait(0.8)
    # A cage by its card's ID, as at the rack.
    d.type("#find", CHOSEN["cage"], delay=90, after=0.8)
    d.click("[data-open-cage] >> nth=0", after=1.2)
    d.cover()
    # A weight, recorded with no signal: it shows at once, waiting.
    d.click("[data-act=weigh] >> nth=0", after=0.8)
    d.type("#ask input[name=f0]", "24.1", delay=110, after=0.5)
    d.click("#ask-ok", after=1.0)
    d.zoom("#waiting", scale=2.2)
    d.wait(1.4)
    d.unzoom()
    # Genotyping: the pups appear, ready to weigh.
    d.click("[data-act=genotyping]", after=0.8)
    d.type("#ask input[name=f0]", "4", delay=110, after=0.5)
    d.click("#ask-ok", after=1.0)
    d.scroll(420, seconds=1.2)
    d.wait(1.2)


def decide(d):
    d.goto("/decisions", settle=0.8)
    d.start()
    d.wait(1.0)
    card = d.page.locator("section[id^=held-]").first
    d.zoom(card, scale=1.5)
    d.wait(1.8)
    d.move("button[value=mine] >> nth=0", 0.8)
    d.wait(0.6)
    d.unzoom()
    d.click("button[value=mine] >> nth=0", after=1.6)


CLIPS = {
    "offline": [("phone", offline_phone), ("desktop", decide)],
}
PREPARE = {
    "offline": make_offline,
}
