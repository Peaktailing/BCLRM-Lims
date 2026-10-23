"""The shelf as a cache: online writes, delta reads, and versions.

Three claims are tested here, and they are the reasons the chemical shelf does
not work offline:

  * a bottle is read in pieces — a cursor, and only what changed after it,
    with a fixed short projection (app/chem_cache.py)
  * a write names the version it saw, and a write against a shelf that has
    moved on is refused instead of applied (app/reagent_workflow.py)
  * nothing about a bottle may be queued on a device: the offline queue has
    no chemical action, and asking it for one is refused (app/sync.py)

The version itself is the lab's change count (app/sync_clock.py) on the
newest of the four rows that describe a bottle.
"""
from __future__ import annotations

from types import SimpleNamespace

# tests.base first: it points the app at a throwaway database before app is
# imported. Importing app first would open data/biomanager.db.
from tests.base import *  # noqa: F401,F403
from tests.base import one, row
from tests import test_inventory as inv_tests

from app import chem_cache, reagent_workflow


class Shelf(inv_tests.InventoryCase):
    """A reagent database of its own. The suite shares one database, so every
    test file that needs bottles makes its own module and works only in it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shelf = cls.new_module(cls.a, "chemical_reagents")

    def bottle(self, name: str | None = None, **fields) -> int:
        return self.make_item(self.a, self.shelf, name,
                              attr_cas="69-72-7", attr_quantity="500", attr_unit="g", **fields)

    def cache(self, **params):
        r = self.a.get("/api/chem/cache", query_string=params)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def bump(self, item_id: int, **changes) -> None:
        """Change a bottle the way a page would: through the session, so the
        change counter stamps it."""
        from app.db import SessionLocal
        from app.models import InventoryItem
        with SessionLocal() as s:
            item = s.get(InventoryItem, item_id)
            for key, value in changes.items():
                setattr(item, key, value)
            s.commit()

    def version_of(self, item_id: int) -> int:
        from app.db import SessionLocal
        from app.models import ChemBottle, InventoryItem
        with SessionLocal() as s:
            item = s.get(InventoryItem, item_id)
            row_ = s.get(ChemBottle, item_id)
            return chem_cache.version(item, row_, row_.lot if row_ is not None else None)

    def make_order(self, bottle_id: int, status: str = "approved", requester: str | None = None) -> int:
        from app.db import SessionLocal
        from app.models import ReagentBorrowOrder
        with SessionLocal() as s:
            order = ReagentBorrowOrder(number=9999, bottle_id=bottle_id,
                                       requester=requester or self.member, status=status,
                                       quantity=100.0, unit="g", experiment_name="缓存测试")
            s.add(order)
            s.commit()
            return order.id

    def sign_out(self, order_id: int, expected: int | None = None) -> str:
        from app.db import SessionLocal
        actor = SimpleNamespace(username=self.admin, role="admin")
        with SessionLocal() as s:
            message = reagent_workflow.sign_out(s, order_id, actor, expected_version=expected)
            s.commit()
            return message


class Reading(Shelf):
    def test_the_shelf_comes_back_with_the_fields_a_list_shows(self):
        bottle = self.bottle()
        answer = self.cache()
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["fields"], list(chem_cache.FIELDS))
        mine = [b for b in answer["bottles"] if b["id"] == bottle]
        self.assertEqual(len(mine), 1, "the bottle just created is not in the cache")
        self.assertEqual(set(mine[0]), set(chem_cache.FIELDS))

    def test_a_bottle_has_a_version_from_the_lab_count(self):
        bottle = self.bottle()
        self.assertGreater(self.version_of(bottle), 0)

    def test_the_delta_carries_only_what_changed(self):
        first = self.bottle()
        second = self.bottle()
        cursor = self.cache()["cursor"]
        self.bump(second, notes="counting again")
        answer = self.cache(since=cursor)
        self.assertFalse(answer["reset"])
        ids = [b["id"] for b in answer["bottles"]]
        self.assertIn(second, ids)
        self.assertNotIn(first, ids)
        self.assertGreater(answer["cursor"], cursor)

    def test_nothing_changed_is_an_empty_answer_not_a_reset(self):
        self.bottle()
        cursor = self.cache()["cursor"]
        answer = self.cache(since=cursor)
        self.assertEqual(answer["bottles"], [])
        self.assertFalse(answer["reset"])

    def test_a_cursor_from_another_lab_asks_for_a_reset(self):
        self.bottle()
        answer = self.cache(since=10 ** 9)
        self.assertTrue(answer["reset"])
        self.assertEqual(answer["bottles"], [])

    def test_a_detail_carries_what_the_list_leaves_out(self):
        bottle = self.bottle()
        r = self.a.get(f"/api/chem/bottle/{bottle}")
        self.assertEqual(r.status_code, 200)
        detail = r.get_json()["bottle"]
        for key in ("substance", "lot", "moves", "custodian", "opened", "v", "notes"):
            self.assertIn(key, detail)

    def test_the_answer_is_not_cacheable_by_a_proxy(self):
        r = self.a.get("/api/chem/cache")
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_a_bottle_from_another_database_is_not_in_the_shelf(self):
        other = self.new_module(self.a, "custom", "不是试剂")
        foreign = self.make_item(self.a, other, "盒子")
        ids = [b["id"] for b in self.cache()["bottles"]]
        self.assertNotIn(foreign, ids)


class Writing(Shelf):
    def test_an_approved_order_takes_the_bottle_off_the_shelf(self):
        bottle = self.bottle()
        order = self.make_order(bottle)
        self.assertEqual(self.sign_out(order), "")
        self.assertEqual(one("select state from chem_bottle where item_id_fk=?", bottle), "borrowed")

    def test_the_same_bottle_cannot_be_signed_out_twice(self):
        bottle = self.bottle()
        first = self.make_order(bottle)
        self.assertEqual(self.sign_out(first), "")
        # A second order for the same bottle — approved before the first was
        # signed out, the way two people working at once would leave it.
        second = self.make_order(bottle)
        message = self.sign_out(second)
        self.assertIn("不能领出", message)
        self.assertEqual(one("select status from chem_borrow_order where id=?", second), "approved")

    def test_a_stale_version_is_refused(self):
        bottle = self.bottle()
        order = self.make_order(bottle)
        seen = self.version_of(bottle)
        self.bump(bottle, notes="someone else was here")
        message = self.sign_out(order, expected=seen)
        self.assertIn("已经被改动过", message)
        self.assertEqual(one("select status from chem_borrow_order where id=?", order), "approved")

    def test_the_version_it_saw_is_accepted(self):
        bottle = self.bottle()
        order = self.make_order(bottle)
        seen = self.version_of(bottle)
        self.assertEqual(self.sign_out(order, expected=seen), "")

    def test_returning_puts_the_bottle_back_and_records_the_opening(self):
        from app.db import SessionLocal
        bottle = self.bottle()
        order = self.make_order(bottle)
        self.sign_out(order)
        actor = SimpleNamespace(username=self.admin, role="admin")
        with SessionLocal() as s:
            message = reagent_workflow.record_return(s, order, actor, returned=80.0)
            s.commit()
        self.assertEqual(message, "")
        state, opened = row("select state, opened_on from chem_bottle where item_id_fk=?", bottle)
        self.assertEqual(state, "in_stock")
        self.assertIsNotNone(opened)

    def test_a_second_order_may_ask_but_cannot_take_the_bottle(self):
        """Orders are intentions; the bottle is the fact. Two orders for one
        bottle may both stand — the second sign-out is what is refused."""
        bottle = self.bottle()
        first = self.make_order(bottle)
        second = self.make_order(bottle, status="approved")
        self.assertEqual(self.sign_out(first), "")
        self.assertIn("不能领出", self.sign_out(second))
        self.assertEqual(one("select status from chem_borrow_order where id=?", second), "approved")


class Offline(Shelf):
    def test_the_queue_has_no_chemical_action(self):
        from app.sync import ACTIONS
        self.assertEqual([a for a in ACTIONS if a.startswith("chem")], [])

    def test_pushing_a_bottle_action_is_refused(self):
        r = self.a.post("/api/sync/push", json={"ops": [
            {"op": "cache-test-1", "action": "chem_bottle_issue", "target": {}, "fields": {}}]})
        self.assertEqual(r.status_code, 200)
        answer = r.get_json()["results"][0]
        self.assertEqual(answer["result"], "refused")
        self.assertIn("offline", answer["message"])
