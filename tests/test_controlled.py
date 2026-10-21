"""The controlled substances list (app/controlled.py): matching by CAS
number, name or alias, and the approval a borrow order for one needs.
The seed is checked too — a CAS number that fails its check digit would
match nothing and quietly let a bottle through.
"""
from __future__ import annotations

import unittest

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import *  # noqa: F401,F403
from tests.base import one

from app import controlled
from app.chemlib import cas_is_valid


class TheSeed(unittest.TestCase):
    def test_every_cas_number_in_the_seed_passes_its_check_digit(self):
        for name, _aliases, cas, _type, _note in controlled.DEFAULT_CONTROLLED:
            self.assertTrue(cas_is_valid(cas), f"{name} ({cas})")

    def test_the_seed_is_seeded_on_a_new_database(self):
        count = one("select count(*) from controlled_list")
        self.assertEqual(count, len(controlled.DEFAULT_CONTROLLED))
        row = one("select dangerous_type from controlled_list where cas_number='67-64-1'")
        self.assertEqual(row, "drug precursor")

    def test_the_seed_covers_the_four_chinese_catalogues(self):
        types = {t for _n, _a, _c, t, _note in controlled.DEFAULT_CONTROLLED}
        self.assertEqual(types, {"drug precursor", "explosive precursor",
                                 "highly toxic", "narcotic or psychotropic"})


class Matching(unittest.TestCase):
    def setUp(self):
        from app.db import SessionLocal
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()

    def entry(self, **kw):
        return controlled.match(self.session, **kw)

    def test_the_cas_number_is_the_identity(self):
        # 丙酮 is on the list by CAS number whatever it is called here.
        entry = self.entry(cas="67-64-1")
        self.assertEqual(entry.chemical_name, "丙酮")
        self.assertEqual(entry.dangerous_type, "drug precursor")

    def test_a_cas_number_not_on_the_list_is_none(self):
        self.assertIsNone(self.entry(cas="7732-18-5"))     # water

    def test_a_name_matches_without_spaces_or_case(self):
        for name in ("丙酮", " 丙酮 ", "acetone", "ACETONE", "Dimethyl Ketone"):
            self.assertIsNotNone(self.entry(name=name), name)

    def test_an_alias_matches(self):
        # 高锰酸钾 is asked for as KMnO4 and as PP粉 as often as by name.
        for alias in ("KMnO4", "kmno4", "PP粉"):
            entry = self.entry(name=alias)
            self.assertIsNotNone(entry, alias)
            self.assertEqual(entry.cas_number, "7722-64-7")

    def test_a_name_that_only_contains_a_listed_name_is_not_a_match(self):
        self.assertIsNone(self.entry(name="丙酮废液"))       # waste, not the substance

    def test_no_cas_and_no_name_is_none(self):
        self.assertIsNone(self.entry(cas="", name=""))

    def test_a_cas_number_that_misses_still_falls_back_to_the_name(self):
        # A bottle named 丙酮 whose CAS number is not the listed one (an
        # isotopologue, a mistyped digit) still matches by name: a check
        # that is about what leaves the shelf asks one approval too many
        # rather than let a bottle through.
        entry = self.entry(cas="67-64-2", name="丙酮")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.cas_number, "67-64-1")


class TheApprovalABorrowOrderNeeds(unittest.TestCase):
    def setUp(self):
        from app.db import SessionLocal
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()

    def state(self, **kw):
        return controlled.borrow_order_state(self.session, **kw)

    def test_a_listed_cas_number_makes_the_order_wait(self):
        state = self.state(cas="151-50-8")               # 氰化钾
        self.assertTrue(state["controlled"])
        self.assertEqual(state["type"], "highly toxic")
        self.assertEqual(state["status"], "pending")
        self.assertFalse(state["self_approval"])
        self.assertIn("CAS number", state["reason"])

    def test_a_listed_name_makes_the_order_wait(self):
        state = self.state(name="氰化钾")
        self.assertTrue(state["controlled"])
        self.assertIn("name", state["reason"])

    def test_a_bottle_marked_controlled_waits_even_if_the_list_has_not_caught_up(self):
        state = self.state(cas="999-99-9", name="Something new", bottle_controlled=True)
        self.assertTrue(state["controlled"])
        self.assertEqual(state["status"], "pending")
        self.assertFalse(state["self_approval"])

    def test_an_unlisted_substance_is_the_labs_own_business(self):
        state = self.state(cas="7732-18-5", name="Water")
        self.assertFalse(state["controlled"])
        self.assertEqual(state["status"], "")
        self.assertTrue(state["self_approval"])

    def test_needs_approval_and_controlled_type_of(self):
        self.assertTrue(controlled.needs_approval("67-64-1", self.session))
        self.assertEqual(controlled.controlled_type_of("67-64-1", self.session), "drug precursor")
        self.assertFalse(controlled.needs_approval("7732-18-5", self.session))
        self.assertIsNone(controlled.controlled_type_of("7732-18-5", self.session))
