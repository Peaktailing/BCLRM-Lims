"""A chemical experiment's plan, and the chain it hangs off.

The plan is an equation (chemlib.Reaction: CAS numbers and coefficients)
plus the role each substance plays — reactant, catalyst, solvent, workup.
Everything else follows from the CAS numbers, which is the point: the
same number that identifies a substance on a bottle identifies it in a
catalogue, in a controlled list and in a reaction.

    bottles_for(cas)        what the lab has of it, and whether it may go
    missing_for(plan)       what it has none of — asked for on a demand
    quantities(weighed)     equivalents, the limiting reagent, what a
                            product comes to (chemlib)
    record_yield(grams)     the percent yield, with its warning
    register_product(…)     a new substance joins the references
    start_from_template(…)  a course's students each get their own copy

No HTTP here: the routes (app/chemical_experiments_routes.py) parse and
render, this decides and computes.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from . import controlled
from .chemlib import Reaction, equivalents, limiting_reagent, percent_yield, theoretical_yield
from .models import (ChemicalExperiment, ChemicalReference, ExperimentCourse,
                     InventoryItem, ReagentDemand)

# The roles a substance plays in a plan. The first three go into the
# yield arithmetic; a solvent and a workup reagent are there in bulk and
# are not counted as limiting.
REAGENT_ROLES = ["reactant", "catalyst", "solvent", "workup"]


# ---------------------------------------------------------------- the equation

def reaction_of(experiment: ChemicalExperiment) -> Reaction:
    """The plan's equation, as chemlib wants it."""
    try:
        data = json.loads(experiment.reaction_json or "{}")
        return Reaction(reactants=[(str(c), float(n)) for c, n in data.get("reactants", [])],
                        products=[(str(c), float(n)) for c, n in data.get("products", [])])
    except (ValueError, TypeError):
        return Reaction()


def reaction_to_json(reaction: Reaction) -> str:
    return json.dumps({"reactants": [[cas, coef] for cas, coef in reaction.reactants],
                       "products": [[cas, coef] for cas, coef in reaction.products]})


def reagents_of(experiment: ChemicalExperiment) -> list[dict]:
    """[{cas, name, role}] — what the plan says goes into the flask."""
    try:
        rows = json.loads(experiment.reagents_json or "[]")
    except ValueError:
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("cas")]


def weighed_of(experiment: ChemicalExperiment) -> dict[str, float]:
    """{cas: grams} — what was actually weighed at the bench."""
    try:
        rows = json.loads(experiment.weighed_json or "{}")
    except ValueError:
        return {}
    out = {}
    for cas, grams in rows.items():
        try:
            out[str(cas)] = float(grams)
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------- what the lab has

def chemical_modules(session) -> list:
    """The databases a chemical plan looks in for bottles: the Chemicals
    and chemical_reagents presets (a Formulation picks from the same)."""
    from . import inventory_service as inventories
    return [m for m in inventories.list_modules(session, everyone=True)
            if m.kind in ("chemicals", "chemical_reagents")
            or any(f["key"] == "mw" for f in inventories.view(m).fields)]


def bottles_for(session, cas: str) -> list[dict]:
    """The lab's bottles of one substance, by CAS number: what is in
    stock and may be signed out, what is used up, and where it sits. A
    bottle carries the CAS in its attrs, the way the presets write it."""
    cas = (cas or "").strip()
    if not cas:
        return []
    from . import inventory_service as inventories
    modules = {m.id: m for m in chemical_modules(session)}
    if not modules:
        return []
    out = []
    for item in session.scalars(select(InventoryItem).where(
            InventoryItem.module_id_fk.in_(list(modules))).order_by(InventoryItem.name)):
        attrs = item.attrs_dict
        if (str(attrs.get("cas") or "").strip() != cas):
            continue
        module = modules[item.module_id_fk]
        mv = inventories.view(module)
        available = inventories.is_available(mv, item.status) is not False
        out.append({"item_id": item.id, "ref": f"@{module.key} {item.number}",
                    "database": module.label, "name": item.name or "",
                    "grade": str(attrs.get("grade") or ""), "lot": item.lot or "",
                    "quantity": item.quantity or str(attrs.get("quantity") or ""),
                    "unit": item.unit or str(attrs.get("unit") or ""),
                    "location": item.rack.name if item.rack is not None else "",
                    "status": item.status or "", "available": available})
    return out


def stock_check(session, experiment: ChemicalExperiment) -> list[dict]:
    """Every substance in the plan, with what the lab has of it.

    One row per reagent: its bottles when there are any, a flag when
    there are none, and whether signing one out would need an approver
    (app/controlled.py). This is the table the plan page shows before
    anyone weighs anything.
    """
    rows = []
    for reagent in reagents_of(experiment):
        cas = str(reagent.get("cas") or "")
        bottles = bottles_for(session, cas)
        state = controlled.borrow_order_state(session, cas=cas, name=str(reagent.get("name") or ""))
        rows.append({"cas": cas, "name": str(reagent.get("name") or ""),
                     "role": str(reagent.get("role") or "reactant"),
                     "bottles": bottles, "in_stock": bool(bottles),
                     "controlled": state["controlled"], "controlled_type": state["type"]})
    return rows


def missing_demands(session, experiment: ChemicalExperiment, requester: str = "") -> list[int]:
    """A demand for every substance the plan needs and the lab has none
    of, so the purchase route starts from the bench rather than from
    memory. Existing open demands for the same substance are left alone.

    Returns the ids of the demands created (the caller commits).
    """
    made = []
    for row in stock_check(session, experiment):
        if row["in_stock"] or not row["cas"]:
            continue
        already = session.scalar(select(ReagentDemand.id).where(
            ReagentDemand.cas == row["cas"], ReagentDemand.status.in_(("open", "planned"))).limit(1))
        if already:
            continue
        demand = ReagentDemand(chemical_name=row["name"] or row["cas"], cas=row["cas"],
                               quantity=0.0, unit="",
                               purpose=f"{experiment.title}（化学实验方案）",
                               course_id=experiment.course_id, requester=requester,
                               status="open", created_by=requester)
        session.add(demand)
        session.flush()
        made.append(demand.id)
    return made


# ---------------------------------------------------------------- the arithmetic

def weights_of(session, cas_list) -> dict[str, float | None]:
    """Molecular weights for a set of CAS numbers, from the references.
    A substance the lab has no reference for gets None — chemlib says so
    rather than guessing. A reference with a formula but no number yet
    (a product just registered) has its weight computed from the formula:
    the formula is the source of truth when nobody has weighed a value."""
    from .chemlib import FormulaError, molecular_weight
    wanted = {str(c).strip() for c in cas_list if str(c).strip()}
    out: dict[str, float | None] = {cas: None for cas in wanted}
    if not wanted:
        return out
    for ref in session.scalars(select(ChemicalReference).where(ChemicalReference.cas.in_(wanted))):
        mw = ref.molecular_weight
        if not mw and ref.formula:
            try:
                mw = round(molecular_weight(ref.formula), 2)
            except FormulaError:
                mw = None
        out[ref.cas] = mw
    return out


def quantities(session, experiment: ChemicalExperiment, weighed: dict[str, float] | None = None) -> dict:
    """The plan's arithmetic: equivalents against the first reactant, the
    limiting reagent, the theoretical yield of the product, and the mass
    of each reactant that amount needs. A missing molecular weight is a
    readable error, not a crash — the plan page shows what to fill in."""
    reaction = reaction_of(experiment)
    weighed = weighed if weighed is not None else weighed_of(experiment)
    cas_list = [cas for cas, _coef in reaction.reactants + reaction.products]
    weights = weights_of(session, cas_list)
    unknown = sorted(cas for cas, mw in weights.items() if not mw)
    if unknown:
        return {"ok": False, "unknown_cas": unknown, "message": "这些物质还没有分子量，请先在化学品档案中填写分子式或分子量"}
    try:
        eq = equivalents(reaction, reaction.reactants[0][0], weighed, weights) if reaction.reactants else {}
        limiting, moles = limiting_reagent(reaction, weighed, weights)
        theory = theoretical_yield(reaction, experiment.product_cas, weighed, weights) if experiment.product_cas else {}
        return {"ok": True, "equivalents": eq, "limiting": limiting, "limiting_moles": round(moles, 6),
                "theoretical": theory, "weights": weights}
    except Exception as exc:                       # a FormulaError from chemlib: "not weighed", "not a product"
        return {"ok": False, "message": str(exc)}


def record_yield(session, experiment: ChemicalExperiment, actual_grams: float) -> dict:
    """The mass that came out of the flask, against what the equation
    says should have: the percent yield, with chemlib's warning when the
    number cannot be true. Written back onto the record."""
    reaction = reaction_of(experiment)
    weighed = weighed_of(experiment)
    weights = weights_of(session, [cas for cas, _c in reaction.reactants + reaction.products])
    theory = theoretical_yield(reaction, experiment.product_cas, weighed, weights)
    result = percent_yield(actual_grams, theory["product_grams"])
    experiment.actual_yield_grams = actual_grams
    experiment.yield_percent = result["percent"]
    experiment.yield_warning = result["warning"]
    experiment.status = "done"
    experiment.done_at = datetime.utcnow()
    return {"ok": True, "percent": result["percent"], "warning": result["warning"],
            "theoretical_grams": theory["product_grams"], "limiting": theory["limiting"]}


# ---------------------------------------------------------------- the product, and copies

def register_product(session, cas: str, formula: str, name: str = "") -> ChemicalReference:
    """A substance the lab made joins the references, so the next plan
    can use it: the CAS number is the identity, the formula gives the
    molecular weight (chemlib), and a row that already claims the CAS
    number is topped up rather than duplicated."""
    from .chemlib import molecular_weight
    cas = (cas or "").strip()
    existing = session.scalar(select(ChemicalReference).where(ChemicalReference.cas == cas))
    if existing is not None:
        if formula and formula != existing.formula:
            existing.formula = formula
            if existing.mw_source != "manual":
                existing.molecular_weight = round(molecular_weight(formula), 2)
        # A row whose name is still just its CAS number carries no name at
        # all: now that the bench has one, it may have it.
        if name and (not existing.name or existing.name == existing.cas):
            existing.name = name
        elif name and not existing.notes:
            existing.notes = name
        return existing
    ref = ChemicalReference(name=name or cas, cas=cas, formula=formula,
                            molecular_weight=round(molecular_weight(formula), 2) if formula else 0.0,
                            mw_source="formula" if formula else "manual")
    session.add(ref)
    session.flush()
    return ref


def start_from_template(session, template: ChemicalExperiment, course_id: int | None = None,
                        student: str = "") -> ChemicalExperiment:
    """A course's template becomes one student's working copy: same plan,
    own record, own bench notes. The template stays a template, and the
    copy remembers which one it came from."""
    copy = ChemicalExperiment(
        title=template.title, kind=template.kind, course_id=course_id or template.course_id,
        template_id=template.id,
        reaction_json=template.reaction_json, reagents_json=template.reagents_json,
        procedure=template.procedure, product_cas=template.product_cas,
        status="active", created_by=student)
    session.add(copy)
    session.flush()
    return copy
