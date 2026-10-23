"""Chemical experiments (app/chemical_experiments.py and its routes): the
plan typed as lines, the chain off the CAS numbers, and the yield.

The worked example is the aspirin synthesis a first-year class does:
salicylic acid (69-72-7) and acetic anhydride (108-24-7) make aspirin
(50-78-6) and acetic acid (64-19-7). 1.381 g of acid is 10 mmol, the
anhydride is 1.021 g, the acid is the limiting reagent, the flask should
give 0.90 g of aspirin.
"""
from __future__ import annotations

import json

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import *  # noqa: F401,F403
from tests.base import one
from tests import test_inventory as inv_tests

from app import chemical_experiments as plans
from app.models import ChemicalExperiment, ChemicalReference, ReagentDemand

# The aspirin synthesis, in the CAS numbers the plan is typed with.
SALICYLIC = "69-72-7"       # C7H6O3, 138.121
ANHYDRIDE = "108-24-7"      # C4H6O3, 102.089 — a drug precursor: 易制毒
ASPIRIN = "50-78-6"         # C9H8O4, 180.159
ACETIC = "64-19-7"          # C2H4O2, 60.052

REACTION = f"{SALICYLIC} 2\n{ANHYDRIDE} 1\n--\n{ASPIRIN} 1\n{ACETIC} 1"
REAGENTS = f"{SALICYLIC} 水杨酸 reactant\n{ANHYDRIDE} 醋酸酐 reactant"
WEIGHED = f"{SALICYLIC} 1.381\n{ANHYDRIDE} 1.021"

# The references the arithmetic reads; the lab has no reference of its own
# for these until a plan registers one.
REFERENCES = [(SALICYLIC, "C7H6O3"), (ANHYDRIDE, "C4H6O3"),
              (ASPIRIN, "C9H8O4"), (ACETIC, "C2H4O2")]


class ChemicalExperimentCase(inv_tests.InventoryCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chems = cls.new_module(cls.a, "chemicals")
        # A bottle of the anhydride on the shelf; the acid has none.
        cls.bottle = cls.make_item(cls.a, cls.chems, "醋酸酐 500 mL", attr_cas=ANHYDRIDE,
                                   attr_mw="102.09", attr_purity="99", status="in stock",
                                   attr_quantity="500", attr_unit="mL")

    def references(self):
        """The references the arithmetic reads. A test that counts rows or
        checks a name clears them first: the suite shares one database, so
        another test may have left its own behind."""
        from app.db import SessionLocal
        with SessionLocal() as s:
            for cas, _formula in REFERENCES:
                for ref in s.query(ChemicalReference).filter_by(cas=cas).all():
                    s.delete(ref)
            s.flush()
            for cas, formula in REFERENCES:
                s.add(ChemicalReference(name=cas, cas=cas, formula=formula,
                                        molecular_weight=0.0, mw_source="manual"))
            s.commit()

    def no_references(self):
        from app.db import SessionLocal
        with SessionLocal() as s:
            for cas, _formula in REFERENCES:
                for ref in s.query(ChemicalReference).filter_by(cas=cas).all():
                    s.delete(ref)
            s.commit()

    def make_plan(self, title: str | None = None, **extra) -> int:
        data = {"title": title or "阿司匹林合成", "kind": "synthesis",
                "reaction": REACTION, "reagents": REAGENTS, "weighed": WEIGHED,
                "product_cas": ASPIRIN, "status": "template"}
        data.update(extra)
        r = self.a.post("/chem-experiments", data=data)
        return one("select max(id) from chem_experiment where title=?", data["title"])


class Pages(ChemicalExperimentCase):
    def test_the_pages_open(self):
        self.get_ok(self.a, "/chem-experiments")
        self.get_ok(self.a, "/chem-experiments/new")

    def test_a_plan_needs_both_sides(self):
        r = self.post(self.a, "/chem-experiments", data={"title": "半拉方案", "reaction": "69-72-7 2"})
        self.assertEqual(one("select count(*) from chem_experiment where title=?", "半拉方案"), 0)
        self.assertFlash(r, "至少需要")

    def test_a_member_sees_the_pages_but_not_anothers_edit(self):
        plan = self.make_plan()
        self.get_ok(self.m, "/chem-experiments")
        html = self.get_ok(self.m, f"/chem-experiments/{plan}")
        self.assertIn('name="title"', html)                # the form is there, to read
        self.assertRegex(html, r'name="title"[^>]*\bdisabled\b')
        self.assertNotIn("保存方案", html)                   # and nothing to press

    def test_a_plan_is_created_and_its_parts_are_kept(self):
        plan = self.make_plan()
        values = row("select reaction_json, reagents_json, weighed_json, product_cas, status "
                  "from chem_experiment where id=?", plan)
        reaction_json, reagents_json, weighed_json, product_cas, status = values
        self.assertEqual(product_cas, ASPIRIN)
        self.assertEqual(status, "template")
        reaction = json.loads(reaction_json)
        self.assertEqual(reaction["reactants"], [[SALICYLIC, 2], [ANHYDRIDE, 1]])
        self.assertEqual(reaction["products"], [[ASPIRIN, 1], [ACETIC, 1]])
        self.assertEqual(len(json.loads(reagents_json)), 2)
        self.assertEqual(json.loads(weighed_json)[SALICYLIC], 1.381)

    def test_the_plan_page_shows_the_equation_and_the_weighed(self):
        plan = self.make_plan()
        html = self.get_ok(self.a, f"/chem-experiments/{plan}")
        self.assertIn(SALICYLIC, html)
        self.assertIn("1.381", html)


class TheChain(ChemicalExperimentCase):
    def test_stock_check_finds_the_bottle_and_the_controlled_class(self):
        self.references()
        plan = self.make_plan()
        from app.db import SessionLocal
        with SessionLocal() as s:
            stock = plans.stock_check(s, s.get(ChemicalExperiment, plan))
        by_cas = {row["cas"]: row for row in stock}
        acid, anhydride = by_cas[SALICYLIC], by_cas[ANHYDRIDE]
        self.assertFalse(acid["in_stock"])                 # the lab has no salicylic acid
        self.assertTrue(anhydride["in_stock"])             # the bottle is on the shelf
        self.assertTrue(anhydride["controlled"])           # 醋酸酐 is a drug precursor
        self.assertEqual(anhydride["controlled_type"], "drug precursor")
        self.assertFalse(acid["controlled"])

    def test_a_demand_is_made_for_what_the_lab_has_none_of(self):
        self.references()
        plan = self.make_plan()
        r = self.post(self.a, f"/chem-experiments/{plan}/demands")
        self.assertFlash(r, "已生成 1 条采购需求")
        values = row("select chemical_name, cas, status, purpose from chem_demand where cas=?", SALICYLIC)
        self.assertEqual(values[0], "水杨酸")
        self.assertEqual(values[2], "open")
        self.assertIn("阿司匹林合成", values[3])
        # Asking again does not duplicate it.
        self.post(self.a, f"/chem-experiments/{plan}/demands")
        self.assertEqual(one("select count(*) from chem_demand where cas=?", SALICYLIC), 1)


class TheArithmetic(ChemicalExperimentCase):
    def test_equivalents_limiting_reagent_and_theoretical_yield(self):
        self.references()
        plan = self.make_plan()
        from app.db import SessionLocal
        with SessionLocal() as s:
            got = plans.quantities(s, s.get(ChemicalExperiment, plan))
        self.assertTrue(got["ok"], got)
        self.assertEqual(got["limiting"], SALICYLIC)
        # The anhydride is the standard two equivalents: 10 mmol against
        # the acid's 5 mmol of reaction extent.
        self.assertAlmostEqual(got["equivalents"][ANHYDRIDE], 2.0, places=2)
        self.assertAlmostEqual(got["theoretical"]["product_grams"], 0.9008, places=3)

    def test_a_missing_molecular_weight_is_a_readable_answer(self):
        # No references: the plan says which CAS numbers to fill in first.
        self.no_references()
        plan = self.make_plan()
        from app.db import SessionLocal
        with SessionLocal() as s:
            got = plans.quantities(s, s.get(ChemicalExperiment, plan))
        self.assertFalse(got["ok"])
        self.assertEqual(set(got["unknown_cas"]), set(cas for cas, _f in REFERENCES))

    def test_the_yield_is_recorded_with_its_warning(self):
        self.references()
        plan = self.make_plan()
        r = self.post(self.a, f"/chem-experiments/{plan}/yield", data={"actual_grams": "0.72"})
        self.assertFlash(r, "79.9")
        values = row("select actual_yield_grams, yield_percent, status from chem_experiment where id=?", plan)
        self.assertEqual(values[0], 0.72)
        self.assertAlmostEqual(values[1], 79.9, places=1)
        self.assertEqual(values[2], "done")

    def test_a_yield_over_the_theoretical_value_warns(self):
        self.references()
        plan = self.make_plan()
        self.post(self.a, f"/chem-experiments/{plan}/yield", data={"actual_grams": "1.4"})
        warning = one("select yield_warning from chem_experiment where id=?", plan)
        self.assertIn("over the theoretical", warning)

    def test_a_yield_needs_a_number(self):
        self.references()
        plan = self.make_plan()
        r = self.post(self.a, f"/chem-experiments/{plan}/yield", data={"actual_grams": "很多"})
        self.assertFlash(r, "请填写实际产量")


class TheProduct(ChemicalExperimentCase):
    def test_the_product_joins_the_references(self):
        self.no_references()
        plan = self.make_plan()
        r = self.post(self.a, f"/chem-experiments/{plan}/product",
                      data={"cas": ASPIRIN, "formula": "C9H8O4", "name": "阿司匹林"})
        self.assertFlash(r, "已登记")
        values = row("select name, formula, molecular_weight, mw_source from chem_substance where cas=?", ASPIRIN)
        self.assertEqual((values[0], values[1]), ("阿司匹林", "C9H8O4"))
        self.assertAlmostEqual(values[2], 180.16, places=1)
        self.assertEqual(values[3], "formula")

    def test_registering_the_same_cas_twice_tops_up_rather_than_duplicates(self):
        self.post(self.a, f"/chem-experiments/{self.make_plan()}/product",
                  data={"cas": ASPIRIN, "formula": "C9H8O4", "name": "阿司匹林"})
        self.post(self.a, f"/chem-experiments/{self.make_plan('第二次')}/product",
                  data={"cas": ASPIRIN, "formula": "C9H8O4", "name": "阿司匹林"})
        self.assertEqual(one("select count(*) from chem_substance where cas=?", ASPIRIN), 1)


class Copies(ChemicalExperimentCase):
    def test_a_template_becomes_a_members_working_copy(self):
        plan = self.make_plan()
        r = self.m.post(f"/chem-experiments/{plan}/start")
        self.assertEqual(r.status_code, 302)
        copy_id = one("select max(id) from chem_experiment where created_by=?", self.member)
        self.assertIsNotNone(copy_id)
        self.assertNotEqual(copy_id, plan)
        values = row("select status, created_by, title from chem_experiment where id=?", copy_id)
        self.assertEqual((values[0], values[1]), ("active", self.member))
        # The template stays a template.
        self.assertEqual(one("select status from chem_experiment where id=?", plan), "template")
