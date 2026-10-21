"""The notebook Reaction block's server side (app/lab_notebook.py
reaction_substances and reaction_balance): a CAS number completed from the
chemical references or a bottle in a Chemicals database, a name with no
CAS number, the check digit's verdict on a typo, and whether the equation
balances.

The worked example is the aspirin synthesis a first-year class does:
salicylic acid (69-72-7) and acetic anhydride (108-24-7) make aspirin
(50-78-6) and acetic acid (64-19-7).
"""
from __future__ import annotations

import json

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import *  # noqa: F401,F403
from tests import test_inventory as inv_tests

from app.models import ChemicalReference

SALICYLIC = "69-72-7"       # C7H6O3, 138.121
ANHYDRIDE = "108-24-7"      # C4H6O3, 102.089 — a drug precursor: 易制毒
ASPIRIN = "50-78-6"         # C9H8O4, 180.159
ACETIC = "64-19-7"          # C2H4O2, 60.052

# A well-formed CAS number nothing knows (its check digit agrees).
UNKNOWN = "123-45-5"
# The same with the check digit wrong: a typo finds the wrong substance.
TYPO = "123-45-6"

REFERENCES = [(SALICYLIC, "水杨酸", "C7H6O3"), (ANHYDRIDE, "醋酸酐", "C4H6O3"),
              (ASPIRIN, "阿司匹林", "C9H8O4"), (ACETIC, "乙酸", "C2H4O2")]


class ReactionBlockCase(inv_tests.InventoryCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chems = cls.new_module(cls.a, "chemicals")
        # A bottle of the anhydride on the shelf; the acid has none.
        cls.bottle = cls.make_item(cls.a, cls.chems, "醋酸酐 500 mL", attr_cas=ANHYDRIDE,
                                   attr_mw="102.09", status="in stock")

    def references(self):
        """The references the block reads. A test that counts rows clears
        them first: the suite shares one database, so another test may have
        left its own behind."""
        from app.db import SessionLocal
        with SessionLocal() as s:
            for _cas, _name, _formula in REFERENCES:
                for ref in s.query(ChemicalReference).filter_by(cas=_cas).all():
                    s.delete(ref)
            s.flush()
            for cas, name, formula in REFERENCES:
                s.add(ChemicalReference(name=name, cas=cas, formula=formula,
                                        molecular_weight=0.0, mw_source="manual"))
            s.commit()

    def no_references(self):
        from app.db import SessionLocal
        with SessionLocal() as s:
            for _cas, _name, _formula in REFERENCES:
                for ref in s.query(ChemicalReference).filter_by(cas=_cas).all():
                    s.delete(ref)
            s.commit()

    def solve(self, **payload):
        r = self.m.post("/notebook/api/reaction", data=json.dumps(payload),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def equation(self, acid_coef=1):
        """The aspirin equation, the acid's coefficient as the plan typed it."""
        return {"reactants": [{"cas": SALICYLIC, "coef": acid_coef}, {"cas": ANHYDRIDE, "coef": 1}],
                "products": [{"cas": ASPIRIN, "coef": 1}, {"cas": ACETIC, "coef": 1}]}


class Substances(ReactionBlockCase):
    def test_a_cas_number_is_completed_from_the_references(self):
        self.references()
        got = self.solve(cas_list=[SALICYLIC])
        acid = [s for s in got["substances"] if s["cas"] == SALICYLIC][0]
        self.assertEqual((acid["name"], acid["formula"], acid["source"]), ("水杨酸", "C7H6O3", "reference"))
        self.assertAlmostEqual(acid["mw"], 138.12, places=1)   # from the formula
        self.assertTrue(acid["cas_valid"])

    def test_a_bottle_in_the_chemicals_database_speaks_for_a_cas_number(self):
        self.no_references()
        got = self.solve(cas_list=[ANHYDRIDE])
        bottle = [s for s in got["substances"] if s["cas"] == ANHYDRIDE][0]
        self.assertEqual((bottle["name"], bottle["source"]), ("醋酸酐 500 mL", "inventory"))
        self.assertAlmostEqual(bottle["mw"], 102.09, places=2)
        self.assertTrue(bottle["cas_valid"])

    def test_a_cas_number_the_records_do_not_know_has_no_weight_and_says_so(self):
        self.no_references()
        got = self.solve(cas_list=[UNKNOWN])
        unknown = [s for s in got["substances"] if s["cas"] == UNKNOWN][0]
        self.assertEqual((unknown["name"], unknown["formula"], unknown["mw"]), ("", "", None))
        self.assertTrue(unknown["cas_valid"])

    def test_a_typo_in_a_cas_number_is_flagged(self):
        got = self.solve(cas_list=[TYPO])
        typo = [s for s in got["substances"] if s["cas"] == TYPO][0]
        self.assertFalse(typo["cas_valid"])

    def test_a_formula_the_row_typed_is_weighed_by_chemlib(self):
        self.no_references()
        # A formula with no CAS number to hang it on comes to nothing.
        got = self.solve(cas_list=[], reactants=[{"cas": "", "coef": 1, "name": "", "formula": ""}])
        self.assertEqual([s for s in got["substances"] if s["mw"]], [])
        got = self.solve(cas_list=[ASPIRIN],
                         reactants=[{"cas": ASPIRIN, "coef": 1, "name": "", "formula": "C9H8O4"}])
        aspirin = [s for s in got["substances"] if s["cas"] == ASPIRIN][0]
        self.assertAlmostEqual(aspirin["mw"], 180.16, places=1)
        self.assertEqual(aspirin["source"], "formula")

    def test_a_name_with_no_cas_number_is_completed_from_the_references(self):
        self.references()
        got = self.solve(reactants=[{"cas": "", "coef": 1, "name": "水杨酸", "formula": ""}])
        named = [s for s in got["substances"] if s["name"] == "水杨酸"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["cas"], SALICYLIC)
        self.assertAlmostEqual(named[0]["mw"], 138.12, places=1)


class Balance(ReactionBlockCase):
    def test_a_balanced_equation_conserves_every_element(self):
        self.references()
        got = self.solve(check=True, **self.equation())
        self.assertTrue(got["balance"]["checked"], got["balance"])
        self.assertEqual(got["balance"]["problems"], [])

    def test_an_unbalanced_equation_names_the_elements_that_do_not_conserve(self):
        self.references()
        # The acid at two, as the plans' worked example types it: carbon and
        # hydrogen no longer balance.
        got = self.solve(check=True, **self.equation(acid_coef=2))
        self.assertTrue(got["balance"]["checked"])
        problems = " ".join(got["balance"]["problems"])
        self.assertIn("C:", problems)
        self.assertIn("H:", problems)

    def test_a_formula_nobody_knows_stops_the_check_and_says_which(self):
        self.no_references()
        got = self.solve(check=True, **self.equation())
        self.assertFalse(got["balance"]["checked"])
        self.assertEqual(set(got["balance"]["missing"]),
                         {SALICYLIC, ANHYDRIDE, ASPIRIN, ACETIC})

    def test_a_coefficient_that_is_not_a_number_is_said_plainly(self):
        self.references()
        equation = self.equation()
        equation["reactants"][0]["coef"] = "两"
        got = self.solve(check=True, **equation)
        self.assertFalse(got["balance"]["checked"])
        self.assertTrue(any("coefficient" in p for p in got["balance"]["problems"]))

    def test_no_check_without_an_equation(self):
        self.references()
        got = self.solve(cas_list=[SALICYLIC])
        self.assertIsNone(got["balance"])


class AsATemplate(ReactionBlockCase):
    def test_the_equation_stays_and_this_runs_results_go(self):
        from app.lab_notebook import structure_only
        block = {"name": "阿司匹林合成", "notes": "80 °C, 20 min",
                 "sides": [
                     {"side": "reactant", "cas": SALICYLIC, "name": "水杨酸", "coef": "2",
                      "mw": "138.121", "role": "reactant", "weighed": "1.381", "unit": "g"},
                     {"side": "product", "cas": ASPIRIN, "name": "阿司匹林", "coef": "1", "mw": "180.159"}],
                 "product": 1, "actual": "0.72",
                 "log": [{"at": "2026-10-21T10:00:00", "grams": 0.72, "percent": 79.9}]}
        body = f"## Reaction\n\n```reaction\n{json.dumps(block, ensure_ascii=False)}\n```\n"
        kept = json.loads(structure_only(body).split("```reaction\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual((kept["name"], kept["notes"]), ("阿司匹林合成", "80 °C, 20 min"))
        self.assertEqual([r["cas"] for r in kept["sides"]], [SALICYLIC, ASPIRIN])
        self.assertEqual(kept["sides"][0]["coef"], "2")            # the equation stays
        self.assertNotIn("weighed", kept["sides"][0])              # this run's weighings go
        self.assertNotIn("actual", kept)                           # and the mass it came to
        self.assertNotIn("log", kept)                              # and the yields recorded
