"""Derived readouts: the number an experiment follows, worked out by
BioManager from what a ruler or an instrument gives.

BioManager computes; the model talks. A caliper sheet gives a tumour's
length and width, a qPCR export the Ct of each gene, a plate reader each
well's OD; the readout is a formula over those. Each formula here is named,
says what it takes (its inputs, each with a unit), what it gives and how,
in a line a person can check, and refuses what it can't use (a value
missing, below zero, a Ct no run gives) in words. Nothing here touches the
database: app/experiments.py keeps the inputs with each reading, and the
`derive` tool (POST /api/v1/derive) shows the numbers before anything is
proposed.

    check("tumour_lw", {"length": "12.1", "width": 8})   → {"length": 12.1, "width": 8.0}
    compute("tumour_lw", {"length": 12.1, "width": 8})   → 387.2
    delta_delta_ct([{"group": "Vehicle", "ct_target": 25, "ct_reference": 18}, …], "Vehicle")
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .i18n import gettext, translate_value as tr

CT_MAX = 50.0           # no qPCR run goes past this many cycles
OD_MAX = 10.0           # nor a plate reader past this absorbance


class DerivedError(ValueError):
    """Inputs a formula can't take, in words for the person."""


@dataclass(frozen=True)
class Input:
    key: str
    label: str
    unit: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "unit": self.unit}


@dataclass(frozen=True)
class Formula:
    key: str
    label: str
    unit: str
    expression: str
    description: str
    inputs: tuple[Input, ...]
    per_group: bool = False          # against the control group's mean ΔCt on the same day
    can_be_negative: bool = False
    families: tuple[str, ...] = ()   # the animals it fits; empty: every kind
    verb: str = "Record"

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "unit": self.unit, "expression": self.expression,
                "description": self.description, "inputs": [i.as_dict() for i in self.inputs],
                "per_group": self.per_group, "can_be_negative": self.can_be_negative}


_LENGTH, _WIDTH, _HEIGHT = Input("length", "Length", "mm"), Input("width", "Width", "mm"), Input("height", "Height", "mm")
_CTS = (Input("ct_target", "Ct of the target gene"), Input("ct_reference", "Ct of the reference gene"))

FORMULAS: dict[str, Formula] = {f.key: f for f in (
    Formula("tumour_lw", "Tumour volume (L × W² / 2)", "mm³", "L × W² / 2",
            "A tumour's volume from calipers, as an ellipsoid: length × width² / 2, the length being the longer side.",
            (_LENGTH, _WIDTH), families=("mouse", "organism"), verb="Measure"),
    Formula("tumour_lwh", "Tumour volume (π/6 × L × W × H)", "mm³", "π/6 × L × W × H",
            "A tumour's volume as an ellipsoid from its three diameters: π/6 × length × width × height.",
            (_LENGTH, _WIDTH, _HEIGHT), families=("mouse", "organism"), verb="Measure"),
    Formula("delta_ct", "ΔCt", "", "Ct target − Ct reference",
            "How many cycles later the target gene comes up than the reference gene: Ct of the target − Ct of the reference.",
            _CTS, can_be_negative=True),
    Formula("delta_delta_ct", "ΔΔCt", "", "ΔCt − mean ΔCt of the control group",
            "Each animal's ΔCt less the control group's mean ΔCt on the same day.",
            _CTS, per_group=True, can_be_negative=True),
    Formula("fold_change", "Fold change (2^−ΔΔCt)", "", "2^−ΔΔCt",
            "Expression against the control group: 2^−ΔΔCt, where ΔΔCt is the animal's ΔCt less the control group's mean ΔCt on the same day.",  # noqa: E501
            _CTS, per_group=True),
    Formula("percent_of_baseline", "% of baseline", "%", "value / baseline × 100",
            "A value as a percentage of a baseline, such as body weight as % of day 1: value / baseline × 100.",
            (Input("value", "Value"), Input("baseline", "Baseline"))),
    Formula("blank_subtracted", "Absorbance, blank subtracted", "OD", "OD − blank",
            "A well's absorbance less the blank's: OD − blank OD.",
            (Input("od", "OD"), Input("blank", "Blank OD")), can_be_negative=True),
)}


def formula(key: str) -> Formula:
    f = FORMULAS.get(str(key or "").strip())
    if f is None:
        raise DerivedError(gettext("“%(formula)s” is not a formula BioManager works out; it has %(known)s.",
                                   formula=key, known=", ".join(FORMULAS)))
    return f


def catalogue() -> list[dict]:
    """Every formula, for the `derive` tool and GET /api/v1/derive."""
    return [f.as_dict() for f in FORMULAS.values()]


def tidy(x: float) -> float:
    """Six significant figures: what a measurement carries, without float noise."""
    return float(f"{x:.6g}")


# ---------------------------------------------------------------- the formulas themselves

def tumour_volume_ellipsoid(length: float, width: float) -> float:
    """L × W² / 2, in mm³ from mm."""
    return tidy(length * width * width / 2)


def tumour_volume_three_axes(length: float, width: float, height: float) -> float:
    """π/6 × L × W × H, in mm³ from mm."""
    return tidy(math.pi / 6 * length * width * height)


def delta_ct(ct_target: float, ct_reference: float) -> float:
    return tidy(ct_target - ct_reference)


def percent_of_baseline(value: float, baseline: float) -> float:
    if baseline <= 0:
        raise DerivedError(gettext("The baseline is %(value)s: a percentage of it needs a baseline above zero.",
                                   value=f"{baseline:g}"))
    return tidy(value / baseline * 100)


def blank_subtracted(od: float, blank: float) -> float:
    return tidy(od - blank)


def delta_delta_ct(rows: list[dict], control: str) -> list[dict]:
    """Each row's ΔCt, ΔΔCt against the mean ΔCt of the control group's
    rows on the same day (a row's `day`, if it has one), and fold change
    2^−ΔΔCt. Rows are {"group", "ct_target", "ct_reference"[, "day"]},
    already checked; the result keeps each row's own keys."""
    wanted = str(control or "").strip().lower()
    if not wanted:
        raise DerivedError(gettext("Say which group is the control: ΔΔCt is worked out against its mean ΔCt."))
    by_day: dict[str, list[float]] = {}
    for r in rows:
        if str(r.get("group") or "").strip().lower() == wanted:
            by_day.setdefault(str(r.get("day") or ""), []).append(r["ct_target"] - r["ct_reference"])
    out = []
    for r in rows:
        day = str(r.get("day") or "")
        if day not in by_day:
            if day:
                raise DerivedError(gettext("No animal of the control group “%(group)s” has its Ct values on %(day)s: ΔΔCt is worked out against them.",  # noqa: E501
                                           group=control, day=day))
            raise DerivedError(gettext("No animal of the control group “%(group)s” has its Ct values: ΔΔCt is worked out against them.",  # noqa: E501
                                       group=control))
        mean = sum(by_day[day]) / len(by_day[day])
        dct = r["ct_target"] - r["ct_reference"]
        ddct = dct - mean
        out.append({**r, "delta_ct": tidy(dct), "control_mean_delta_ct": tidy(mean), "delta_delta_ct": tidy(ddct),
                    "fold_change": tidy(2 ** -ddct)})
    return out


# ---------------------------------------------------------------- checking what was given

def _number(f: Formula, inp: Input, raw) -> float:
    label = tr(inp.label)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise DerivedError(gettext("%(input)s is missing: %(formula)s needs it.", input=label, formula=tr(f.label)))
    if isinstance(raw, bool):
        raise DerivedError(gettext("%(input)s “%(value)s” isn't a number.", input=label, value=raw))
    text = str(raw).strip().replace(",", ".")
    if text.lower() in ("undetermined", "undet", "n/a", "na", "nan", "no ct", "-"):
        raise DerivedError(gettext("%(input)s is “%(value)s”: it never came up, so there is nothing to work out.",
                                   input=label, value=str(raw).strip()))
    try:
        value = float(text)
    except ValueError:
        raise DerivedError(gettext("%(input)s “%(value)s” isn't a number.", input=label, value=str(raw).strip())) from None
    if not math.isfinite(value):
        raise DerivedError(gettext("%(input)s “%(value)s” isn't a number.", input=label, value=str(raw).strip()))
    if value < 0:
        raise DerivedError(gettext("%(input)s can't be below zero (%(value)s).", input=label, value=f"{value:g}"))
    return value


def check(key: str, raw) -> dict[str, float]:
    """The formula's inputs from what was given ({input key: number or
    text}), as numbers; a DerivedError, in words, for anything it can't use."""
    f = formula(key)
    names = ", ".join(tr(i.label) for i in f.inputs)
    if not isinstance(raw, dict):
        raise DerivedError(gettext("%(formula)s is worked out from %(inputs)s: give those, not the result.",
                                   formula=tr(f.label), inputs=names))
    known = {i.key for i in f.inputs}
    extra = sorted(str(k) for k in raw if k not in known)
    if extra:
        raise DerivedError(gettext("%(formula)s takes %(inputs)s, not %(extra)s.", formula=tr(f.label),
                                   inputs=", ".join(i.key for i in f.inputs), extra=", ".join(extra)))
    values = {i.key: _number(f, i, raw.get(i.key)) for i in f.inputs}
    if f.key == "tumour_lw" and values["width"] > values["length"]:
        raise DerivedError(gettext("The width (%(width)s mm) is more than the length (%(length)s mm): the length is the longer side.",  # noqa: E501
                                   width=f"{values['width']:g}", length=f"{values['length']:g}"))
    if f.key in ("delta_ct", "delta_delta_ct", "fold_change"):
        for i in f.inputs:
            if not 0 < values[i.key] <= CT_MAX:
                raise DerivedError(gettext("A Ct of %(value)s isn't one a run gives (above 0, at most %(max)s).",
                                           value=f"{values[i.key]:g}", max=f"{CT_MAX:g}"))
    if f.key == "blank_subtracted":
        for i in f.inputs:
            if values[i.key] > OD_MAX:
                raise DerivedError(gettext("An OD of %(value)s is more than a plate reader reads (at most %(max)s).",
                                           value=f"{values[i.key]:g}", max=f"{OD_MAX:g}"))
    if f.key == "percent_of_baseline" and values["baseline"] == 0:
        raise DerivedError(gettext("The baseline is %(value)s: a percentage of it needs a baseline above zero.",
                                   value="0"))
    return values


def compute(key: str, raw) -> float:
    """One animal's value from its inputs (checked here). A formula against
    a control group needs the others: see delta_delta_ct and derive()."""
    f = formula(key)
    v = check(key, raw)
    if f.key == "tumour_lw":
        return tumour_volume_ellipsoid(v["length"], v["width"])
    if f.key == "tumour_lwh":
        return tumour_volume_three_axes(v["length"], v["width"], v["height"])
    if f.key == "delta_ct":
        return delta_ct(v["ct_target"], v["ct_reference"])
    if f.key == "percent_of_baseline":
        return percent_of_baseline(v["value"], v["baseline"])
    if f.key == "blank_subtracted":
        return blank_subtracted(v["od"], v["blank"])
    raise DerivedError(gettext("%(formula)s is worked out against a control group: give the whole day's animals and which group is the control.",  # noqa: E501
                               formula=tr(f.label)))


def group_values(key: str, rows: list[dict], control: str) -> list[float]:
    """ΔΔCt or fold change for each row ({"group", "day", inputs…}, checked)."""
    field = "delta_delta_ct" if key == "delta_delta_ct" else "fold_change"
    return [r[field] for r in delta_delta_ct(rows, control)]


# ---------------------------------------------------------------- the inputs kept with a reading

def note(inputs: dict[str, float]) -> str:
    """The inputs as kept in a reading's note: JSON, and readable as it is."""
    return json.dumps({k: (int(v) if float(v).is_integer() else v) for k, v in inputs.items()}, ensure_ascii=False)


def read_note(text: str | None) -> dict[str, float] | None:
    try:
        data = json.loads(text or "")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return {str(k): float(v) for k, v in data.items()}
    except (TypeError, ValueError):
        return None


def inputs_text(key: str, inputs: dict[str, float]) -> str:
    """"Length 12 mm, Width 8 mm": the inputs in words, in the page's language."""
    f = formula(key)
    parts = []
    for i in f.inputs:
        if i.key in inputs:
            parts.append(f"{tr(i.label)} {inputs[i.key]:g}{f' {i.unit}' if i.unit else ''}")
    return ", ".join(parts)


# ---------------------------------------------------------------- many rows at once (the derive tool)

def derive(key: str, rows, control: str | None = None) -> dict:
    """A formula over rows, changing nothing: each row as given, with its
    inputs as numbers and its value, or its error in words. A row is
    {inputs…} or {"inputs": {…}}, and may carry "animal", "group" and "day"
    (a formula against a control group takes the control's mean ΔCt for the
    same day)."""
    f = formula(key)
    if not isinstance(rows, list) or not rows:
        raise DerivedError(gettext("rows is a list of the measurements, one row each."))
    if len(rows) > 2000:
        raise DerivedError(gettext("At most %(max)s rows at once.", max=2000))
    out, good = [], []
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            out.append({"row": n, "error": gettext("Each row is an object.")})
            continue
        given = row.get("inputs") if isinstance(row.get("inputs"), dict) else {
            k: v for k, v in row.items() if k not in ("animal", "label", "group", "day", "date")}
        entry = {"row": n, **{k: row[k] for k in ("animal", "label", "group", "day", "date") if k in row}}
        try:
            entry["inputs"] = check(f.key, given)
            if not f.per_group:
                entry["value"] = compute(f.key, entry["inputs"])
            else:
                good.append(entry)
        except DerivedError as e:
            entry["error"] = str(e)
        out.append(entry)
    answer = {"formula": f.as_dict(), "rows": out}
    if f.per_group:
        flat = [{"group": e.get("group", ""), "day": str(e.get("day") or e.get("date") or ""), **e["inputs"]}
                for e in good]
        worked = delta_delta_ct(flat, control or "")
        means = {}
        for e, w in zip(good, worked):
            e.update(delta_ct=w["delta_ct"], delta_delta_ct=w["delta_delta_ct"], fold_change=w["fold_change"],
                     value=w["delta_delta_ct"] if f.key == "delta_delta_ct" else w["fold_change"])
            means[w["day"] or "all"] = w["control_mean_delta_ct"]
        answer.update(control=control, control_mean_delta_ct=means)
    answer["computed"] = sum(1 for e in out if "value" in e)
    answer["refused"] = sum(1 for e in out if "error" in e)
    answer["changes_nothing"] = True
    return answer
