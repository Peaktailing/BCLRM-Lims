"""Chemical calculations for the lab: formulas to molecular weights, and
reactions to limiting reagent, theoretical yield and percent yield.

Pure functions, no database, no Flask — the notebook's Formulation block
weighs and moles its way through a mixture (that lives in the browser);
this works out what a reaction makes from what was weighed. A teaching
lab's synthesis experiments (the chemical_experiments table) call it, and
so does anything that turns a formula into a number.

The atomic weights are the IUPAC standard ones (2021), abbreviated to the
elements a teaching or synthesis lab meets; an unknown symbol raises
FormulaError rather than guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# IUPAC standard atomic weights (2021), the elements a lab meets. Kept
# short on purpose: a formula with something missing is a typo to fix,
# not a weight to invent.
ATOMIC_WEIGHTS = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938,
    "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Tc": 97.0, "Ru": 101.07, "Rh": 102.91,
    "Pd": 106.42, "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71,
    "Sb": 121.76, "Te": 127.60, "I": 126.90, "Xe": 131.29, "Cs": 132.91,
    "Ba": 137.33, "La": 138.91, "Ce": 140.12, "Pr": 140.91, "Nd": 144.24,
    "Sm": 150.36, "Eu": 151.96, "Gd": 157.25, "Tb": 158.93, "Dy": 162.50,
    "Ho": 164.93, "Er": 167.26, "Yb": 173.05, "Lu": 174.97, "Hf": 178.49,
    "Ta": 180.95, "W": 183.84, "Re": 186.21, "Os": 190.23, "Ir": 192.22,
    "Pt": 195.08, "Au": 196.97, "Hg": 200.59, "Tl": 204.38, "Pb": 207.2,
    "Bi": 208.98, "Th": 232.04, "U": 238.03,
}


class FormulaError(ValueError):
    """A formula that could not be read: unknown symbol, empty, bad group."""


# An element is a capital then optional smalls; a count is digits with an
# optional decimal ("Fe0.5" in a non-stoichiometric oxide).
_ELEMENT = re.compile(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)")


def parse_formula(formula: str) -> dict[str, float]:
    """Element counts in a formula: "CuSO4·5H2O" → {"Cu": 1, "S": 1, "O": 9, "H": 10}.

    Reads what a catalogue writes: hydrates with a dot (· or .) and a
    leading count ("Na2CO3.10H2O"), groups in brackets with their count
    ("(NH4)2SO4"), fractional counts ("Fe0.5"). A dot is a hydrate dot
    only when both of its sides read as real, non-empty units — so the
    decimal point in "Fe0.5O" stays a decimal. Raises FormulaError on
    anything else.
    """
    text = (formula or "").strip()
    if not text:
        raise FormulaError("empty formula")
    if "·" in text or "•" in text:
        counts: dict[str, float] = {}
        for part in re.split(r"[·•]", text):
            for symbol, n in _read_one(part).items():
                counts[symbol] = counts.get(symbol, 0.0) + n
        return counts
    for i, ch in enumerate(text):
        if ch != ".":
            continue
        try:
            left, right = _read_one(text[:i]), _read_one(text[i + 1:])
        except FormulaError:
            continue
        if _all_present(left) and _all_present(right):
            return {symbol: left.get(symbol, 0.0) + right.get(symbol, 0.0)
                    for symbol in set(left) | set(right)}
    return _read_one(text)


def _all_present(counts: dict[str, float]) -> bool:
    """Every element in the unit is really there (counts above zero)."""
    return bool(counts) and all(n > 0 for n in counts.values())


def _read_one(formula: str) -> dict[str, float]:
    """One formula unit: elements, groups and fractional counts.

    An interpunct (·) never belongs to a single unit, so this refuses it;
    a full stop is read as a decimal point inside a count ("Fe0.5") —
    whether one is really a hydrate dot is parse_formula's call.
    """
    if "·" in formula or "•" in formula:
        raise FormulaError(f"an interpunct is not part of one unit: {formula!r}")
    counts: dict[str, float] = {}

    def add_group(group: str, multiplier: float) -> None:
        pos = 0
        for match in _ELEMENT.finditer(group):
            if match.start() != pos:
                raise FormulaError(f"cannot read {formula!r} at {group[pos:match.start()]!r}")
            symbol, count = match.group(1), match.group(2)
            if symbol not in ATOMIC_WEIGHTS:
                raise FormulaError(f"{symbol!r} is not a known element (in {formula!r})")
            counts[symbol] = counts.get(symbol, 0.0) + (float(count) if count else 1.0) * multiplier
            pos = match.end()
        if pos != len(group):
            raise FormulaError(f"cannot read {formula!r} at {group[pos:]!r}")

    def add_part(part: str) -> None:
        part = part.strip()
        if not part:
            raise FormulaError(f"empty part in {formula!r}")
        lead = re.match(r"^(\d+(?:\.\d+)?)(.*)$", part)
        multiplier = float(lead.group(1)) if lead else 1.0
        body = lead.group(2) if lead else part
        # Walk the body: brackets multiply what they hold, the rest is plain.
        depth = 0
        start = 0
        plain: list[str] = []
        for i, ch in enumerate(body):
            if ch == "(":
                if depth == 0:
                    plain.append(body[start:i])
                    start = i + 1
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    raise FormulaError(f"unbalanced bracket in {formula!r}")
                if depth == 0:
                    inner = body[start:i]
                    after = re.match(r"^(\d+(?:\.\d+)?)", body[i + 1:])
                    times = float(after.group(1)) if after else 1.0
                    add_group(inner, times)
                    start = i + 1 + (len(after.group(1)) if after else 0)
        if depth != 0:
            raise FormulaError(f"unbalanced bracket in {formula!r}")
        plain.append(body[start:])
        for chunk in plain:
            if chunk.strip():
                add_group(chunk, multiplier)

    add_part(formula)
    return counts


def molecular_weight(formula: str) -> float:
    """The molecular weight of a formula, in g/mol.

    >>> round(molecular_weight("C6H12O6"), 3)
    180.156
    >>> round(molecular_weight("CuSO4·5H2O"), 3)
    249.677
    """
    return round(sum(ATOMIC_WEIGHTS[symbol] * n for symbol, n in parse_formula(formula).items()), 4)


def hill_formula(counts: dict[str, float]) -> str:
    """Counts back to a formula, Hill order (C, H, then the rest alphabetical):
    what a newly made product gets registered as.
    """
    parts: list[str] = []
    for symbol in sorted(counts, key=lambda s: (s != "C", s != "H", s)):
        n = counts[symbol]
        text = f"{n:g}" if n != int(n) else str(int(n))
        parts.append(symbol + ("" if n == 1 else text))
    return "".join(parts)


@dataclass
class Reaction:
    """A reaction as the lab writes it: each side a list of (CAS, coefficient).

    The coefficients are the stoichiometric ones ("2 H2 + O2 → 2 H2O" is
    [("H2", 2), ("O2", 1)] → [("H2O", 2)]). A coefficient may be fractional.
    """

    reactants: list[tuple[str, float]] = field(default_factory=list)
    products: list[tuple[str, float]] = field(default_factory=list)

    def sides(self) -> tuple[dict[str, float], dict[str, float]]:
        return (dict(self.reactants), dict(self.products))


def _moles_of(cas: str, grams: float, weights: dict[str, float | None]) -> float:
    mw = weights.get(cas)
    if not mw:
        raise FormulaError(f"no molecular weight known for {cas!r}")
    return grams / mw


def balance_check(reaction: Reaction, weights: dict[str, float | None],
                  formulas: dict[str, str]) -> list[str]:
    """Elements that do not balance between the two sides, as readable lines.

    `weights` maps CAS → molecular weight, `formulas` CAS → formula. An
    empty list means the equation conserves every element.
    """
    left: dict[str, float] = {}
    right: dict[str, float] = {}
    for side, target in ((reaction.reactants, left), (reaction.products, right)):
        for cas, coefficient in side:
            formula = formulas.get(cas)
            if not formula:
                raise FormulaError(f"no formula known for {cas!r}")
            for symbol, n in parse_formula(formula).items():
                target[symbol] = target.get(symbol, 0.0) + n * coefficient
    problems = []
    for symbol in sorted(set(left) | set(right)):
        have, want = left.get(symbol, 0.0), right.get(symbol, 0.0)
        if abs(have - want) > 1e-6:
            problems.append(f"{symbol}: {have:g} in, {want:g} out")
    return problems


def limiting_reagent(reaction: Reaction, weighed: dict[str, float],
                     weights: dict[str, float | None]) -> tuple[str, float]:
    """Which reactant runs out first, and how much of it there is.

    `weighed` maps CAS → grams actually weighed. Each reactant's moles are
    divided by its coefficient; the smallest ratio is the one that runs out.
    """
    ratios: list[tuple[float, str, float]] = []
    for cas, coefficient in reaction.reactants:
        grams = weighed.get(cas)
        if grams is None:
            raise FormulaError(f"{cas!r} is a reactant but was not weighed")
        if coefficient <= 0:
            raise FormulaError(f"coefficient for {cas!r} must be positive")
        ratios.append((_moles_of(cas, grams, weights) / coefficient, cas, grams))
    if not ratios:
        raise FormulaError("a reaction needs at least one reactant")
    ratio, cas, _grams = min(ratios, key=lambda item: item[0])
    return cas, _moles_of(cas, weighed[cas], weights)


def equivalents(reaction: Reaction, basis_cas: str, weighed: dict[str, float],
                weights: dict[str, float | None]) -> dict[str, float]:
    """Each weighed reactant's equivalents against `basis_cas` (the 1.00 one).

    The same word the notebook's Formulation uses, so a student reads one
    number either way: 1.00 is the basis, 0.50 is half of it.
    """
    basis_moles = _moles_of(basis_cas, weighed[basis_cas], weights)
    basis_coefficient = dict(reaction.reactants).get(basis_cas)
    if not basis_coefficient:
        raise FormulaError(f"{basis_cas!r} is not a reactant")
    out: dict[str, float] = {}
    for cas, grams in weighed.items():
        coefficient = dict(reaction.reactants).get(cas)
        if not coefficient:
            continue
        out[cas] = _moles_of(cas, grams, weights) / coefficient / (basis_moles / basis_coefficient)
    return out


def theoretical_yield(reaction: Reaction, product_cas: str, weighed: dict[str, float],
                      weights: dict[str, float | None]) -> dict:
    """What the weighed reactants can make of `product_cas`, in grams.

    Returns the limiting reagent, its moles, the grams of product those
    moles allow by the coefficients, and what each reactant was worth.
    """
    limiting, moles = limiting_reagent(reaction, weighed, weights)
    coefficients = dict(reaction.reactants)
    product_coefficient = dict(reaction.products).get(product_cas)
    if not product_coefficient:
        raise FormulaError(f"{product_cas!r} is not a product of this reaction")
    scale = moles / coefficients[limiting]
    product_mw = weights.get(product_cas)
    if not product_mw:
        raise FormulaError(f"no molecular weight known for {product_cas!r}")
    return {
        "limiting": limiting,
        "limiting_moles": moles,
        "product_moles": scale * product_coefficient,
        "product_grams": round(scale * product_coefficient * product_mw, 4),
        "reactants": {cas: round(_moles_of(cas, grams, weights), 6) for cas, grams in weighed.items()},
    }


def percent_yield(actual_grams: float, theoretical_grams: float) -> dict:
    """The yield as a percent, with a warning when it cannot be true.

    Over 100% means something else is in the flask: an un-dried product,
    a side product, a weighing mistake. The caller shows the warning; the
    number is still returned so the record can keep it.
    """
    if theoretical_grams <= 0:
        raise FormulaError("theoretical yield must be positive")
    percent = round(actual_grams / theoretical_grams * 100, 1)
    warning = ""
    if percent > 100:
        warning = "over the theoretical value — check the product is dry, side products, and the weighing"
    elif percent < 5:
        warning = "very low — check the limiting reagent was really the one weighed, and losses in workup"
    return {"percent": percent, "warning": warning}


# ---------------------------------------------------------------- CAS numbers

# A CAS Registry Number is two to seven digits, two digits, one digit
# (7732-18-5, water). The last digit is a check digit: the digits before
# it, read right to left, each times its position, summed, mod 10.
_CAS = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")


def cas_is_valid(cas: str) -> bool:
    """True when a CAS number is well-formed and its check digit agrees.

    A typo in a CAS number finds the wrong substance or none at all — a
    controlled-substance check that misses is worse than one that never
    ran — so anything typed in for a CAS is checked before it is kept.
    An empty string is not valid: callers treat "" as "not filled in".
    """
    match = _CAS.match((cas or "").strip())
    if not match:
        return False
    digits = match.group(1) + match.group(2)
    total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digits)))
    return total % 10 == int(match.group(3))
