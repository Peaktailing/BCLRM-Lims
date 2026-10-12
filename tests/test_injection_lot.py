"""The lot of the reagent each manipulation used (app/experiment_steps.py
reagent_used): recorded every time, from the page, bench mode and an
action; the step's own item by default, or the one item named as its
agent; another item or lot when someone says; expired lots warned about;
what was given taken off the inventory only when asked."""
from __future__ import annotations

import json
from datetime import date, timedelta

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import AppTestCase, location, one, row, uniq
from app import actions  # noqa: E402
from app.app import app  # noqa: E402
from app import experiment_steps as xs  # noqa: E402

TODAY = date.today()


class Lots(AppTestCase):
    def setUp(self):
        super().setUp()
        self.start = TODAY - timedelta(days=1)            # day 2 is today
        r = self.m.post("/colony/experiments/create", data={"name": uniq("TMX "), "start_date": self.start.isoformat()})
        self.exp = int(location(r).rsplit("/", 1)[1])
        self.mice = [self.make_mouse(self.m, self.member) for _ in range(2)]
        for i, mouse in enumerate(self.mice):
            self.m.post(f"/colony/experiments/{self.exp}/add-mouse", data={"mouse_row_id": mouse})
            self.m.post(f"/colony/mice/{mouse}/weights/create",
                        data={"weigh_date": self.start.isoformat(), "grams": str(20 + i * 5)})
        self.agent = uniq("Tamoxifen ")
        self.bottle = self.make_item(self.m, "reagents", self.agent, lot="L-1", quantity="10", unit="mL",
                                     expires_on=(TODAY + timedelta(days=200)).isoformat())

    def step(self, **fields):
        body = {"kind": "injection", "agent": self.agent, "dose": "20 mg/kg", "concentration": "10 mg/mL",
                "route": "i.p.", "days": "1-3", **fields}
        r = self.m.post(f"/colony/experiments/{self.exp}/steps/save", json=body)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["steps"][-1]["id"]

    def record(self, step, day=2, **body):
        r = self.m.post(f"/colony/experiments/{self.exp}/steps/{step}/day/{day}/record",
                        json={"done_on": xs.day_date(self.start, day).isoformat(), **body})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def kept(self, step, day=2) -> dict:
        return json.loads(one("select reagent from experiment_step_records where step_id_fk=? and day=?", step, day)
                          or "{}")

    def apply(self, *changes, ok=True):
        out = actions.run(app, self.member, list(changes), apply=True, description=uniq("P"))
        if ok:
            self.assertTrue(out.ok, [c.as_dict() for c in out.changes])
        return out

    # ---- the page and bench mode (the same record route)

    def test_the_step_s_own_item_is_recorded_without_asking(self):
        step = self.step(reagent_id=str(self.bottle))
        self.record(step)                                        # bench mode sends no reagent_id
        self.assertEqual((self.kept(step)["id"], self.kept(step)["lot"]), (self.bottle, "L-1"))
        self.assertTrue(self.kept(step)["expires"])

    def test_a_step_with_only_an_agent_uses_the_item_of_its_name_and_remembers_it(self):
        step = self.step()
        self.assertIsNone(one("select reagent_item_id_fk from experiment_steps where id=?", step))
        self.record(step)
        self.assertEqual(self.kept(step)["lot"], "L-1")
        self.assertEqual(one("select reagent_item_id_fk from experiment_steps where id=?", step), self.bottle)
        page = self.m.get(f"/colony/experiments/{self.exp}").get_data(as_text=True)
        self.assertIn('"lot": "L-1"', page)                       # the page's choices carry the lot

    def test_two_of_the_name_record_none_unless_one_is_chosen(self):
        other = self.make_item(self.m, "reagents", self.agent, lot="L-2")
        step = self.step()
        self.record(step)
        self.assertEqual(self.kept(step), {})
        self.record(step, day=3, reagent_id=str(other), done_on=TODAY.isoformat())
        self.assertEqual(self.kept(step, 3)["lot"], "L-2")
        self.assertEqual(one("select reagent_item_id_fk from experiment_steps where id=?", step), other)

    def test_a_different_lot_another_item_or_as_typed(self):
        new = self.make_item(self.m, "reagents", self.agent, lot="L-9",
                             expires_on=(TODAY + timedelta(days=400)).isoformat())
        step = self.step(reagent_id=str(self.bottle))
        self.record(step, lot="l-9")                              # the new bottle, by its lot
        self.assertEqual((self.kept(step)["id"], self.kept(step)["lot"]), (new, "L-9"))
        self.record(step, day=1, reagent_id=str(self.bottle), lot="X-77")
        kept = self.kept(step, 1)
        self.assertEqual((kept["id"], kept["lot"], kept["expires"]), (self.bottle, "X-77", ""))

    def test_an_expired_lot_is_warned_about_not_refused(self):
        old = self.make_item(self.m, "reagents", uniq("Old "), lot="L-0",
                             expires_on=(TODAY - timedelta(days=10)).isoformat())
        step = self.step(reagent_id=str(old))
        data = self.record(step)
        self.assertTrue(any("L-0" in p and "expired" in p for p in data["problems"]), data["problems"])
        self.assertEqual(self.kept(step)["lot"], "L-0")

    def test_taken_off_the_inventory_only_when_asked_and_once(self):
        step = self.step(reagent_id=str(self.bottle))
        self.record(step)
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "10")
        # 0.4 mg and 0.5 mg at 10 mg/mL: 40 µL + 50 µL = 0.09 mL
        data = self.record(step, day=1, take_off=True)
        self.assertIn("taken off", data["message"])
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "9.91")
        self.assertIn("taken", self.kept(step, 1))
        self.record(step, day=1, take_off=True, note="again")     # saved again: not twice
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "9.91")

    def test_undoing_the_day_puts_it_back(self):
        step = self.step(reagent_id=str(self.bottle))
        self.record(step, day=1, take_off=True)
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "9.91")
        r = self.m.post(f"/colony/experiments/{self.exp}/steps/{step}/day/1/undo", json={})
        self.assertIn("put back", r.get_json()["message"])
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "10")

    def test_recorded_again_with_another_bottle_the_first_gets_it_back(self):
        other = self.make_item(self.m, "reagents", self.agent, lot="L-2", quantity="5", unit="mL",
                               expires_on=(TODAY + timedelta(days=300)).isoformat())
        step = self.step(reagent_id=str(self.bottle))
        self.record(step, day=1, take_off=True)
        data = self.record(step, day=1, reagent_id=str(other), take_off=True)
        self.assertIn("put back", data["message"])
        self.assertEqual(one("select quantity from inventory_items where id=?", self.bottle), "10")
        self.assertEqual(one("select quantity from inventory_items where id=?", other), "4.91")

    def test_take_off_that_does_not_fit_says_why(self):
        vials = self.make_item(self.m, "reagents", uniq("Vials "), quantity="3", unit="vials")
        step = self.step(reagent_id=str(vials))
        data = self.record(step, take_off=True)
        self.assertTrue(any("Nothing was taken off" in p for p in data["problems"]), data["problems"])
        self.assertEqual(one("select quantity from inventory_items where id=?", vials), "3")

    def test_record_manipulation_not_in_the_plan_keeps_the_lot(self):
        data = self.m.post(f"/colony/experiments/{self.exp}/record-now", json={
            "kind": "injection", "agent": self.agent, "dose": "25 µg", "done_on": TODAY.isoformat()}).get_json()
        rec = [r for r in data["schedule"] if r["record"]][0]["record"]
        self.assertEqual(rec["reagent"]["lot"], "L-1")

    def test_the_lot_is_in_the_export_and_the_summary(self):
        step = self.step(reagent_id=str(self.bottle))
        self.record(step)
        from app import experiments as xp
        from app.assistant_compute import experiment_summary
        from app.db import SessionLocal
        with app.test_request_context("/"), SessionLocal() as s:
            procedures = experiment_summary(s, self.exp)["procedures"]
            exp = s.get(xp.Experiment, self.exp)
            manip = xp._rows_for_export(s, exp, xp.place_for(s, "colony"))[2]
        self.assertIn(f"{self.agent} lot L-1", procedures[0]["lots"])
        self.assertEqual(manip[0][-2], "Lot")
        self.assertIn("L-1", [r[-2] for r in manip[1:]])

    # ---- an action

    def test_an_action_records_the_step_s_lot_and_says_so(self):
        step = self.step(reagent_id=str(self.bottle))
        out = self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": step}})
        self.assertIn("lot L-1", out.changes[0].summary)
        self.assertEqual(self.kept(step)["lot"], "L-1")

    def test_an_action_names_another_lot(self):
        new = self.make_item(self.m, "reagents", self.agent, lot="L-5")
        step = self.step(reagent_id=str(self.bottle))
        self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": step},
                    "fields": {"lot": "L-5"}})
        self.assertEqual(self.kept(step)["id"], new)

    def test_an_unknown_lot_or_a_choice_left_open_is_refused(self):
        step = self.step(reagent_id=str(self.bottle))
        out = self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": step},
                          "fields": {"lot": "NOPE"}}, ok=False)
        self.assertIn("no", " ".join(out.changes[0].errors))
        self.assertIn("NOPE", " ".join(out.changes[0].errors))
        self.make_item(self.m, "reagents", self.agent, lot="L-6")
        bare = self.step(days="5")
        out = self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": bare},
                          "fields": {"day": 5}}, ok=False)
        self.assertIn("more than once", " ".join(out.changes[0].errors))
        self.assertIsNone(one("select id from experiment_step_records where step_id_fk=?", bare))

    def test_an_action_warns_of_an_expired_lot(self):
        old = self.make_item(self.m, "reagents", uniq("Old "), lot="L-0",
                             expires_on=(TODAY - timedelta(days=10)).isoformat())
        step = self.step(reagent_id=str(old))
        out = self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": step}})
        self.assertTrue(any("expired" in w for w in out.changes[0].warnings), out.changes[0].warnings)

    def test_an_action_takes_it_off_when_asked(self):
        step = self.step(reagent_id=str(self.bottle))
        out = self.apply({"action": "experiment_step_done", "target": {"kind": "experiment_step", "id": step},
                          "fields": {"take_off": True}})
        self.assertIn("taken off", out.changes[0].summary)
        self.assertEqual(row("select quantity from inventory_items where id=?", self.bottle), ("9.91",))
