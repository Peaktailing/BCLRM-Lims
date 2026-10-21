"""Tests for app/chemlib.py: formulas, molecular weights, reactions.

Values a chemist checks by eye: glucose 180.156, copper sulfate pentahydrate
249.677, water from hydrogen and oxygen, aspirin from salicylic acid.
"""
from __future__ import annotations

import pytest

from app.chemlib import (FormulaError, Reaction, balance_check, cas_is_valid,
                         equivalents, hill_formula, limiting_reagent,
                         molecular_weight, parse_formula, percent_yield,
                         theoretical_yield)


class TestParseFormula:
    def test_plain(self):
        assert parse_formula("H2O") == {"H": 2, "O": 1}

    def test_two_letter_symbol(self):
        assert parse_formula("NaCl") == {"Na": 1, "Cl": 1}

    def test_group_with_count(self):
        assert parse_formula("(NH4)2SO4") == {"N": 2, "H": 8, "S": 1, "O": 4}

    def test_hydrate_dot(self):
        assert parse_formula("CuSO4·5H2O") == {"Cu": 1, "S": 1, "O": 9, "H": 10}

    def test_hydrate_leading_count(self):
        # "2H2O" after the dot means two waters per formula unit
        assert parse_formula("Na2CO3.10H2O") == {"Na": 2, "C": 1, "O": 13, "H": 20}

    def test_fractional_count(self):
        assert parse_formula("Fe0.5O") == {"Fe": 0.5, "O": 1}

    def test_hydrate_ascii_dot(self):
        # a catalogue that writes the hydrate with a plain full stop
        assert parse_formula("CuSO4.5H2O") == parse_formula("CuSO4·5H2O")

    def test_decimal_not_a_hydrate(self):
        # "Fe0" is not a real unit (nothing in it), so the first dot stays
        # decimal; the second one has a real unit on both sides: a hydrate
        assert parse_formula("Fe0.5O.2H2O") == {"Fe": 0.5, "O": 3.0, "H": 4.0}

    def test_empty(self):
        with pytest.raises(FormulaError):
            parse_formula("")

    def test_unknown_symbol(self):
        with pytest.raises(FormulaError, match="known element"):
            parse_formula("Xx3")

    def test_unbalanced_bracket(self):
        with pytest.raises(FormulaError, match="bracket"):
            parse_formula("((NH4)2SO4")

    def test_stray_character(self):
        with pytest.raises(FormulaError):
            parse_formula("H2-O")


class TestMolecularWeight:
    @pytest.mark.parametrize("formula,expected", [
        ("H2O", 18.015),
        ("C6H12O6", 180.156),
        ("C2H5OH", 46.069),
        ("NaCl", 58.44),
        ("(NH4)2SO4", 132.134),
        ("KMnO4", 158.032),
        ("CuSO4·5H2O", 249.677),
        ("C9H8O4", 180.159),          # aspirin
        ("C7H6O3", 138.1217),         # salicylic acid
        ("C4H6O3", 102.089),          # acetic anhydride
    ])
    def test_known(self, formula, expected):
        assert molecular_weight(formula) == pytest.approx(expected, abs=5e-4)


class TestHillFormula:
    def test_order(self):
        # no carbon: everything alphabetical, H included
        assert hill_formula({"H": 10, "Cu": 1, "O": 9, "S": 1}) == "H10CuO9S"

    def test_carbon_first(self):
        assert hill_formula({"O": 2, "C": 1, "H": 4}) == "CH4O2"

    def test_single_atoms_drop_the_one(self):
        assert hill_formula({"C": 1, "H": 4}) == "CH4"


WATER = Reaction(reactants=[("7732-18-5", 2)], products=[])   # filled per test
WEIGHTS = {"H2": 2.016, "O2": 31.998, "H2O": 18.015,
           "C7H6O3": 138.121, "C4H6O3": 102.089, "C9H8O4": 180.159,
           "C2H4O2": 60.052}
FORMULAS = {"H2": "H2", "O2": "O2", "H2O": "H2O",
            "C7H6O3": "C7H6O3", "C4H6O3": "C4H6O3", "C9H8O4": "C9H8O4",
            "C2H4O2": "C2H4O2"}


def water_reaction() -> Reaction:
    return Reaction(reactants=[("H2", 2), ("O2", 1)], products=[("H2O", 2)])


def aspirin_reaction() -> Reaction:
    # salicylic acid + acetic anhydride → aspirin + acetic acid
    return Reaction(reactants=[("C7H6O3", 1), ("C4H6O3", 1)],
                    products=[("C9H8O4", 1), ("C2H4O2", 1)])


class TestBalanceCheck:
    def test_balanced(self):
        assert balance_check(water_reaction(), WEIGHTS, FORMULAS) == []

    def test_unbalanced(self):
        bad = Reaction(reactants=[("H2", 2), ("O2", 1)], products=[("H2O", 1)])
        problems = balance_check(bad, WEIGHTS, FORMULAS)
        assert problems == ["H: 4 in, 2 out", "O: 2 in, 1 out"]

    def test_aspirin(self):
        assert balance_check(aspirin_reaction(), WEIGHTS, FORMULAS) == []

    def test_missing_formula(self):
        with pytest.raises(FormulaError, match="no formula"):
            balance_check(water_reaction(), WEIGHTS, {})


class TestLimitingReagent:
    def test_hydrogen_runs_out(self):
        # 0.5 g H2 = 248 mmol, needs 124 mmol O2 = 3.97 g; 5 g is plenty
        limiting, moles = limiting_reagent(water_reaction(), {"H2": 0.5, "O2": 5.0}, WEIGHTS)
        assert limiting == "H2"
        assert moles == pytest.approx(0.24802, abs=1e-4)

    def test_oxygen_runs_out(self):
        # 0.5 g O2 = 15.6 mmol; 2 g H2 = 992 mmol needs 496 mmol O2
        limiting, _moles = limiting_reagent(water_reaction(), {"H2": 2.0, "O2": 0.5}, WEIGHTS)
        assert limiting == "O2"

    def test_unweighed_reactant(self):
        with pytest.raises(FormulaError, match="not weighed"):
            limiting_reagent(water_reaction(), {"H2": 0.5}, WEIGHTS)

    def test_unknown_weight(self):
        with pytest.raises(FormulaError, match="molecular weight"):
            limiting_reagent(water_reaction(), {"H2": 0.5, "O2": 1.0}, {})


class TestEquivalents:
    def test_basis_is_one(self):
        # 1.381 g salicylic acid ≈ 10.0 mmol; 1.021 g anhydride ≈ 10.0 mmol
        # (the 0.03 % slack is the atomic weights' four decimals)
        eq = equivalents(aspirin_reaction(), "C7H6O3",
                         {"C7H6O3": 1.381, "C4H6O3": 1.021}, WEIGHTS)
        assert eq["C7H6O3"] == pytest.approx(1.0)
        assert eq["C4H6O3"] == pytest.approx(1.0, abs=2e-3)

    def test_excess_shows_above_one(self):
        eq = equivalents(aspirin_reaction(), "C7H6O3",
                         {"C7H6O3": 1.381, "C4H6O3": 2.042}, WEIGHTS)
        assert eq["C4H6O3"] == pytest.approx(2.0, abs=4e-3)


class TestTheoreticalYield:
    def test_aspirin_from_ten_mmol(self):
        # 1.381 g salicylic acid = 10.0 mmol; 1:1 → 10 mmol aspirin = 1.8016 g
        out = theoretical_yield(aspirin_reaction(), "C9H8O4",
                                {"C7H6O3": 1.381, "C4H6O3": 1.530}, WEIGHTS)
        assert out["limiting"] == "C7H6O3"
        assert out["product_grams"] == pytest.approx(1.8016, abs=1e-3)

    def test_unknown_product(self):
        with pytest.raises(FormulaError, match="not a product"):
            theoretical_yield(aspirin_reaction(), "NaCl",
                              {"C7H6O3": 1.381, "C4H6O3": 1.021}, WEIGHTS)


class TestPercentYield:
    def test_normal(self):
        assert percent_yield(1.44, 1.80)["percent"] == pytest.approx(80.0)

    def test_over_hundred_warns(self):
        out = percent_yield(2.0, 1.8)
        assert out["percent"] > 100
        assert "over the theoretical" in out["warning"]

    def test_very_low_warns(self):
        assert "very low" in percent_yield(0.05, 1.8)["warning"]

    def test_zero_theoretical(self):
        with pytest.raises(FormulaError):
            percent_yield(1.0, 0)


class TestCasNumber:
    # A CAS number's last digit is a check digit: the ones before it, read
    # right to left, each times its position, summed, mod 10. A controlled
    # substance check that misses on a typo is worse than none.
    def test_well_known_numbers(self):
        for cas in ("7732-18-5", "7647-14-5", "7447-40-7", "77-86-1",
                    "60-00-4", "50-99-7", "57-50-1", "7365-45-9",
                    "10043-52-4", "7786-30-3", "64-17-5", "108-88-3"):
            assert cas_is_valid(cas), cas

    def test_a_changed_check_digit_is_refused(self):
        assert not cas_is_valid("7732-18-6")
        assert not cas_is_valid("50-99-8")
        assert not cas_is_valid("7647-14-4")

    def test_malformed(self):
        for cas in ("", "   ", "7732-18", "7732-188", "77-186-5", "773-18-5",
                    "abc-de-f", "7732_18_5", "7732-18-5x", None):
            assert not cas_is_valid(cas), cas

    def test_surrounding_space_is_forgiven(self):
        assert cas_is_valid("  7732-18-5  ")
