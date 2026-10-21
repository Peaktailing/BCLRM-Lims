"""A course's experiments: who started what, and what it used.

A course is the teaching loop around the plans: the templates belong to
it, each student starts their own copy (app/chemical_experiments.py),
and what they weigh at the bench is the term's consumption. This module
reads that back:

    courses(session)     every course with its counts
    usage(session, …)    per substance: weighed in total, per student,
                         against what the lab has
    copies(session, …)   the students' working copies of one template

No HTTP here: the routes parse and render, this decides and counts.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from . import chemical_experiments as plans
from .models import ChemicalExperiment, ExperimentCourse


def courses(session) -> list[dict]:
    """Every course, newest first, with the counts its list page shows:
    templates, working copies started, copies finished."""
    out = []
    for course in session.scalars(select(ExperimentCourse).order_by(
            ExperimentCourse.created_at.desc(), ExperimentCourse.id.desc())):
        experiments = list(session.scalars(select(ChemicalExperiment).where(
            ChemicalExperiment.course_id == course.id)))
        templates = [e for e in experiments if e.status == "template"]
        copies = [e for e in experiments if e.status != "template"]
        out.append({"course": course, "templates": len(templates),
                    "copies": len(copies), "done": sum(1 for e in copies if e.status == "done"),
                    "students": len({e.created_by for e in copies})})
    return out


def copies_of(session, course_id: int | None = None,
              template_id: int | None = None) -> list[ChemicalExperiment]:
    """The working copies: not templates, of a course or of one template
    (by the link the copy was started with)."""
    stmt = select(ChemicalExperiment).where(ChemicalExperiment.status != "template")
    if course_id is not None:
        stmt = stmt.where(ChemicalExperiment.course_id == course_id)
    if template_id is not None:
        stmt = stmt.where(ChemicalExperiment.template_id == template_id)
    return list(session.scalars(stmt.order_by(ChemicalExperiment.created_by,
                                              ChemicalExperiment.id)))


def usage(session, course_id: int | None = None) -> list[dict]:
    """What a course's students weighed, per substance.

    One row per CAS number that appears in any working copy's weighed
    list: the total across the course, how many students weighed it, the
    per-student figure, and what the lab has of it (the same bottles a
    plan page shows, plus the controlled-list flag). Sorted by total,
    heaviest first — the term's biggest consumers on top.
    """
    totals: dict[str, dict] = {}
    for copy in copies_of(session, course_id):
        student = copy.created_by or ""
        for cas, grams in plans.weighed_of(copy).items():
            row = totals.setdefault(cas, {"cas": cas, "name": "", "grams": 0.0, "students": set(),
                                          "per_student": {}})
            row["grams"] += grams
            row["students"].add(student)
            row["per_student"][student] = row["per_student"].get(student, 0.0) + grams
    if not totals:
        return []
    # Names: what the plans call the substance first (a person typed
    # "水杨酸"), the reference's own name when no plan says.
    for copy in copies_of(session, course_id):
        for reagent in plans.reagents_of(copy):
            row = totals.get(str(reagent.get("cas") or ""))
            if row is not None and reagent.get("name") and not row["name"]:
                row["name"] = str(reagent["name"])
    from .models import ChemicalReference
    for ref in session.scalars(select(ChemicalReference).where(
            ChemicalReference.cas.in_(list(totals)))):
        if ref.name and not totals[ref.cas]["name"]:
            totals[ref.cas]["name"] = ref.name
    out = []
    for row in totals.values():
        bottles = plans.bottles_for(session, row["cas"])
        from . import controlled
        state = controlled.borrow_order_state(session, cas=row["cas"], name=row["name"])
        out.append({"cas": row["cas"], "name": row["name"] or row["cas"],
                    "grams": round(row["grams"], 4), "students": len(row["students"]),
                    "per_student": round(row["grams"] / len(row["students"]), 4) if row["students"] else 0.0,
                    "in_stock": bool(bottles), "bottles": len(bottles),
                    "controlled": state["controlled"], "controlled_type": state["type"]})
    out.sort(key=lambda r: (-r["grams"], r["cas"]))
    return out


def student_rows(session, course_id: int | None = None) -> list[dict]:
    """One row per student who started anything in the course: how many
    copies, how many finished, and the yields they recorded."""
    out: dict[str, dict] = {}
    for copy in copies_of(session, course_id):
        student = copy.created_by or ""
        row = out.setdefault(student, {"student": student, "copies": 0, "done": 0,
                                       "yields": [], "last": None})
        row["copies"] += 1
        if copy.status == "done":
            row["done"] += 1
            if copy.yield_percent is not None:
                row["yields"].append(copy.yield_percent)
        stamp = copy.done_at or copy.created_at
        if stamp is not None and (row["last"] is None or stamp > row["last"]):
            row["last"] = stamp
    for row in out.values():
        row["yield_avg"] = round(sum(row["yields"]) / len(row["yields"]), 1) if row["yields"] else None
        row.pop("yields")
    return sorted(out.values(), key=lambda r: r["student"])


def report(session, course) -> dict:
    """The term's report for one course: what was planned, what the
    students weighed, and what that says about next term's shopping.

    The demand side is the arithmetic of the usage table against the
    roll: per-student weighing times the student count is what a full
    class would use, and the gap between that and what was actually
    weighed is what is still to come — shown so a teacher can see it
    before the bottles run out, not after.
    """
    experiments = list(session.scalars(select(ChemicalExperiment).where(
        ChemicalExperiment.course_id == course.id)))
    templates = [e for e in experiments if e.status == "template"]
    copies = [e for e in experiments if e.status != "template"]
    done = [e for e in copies if e.status == "done"]
    yields = [e.yield_percent for e in done if e.yield_percent is not None]
    usage_rows = usage(session, course_id=course.id)
    roll = course.student_count or 0
    for row in usage_rows:
        expected = row["per_student"] * roll if roll else 0.0
        row["expected"] = round(expected, 4)
        row["shortfall"] = round(max(0.0, expected - row["grams"]), 4)
    return {"course": course, "templates": len(templates), "copies": len(copies),
            "done": len(done), "students": len({e.created_by for e in copies}),
            "yield_avg": round(sum(yields) / len(yields), 1) if yields else None,
            "yields": len(yields), "usage": usage_rows,
            "controlled": [r for r in usage_rows if r["controlled"]],
            "students_rows": student_rows(session, course_id=course.id),
            "roll": roll}
