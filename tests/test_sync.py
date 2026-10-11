"""Working offline: the snapshot, the change feed, and the queue taken in
with its clashes held for a decision (app/sync.py)."""
from __future__ import annotations

import uuid

from werkzeug.security import generate_password_hash

# tests.base first: it points the app at a throwaway database before anything
# imports the app. Importing app first would open data/biomanager.db.
from tests.base import AppTestCase, app, client_for, days_ago, execute, make_user, one, uniq  # isort: skip

PASSWORD = "lab bench 42"


def device_for(username: str) -> dict:
    """A device token for `username` (a phone that joined)."""
    execute("update users set password_hash=? where username=?", generate_password_hash(PASSWORD), username)
    body = app.test_client().post("/api/devices/join", json={"username": username, "password": PASSWORD,
                                                              "name": "Facility phone", "platform": "ios"}).get_json()
    return {"Authorization": f"Bearer {body['token']}"}


def op(action, target=None, fields=None, base=None, **extra) -> dict:
    out = {"op": uuid.uuid4().hex, "made_at": "2026-10-11T09:14:05+02:00", "action": action,
           "fields": fields or {}, "base": base or {}, **extra}
    if target is not None:
        out["target"] = target
    return out


def mouse(row_id: int) -> dict:
    return {"kind": "mouse", "id": row_id}


def cage(row_id: int) -> dict:
    return {"kind": "cage", "id": row_id}


class SyncCase(AppTestCase):
    def setUp(self):
        super().setUp()
        # A person of their own: a password (to join) signs their other sessions out.
        self.tech = make_user(uniq("tech"))
        self.phone = device_for(self.tech)
        self.t = client_for(self.tech)
        self.c = app.test_client()

    def snapshot(self) -> dict:
        r = self.c.get("/api/sync/snapshot", headers=self.phone)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        return r.get_json()

    def push(self, *ops) -> list[dict]:
        r = self.c.post("/api/sync/push", json={"ops": list(ops)}, headers=self.phone)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        return r.get_json()["results"]

    def seen(self, row_id: int, **values) -> dict:
        """What the phone saw of a mouse: its version and the values given."""
        return {"v": one("select sync_version from mice where id=?", row_id), **values}


class Snapshot(SyncCase):
    def test_the_snapshot_holds_the_colony_and_this_person_s_to_dos(self):
        colony = self.make_colony(self.t, self.tech, purpose="Breeding")
        execute("insert into tasks (title, owner, is_shared, status, priority, color, notes, created_at, sync_version) "
                "values (?, ?, false, 'todo', 'medium', '', '', '2026-10-01', 0)", "mine to do", self.tech)
        execute("insert into tasks (title, owner, is_shared, status, priority, color, notes, created_at, sync_version) "
                "values (?, ?, false, 'todo', 'medium', '', '', '2026-10-01', 0)", "someone else's", self.other)
        snap = self.snapshot()
        self.assertGreater(snap["cursor"], 0)
        self.assertEqual(snap["user"]["username"], self.tech)
        self.assertIn(colony["cage"], {c["cage_id"] for c in snap["cages"]})
        self.assertTrue({m["id"] for m in snap["mice"]} >= set(colony["mice"]))
        titles = {t["title"] for t in snap["tasks"]}
        self.assertIn("mine to do", titles)
        self.assertNotIn("someone else's", titles)          # personal to-dos are their own
        self.assertIn("mouse_weight", snap["actions"])

    def test_changes_since_a_cursor(self):
        colony = self.make_colony(self.t, self.tech, n_mice=1)
        cursor = self.snapshot()["cursor"]
        self.post(self.t, f"/colony/mice/{colony['mice'][0]}/update", {"note": "fed"})
        gone = self.make_cage(self.t)
        from app.db import SessionLocal
        from app.models import CageRecord
        with SessionLocal() as s:
            s.delete(s.get(CageRecord, gone))
            s.commit()
        r = self.c.get(f"/api/sync/changes?since={cursor}", headers=self.phone).get_json()
        self.assertGreater(r["cursor"], cursor)
        self.assertIn(colony["mice"][0], [m["id"] for m in r["changes"]["mice"]])
        self.assertIn({"table": "mouse_cages", "id": gone}, r["gone"])
        again = self.c.get(f"/api/sync/changes?since={r['cursor']}", headers=self.phone).get_json()
        self.assertEqual(again["changes"]["mice"], [])

    def test_a_guest_pass_doesn_t_work_offline(self):
        guest = make_user(uniq("guest"))
        phone = device_for(guest)
        execute("update users set expires_at='2999-01-01 00:00:00' where username=?", guest)
        self.assertNotEqual(self.c.get("/api/sync/snapshot", headers=phone).status_code, 200)


class Push(SyncCase):
    def test_a_weight_is_taken_in_once_however_often_it_is_sent(self):
        m = self.make_colony(self.t, self.tech, n_mice=1)["mice"][0]
        weigh = op("mouse_weight", mouse(m), {"grams": 24.1, "date": days_ago(1)}, cursor=self.snapshot()["cursor"])
        [first] = self.push(weigh)
        self.assertEqual(first["result"], "applied", first)
        [again] = self.push(weigh)
        self.assertEqual(again, first)
        self.assertEqual(one("select count(*) from mouse_weights where mouse_id_fk=?", m), 1)
        self.assertEqual(one("select recorded_by from mouse_weights where mouse_id_fk=?", m), self.tech)
        self.assertIn("Done offline on Facility phone", one("select description from batches order by id desc limit 1"))

    def test_a_death_that_clashes_is_held_until_its_person_decides(self):
        m = self.make_colony(self.t, self.tech, n_mice=1)["mice"][0]
        saw = self.seen(m, status="experiment")
        self.post(self.a, f"/colony/mice/{m}/update", {"status": "breeder"})        # meanwhile, online
        [held] = self.push(op("mice_died", None, {"mice": [mouse(m)], "reason": "found dead"}, {f"mouse:{m}": saw}))
        self.assertEqual(held["result"], "held", held)
        self.assertEqual(one("select status from mice where id=?", m), "breeder")  # nothing overwritten
        page = self.get_ok(self.t, "/decisions")
        self.assertIn("marked dead or culled", page)
        self.assertIn(self.admin, page)                                            # who changed it meanwhile
        self.assertIn("Needs your decision", self.get_ok(self.t, "/home"))          # in the account menu
        # A later change about the same mouse waits for the decision.
        [waits] = self.push(op("note_add", mouse(m), {"text": "checked"}))
        self.assertEqual(waits["result"], "waiting")
        r = self.post(self.t, f"/decisions/{held['held']}", {"decision": "mine"})
        self.assertFlash(r, "Your change was made", "success")
        self.assertEqual(one("select status from mice where id=?", m), "sac")
        [now] = self.push(op("note_add", mouse(m), {"text": "checked"}))
        self.assertEqual(now["result"], "applied", now)

    def test_keep_theirs_drops_the_offline_change(self):
        m = self.make_colony(self.t, self.tech, n_mice=1)["mice"][0]
        saw = self.seen(m, status="experiment")
        self.post(self.a, f"/colony/mice/{m}/update", {"status": "breeder"})
        [held] = self.push(op("mouse_change", mouse(m), {"status": "geno"}, {f"mouse:{m}": saw}))
        r = self.c.post(f"/api/sync/held/{held['held']}", json={"decision": "theirs"}, headers=self.phone)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(one("select status from mice where id=?", m), "breeder")
        self.assertEqual(self.c.get("/api/sync/held", headers=self.phone).get_json()["held"], [])

    def test_a_different_field_changed_meanwhile_is_merged(self):
        m = self.make_colony(self.t, self.tech, n_mice=1)["mice"][0]
        saw = self.seen(m, status="experiment", note="")
        self.post(self.a, f"/colony/mice/{m}/update", {"note": "moved to room B"})
        [merged] = self.push(op("mouse_change", mouse(m), {"status": "geno"}, {f"mouse:{m}": saw}))
        self.assertEqual(merged["result"], "merged", merged)
        self.assertEqual((one("select status from mice where id=?", m), one("select note from mice where id=?", m)),
                         ("geno", "moved to room B"))

    def test_both_marking_a_mouse_dead_agree(self):
        m = self.make_colony(self.t, self.tech, n_mice=1)["mice"][0]
        saw = self.seen(m, status="experiment")
        self.post(self.a, "/colony/mice/bulk-sac", {"mouse_ids": str(m)})
        execute("update mice set status='sac', date_of_death=? where id=?", days_ago(1), m)
        [same] = self.push(op("mice_died", None, {"mice": [mouse(m)]}, {f"mouse:{m}": saw}))
        self.assertEqual(same["result"], "applied", same)
        self.assertEqual(str(one("select date_of_death from mice where id=?", m))[:10], days_ago(1))

    def test_pups_made_offline_are_named_by_temporary_ids(self):
        colony = self.make_colony(self.t, self.tech, n_mice=1, purpose="Breeding")
        made = op("litter_genotyping", cage(colony["cage_id"]), {"pups": 2},
                  creates={"litter": ["tmp:l1"], "mouse": ["tmp:p1", "tmp:p2"]}, cursor=self.snapshot()["cursor"])
        weigh = op("mouse_weight", "tmp:p2", {"grams": 3.2})
        first, second = self.push(made, weigh)
        self.assertEqual(first["result"], "applied", first)
        pup = first["ids"]["tmp:p2"]
        self.assertEqual(pup["kind"], "mouse")
        self.assertEqual(second["result"], "applied", second)
        self.assertEqual(one("select grams from mouse_weights where mouse_id_fk=?", pup["id"]), 3.2)
        # Sent again later, the temporary id is still known.
        [later] = self.push(op("note_add", "tmp:p1", {"text": "tail clipped"}))
        self.assertEqual(later["result"], "applied", later)

    def test_the_page_s_own_rules_refuse_and_what_depends_on_it_goes_too(self):
        colony = self.make_colony(self.t, self.tech, n_mice=1, purpose="Experiment")
        made = op("litter_genotyping", cage(colony["cage_id"]), {"pups": 2}, creates={"mouse": ["tmp:x1", "tmp:x2"]})
        first, second = self.push(made, op("mouse_weight", "tmp:x1", {"grams": 3}))
        self.assertEqual(first["result"], "refused")
        self.assertIn("Breeding", first["message"])
        self.assertEqual(second["result"], "refused")
        self.assertIn("refused", self.get_ok(self.t, "/decisions"))

    def test_a_to_do_ticked_offline_stays_done(self):
        execute("insert into tasks (title, owner, is_shared, status, priority, color, notes, created_at, sync_version) "
                "values (?, ?, false, 'todo', 'medium', '', '', '2026-10-01', 0)", "change the water", self.tech)
        task = one("select id from tasks where title='change the water' and owner=?", self.tech)
        [done] = self.push(op("task_done", {"kind": "task", "id": task}))
        self.assertEqual(done["result"], "applied", done)
        [again] = self.push(op("task_done", {"kind": "task", "id": task}))
        self.assertEqual(again["result"], "applied")
        self.assertEqual(one("select status from tasks where id=?", task), "done")

    def test_a_move_to_where_it_already_is_is_done(self):
        colony = self.make_colony(self.t, self.tech, n_mice=1)
        [moved] = self.push(op("mice_move", cage(colony["cage_id"]), {"mice": [mouse(colony["mice"][0])]}))
        self.assertEqual(moved["result"], "applied")
        self.assertIn("Already in cage", moved["message"])

    def test_a_tank_s_field_changed_meanwhile_is_held(self):
        tank = self.make_tank(self.t, owner=self.tech)
        saw = {"v": one("select sync_version from tanks where id=?", tank), "notes": ""}
        self.post(self.a, f"/zebrafish/tanks/{tank}/update", {"notes": "fed twice"})
        [held] = self.push(op("tank_change", {"kind": "tank", "id": tank}, {"notes": "fed once"}, {f"tank:{tank}": saw}))
        self.assertEqual(held["result"], "held", held)
        self.assertEqual(one("select notes from tanks where id=?", tank), "fed twice")

    def test_an_unknown_action_is_refused(self):
        [no] = self.push(op("cage_new", None, {}))
        self.assertEqual(no["result"], "refused")
