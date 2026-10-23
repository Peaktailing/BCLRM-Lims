"""The reagent borrow flow (app/reagent_workflow.py and its routes): a
plan's bottles become orders, a controlled one waits for an approver,
the bottle says "in use" while it is out, and the return writes the day
it was first opened.

The aspirin class again: the lab has one bottle of the anhydride (a drug
precursor, so it needs an approver) and none of the acid.
"""
from __future__ import annotations

from datetime import date

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import *  # noqa: F401,F403
from tests.base import one, row
from tests import test_chemical_experiments as chem_tests
from tests import test_inventory as inv_tests

from app import reagent_workflow
from app.models import ChemicalExperiment, ReagentBorrowOrder, ReagentReturnRecord


class BorrowCase(inv_tests.InventoryCase):
    """The plan factory and the references helper, without a bottle: the
    suite shares one database, and a second test class building its own
    anhydride bottle would double the orders a plan makes."""

    def references(self):
        from app.db import SessionLocal
        from app.models import ChemicalReference
        with SessionLocal() as s:
            for cas, _formula in chem_tests.REFERENCES:
                for ref in s.query(ChemicalReference).filter_by(cas=cas).all():
                    s.delete(ref)
            s.flush()
            for cas, formula in chem_tests.REFERENCES:
                s.add(ChemicalReference(name=cas, cas=cas, formula=formula,
                                        molecular_weight=0.0, mw_source="manual"))
            s.commit()

    def make_plan(self, title: str = "领用流方案") -> int:
        data = {"title": title, "kind": "synthesis",
                "reaction": chem_tests.REACTION, "reagents": chem_tests.REAGENTS,
                "weighed": chem_tests.WEIGHED, "product_cas": chem_tests.ASPIRIN,
                "status": "active"}
        r = self.a.post("/chem-experiments", data=data)
        self.assertEqual(r.status_code, 302)
        return one("select max(id) from chem_experiment where title=?", title)

    def borrow_from(self, plan: int, client=None) -> object:
        return self.post(client or self.a, f"/chem-experiments/{plan}/borrow")

    def anhydride_bottles(self) -> int:
        """How many available anhydride bottles the shared database has:
        other test files' fixtures make their own, so the count is what
        the flow actually sees, not what this class built."""
        from app.db import SessionLocal
        from app import chemical_experiments as plans
        with SessionLocal() as s:
            return sum(1 for b in plans.bottles_for(s, chem_tests.ANHYDRIDE) if b["available"])


class WithABottle(BorrowCase):
    """One bottle of the anhydride on the shelf — the lab's whole stock
    of it for these tests. A reagent bottle, the preset whose status
    word list has "in use" for a signed-out one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chems = cls.new_module(cls.a, "chemical_reagents")
        cls.bottle = cls.make_item(cls.a, cls.chems, "醋酸酐 500 mL", attr_cas=chem_tests.ANHYDRIDE,
                                   attr_mw="102.09", attr_purity="99", status="in stock",
                                   attr_quantity="500", attr_unit="mL")

    def setUp(self):
        super().setUp()
        # These tests drive the same shelf several times over. Now that a
        # bottle may only be signed out when it is on the shelf, each starts
        # with every reagent bottle back in stock — the state the previous
        # test left behind is not the subject of the next one.
        execute("update chem_bottle set state='in_stock' where state <> 'in_stock'")
        execute("update inventory_items set status='in stock' where status='in use' "
                "and module_id_fk in (select id from inventory_modules where kind='chemical_reagents')")


class Pages(BorrowCase):
    def test_the_borrow_page_opens(self):
        self.get_ok(self.a, "/chem-experiments/borrows")
        self.assertIn("试剂领用", self.get_ok(self.a, "/chem-experiments/borrows"))

    def test_the_plan_page_offers_the_borrow_button(self):
        plan = self.make_plan()
        html = self.get_ok(self.a, f"/chem-experiments/{plan}")
        self.assertIn("生成领用单", html)


class TheFlow(WithABottle):
    def test_from_plan_reports_what_it_made_and_skipped(self):
        """The service's own answer: one order per available bottle, the
        substances with none named as skipped, the controlled count."""
        from app.db import SessionLocal
        from app.models import ChemicalExperiment
        plan = self.make_plan()
        bottles = self.anhydride_bottles()
        with SessionLocal() as s:
            before = one("select count(*) from chem_borrow_order")
            made = reagent_workflow.from_plan(s, s.get(ChemicalExperiment, plan), self.admin)
            s.commit()
        self.assertEqual(len(made["made"]), bottles)          # one order per bottle
        self.assertEqual(made["pending"], bottles)            # all of it a drug precursor
        self.assertIn("水杨酸", made["skipped"])              # the acid has no bottle
        self.assertEqual(one("select count(*) from chem_borrow_order"), before + bottles)

    def test_a_plan_becomes_an_order_per_bottle(self):
        plan = self.make_plan()
        bottles = self.anhydride_bottles()
        before = one("select count(*) from chem_borrow_order")
        r = self.borrow_from(plan)
        self.assertFlash(r, "领用单")
        self.assertIn("待审批", r.get_data(as_text=True))     # the anhydride is controlled
        self.assertEqual(one("select count(*) from chem_borrow_order"), before + bottles)
        # The newest order: the anhydride's bottle, the plan's purpose.
        values = row("select bottle_id, requester, quantity, unit, purpose, experiment_name "
                     "from chem_borrow_order order by id desc limit 1")
        self.assertEqual(values[1], self.admin)
        self.assertEqual(values[3], "g")
        self.assertIn("领用流方案", values[4])
        self.assertEqual(values[5], "领用流方案")
        # The order carries the next number in the flow's own sequence.
        self.assertEqual(one("select number from chem_borrow_order order by id desc limit 1"),
                         one("select max(number) from chem_borrow_order"))

    def test_a_controlled_bottle_is_created_pending_and_says_so(self):
        plan = self.make_plan()
        r = self.borrow_from(plan)
        self.assertFlash(r, "待审批")
        self.assertEqual(one("select status from chem_borrow_order order by id desc limit 1"),
                         "pending")
        # The page shows the controlled badge and the catalogue class.
        html = self.get_ok(self.a, "/chem-experiments/borrows")
        self.assertIn("drug precursor", html)

    def test_the_borrower_may_not_approve_their_own_order(self):
        plan = self.make_plan()
        self.borrow_from(plan, client=self.m)          # the member asks
        order = one("select max(id) from chem_borrow_order where requester=?", self.member)
        r = self.post(self.m, f"/chem-experiments/borrows/{order}/decide",
                      data={"decision": "approve"})
        self.assertFlash(r, "申请人不能审批")
        self.assertEqual(one("select status from chem_borrow_order where id=?", order), "pending")
        # Another member may: the borrower is never the approver, an
        # outsider may be.
        self.post(self.o, f"/chem-experiments/borrows/{order}/decide",
                  data={"decision": "approve"})
        values = row("select status, approver from chem_borrow_order where id=?", order)
        self.assertEqual((values[0], values[1]), ("approved", self.other))

    def test_an_approved_order_is_signed_out_and_the_bottle_is_in_use(self):
        plan = self.make_plan()
        self.borrow_from(plan)
        order = one("select max(id) from chem_borrow_order")
        self.post(self.o, f"/chem-experiments/borrows/{order}/decide",
                  data={"decision": "approve"})
        r = self.post(self.a, f"/chem-experiments/borrows/{order}/sign-out")
        self.assertFlash(r, "已领出")
        values = row("select status from chem_borrow_order where id=?", order)
        self.assertEqual(values[0], "borrowed")
        bottle_status = one("select status from inventory_items where id=?",
                            one("select bottle_id from chem_borrow_order where id=?", order))
        self.assertEqual(bottle_status, "in use")

    def test_the_return_writes_the_opening_date_and_frees_the_bottle(self):
        plan = self.make_plan()
        self.borrow_from(plan)
        order = one("select max(id) from chem_borrow_order")
        self.post(self.o, f"/chem-experiments/borrows/{order}/decide",
                  data={"decision": "approve"})
        self.post(self.a, f"/chem-experiments/borrows/{order}/sign-out")
        r = self.post(self.a, f"/chem-experiments/borrows/{order}/return",
                      data={"returned": "480", "loss": "20", "outcome": "partially_returned",
                            "remark": "洒了一点"})
        self.assertFlash(r, "已归还")
        values = row("select status from chem_borrow_order where id=?", order)
        self.assertEqual(values[0], "returned")
        bottle_id = one("select bottle_id from chem_borrow_order where id=?", order)
        record = row("select quantity, loss, outcome, remark from chem_return_record "
                     "where borrow_id=?", order)
        self.assertEqual((record[0], record[1], record[2]), (480.0, 20.0, "partially_returned"))
        self.assertEqual(record[3], "洒了一点")
        # The day it was first opened is on the bottle's attrs, and the
        # bottle is back in stock.
        attrs = one("select attrs from inventory_items where id=?", bottle_id)
        self.assertIn(date.today().isoformat(), attrs)
        self.assertEqual(one("select status from inventory_items where id=?", bottle_id), "in stock")

    def test_a_return_needs_a_signed_out_order(self):
        plan = self.make_plan()
        self.borrow_from(plan)
        order = one("select max(id) from chem_borrow_order")
        r = self.post(self.a, f"/chem-experiments/borrows/{order}/return", data={"returned": "1"})
        self.assertFlash(r, "只有已领出")
        self.assertEqual(one("select status from chem_borrow_order where id=?", order), "pending")

    def test_a_decided_order_cannot_be_decided_again(self):
        plan = self.make_plan()
        self.borrow_from(plan)
        order = one("select max(id) from chem_borrow_order")
        self.post(self.o, f"/chem-experiments/borrows/{order}/decide",
                  data={"decision": "reject"})
        r = self.post(self.a, f"/chem-experiments/borrows/{order}/decide",
                      data={"decision": "approve"})
        self.assertFlash(r, "已经处理过")
        self.assertEqual(one("select status from chem_borrow_order where id=?", order), "rejected")
