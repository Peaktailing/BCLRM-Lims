"""Routes for chemical experiments: the plan, the bench arithmetic, the
chain off the CAS numbers.

A plan is typed as lines, the way a bench sheet is written:

    67-64-1 1            ← a reactant: CAS number, coefficient
    78-93-3 1.2
    --                   ← the arrow
    50-78-6 1            ← the product

The reagents list says what each substance is for (reactant, catalyst,
solvent, workup) and what the lab calls it; the weighed list is what the
balance actually read. Everything else — stock, demands, equivalents,
yield — comes from app/chemical_experiments.py.

Who may do what follows the lab's usual rule (app/access.py): anyone
signed in may read a plan and work their own copy; the plan itself is
edited by whoever made it or an admin.
"""
from __future__ import annotations

import json

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from . import audit
from . import chemical_experiments as plans
from .db import SessionLocal
from .models import CHEMICAL_EXPERIMENT_KINDS, ChemicalExperiment, ExperimentCourse
from .chemlib import Reaction

bp = Blueprint("chem", __name__, url_prefix="/chem-experiments")


@bp.before_request
def require_login():
    if g.get("user") is None:
        return redirect(url_for("login", next=request.path))


# ---------------------------------------------------------------- the typed plan

def _parse_sides(text: str) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Lines of "CAS coefficient" with a "--" line for the arrow. A line
    with no coefficient means 1. Anything else is a flash and a None."""
    reactants: list[tuple[str, float]] = []
    products: list[tuple[str, float]] = []
    target = reactants
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("--", "→", "->", "=>"):
            target = products
            continue
        parts = line.split()
        cas = parts[0]
        coefficient = 1.0
        if len(parts) > 1:
            try:
                coefficient = float(parts[1].replace(",", "."))
            except ValueError:
                return [], []
        target.append((cas, coefficient))
    return reactants, products


def _parse_reagents(text: str) -> list[dict]:
    """Lines of "CAS name [role]"; the role defaults to reactant."""
    rows = []
    for raw in (text or "").splitlines():
        parts = raw.strip().split(None, 2)
        if not parts or parts[0].startswith("#"):
            continue
        cas = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        role = (parts[2].strip() if len(parts) > 2 else "reactant") or "reactant"
        rows.append({"cas": cas, "name": name, "role": role})
    return rows


def _parse_weighed(text: str) -> dict[str, float]:
    """Lines of "CAS grams"."""
    out: dict[str, float] = {}
    for raw in (text or "").splitlines():
        parts = raw.strip().split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        try:
            out[parts[0]] = float(parts[1].replace(",", "."))
        except ValueError:
            continue
    return out


def _reaction_text(experiment: ChemicalExperiment) -> str:
    reaction = plans.reaction_of(experiment)
    lines = [f"{cas} {coef:g}" for cas, coef in reaction.reactants]
    lines.append("--")
    lines += [f"{cas} {coef:g}" for cas, coef in reaction.products]
    return "\n".join(lines)


def _reagents_text(experiment: ChemicalExperiment) -> str:
    return "\n".join(f"{r['cas']} {r.get('name') or ''} {r.get('role') or 'reactant'}".rstrip()
                     for r in plans.reagents_of(experiment))


def _weighed_text(experiment: ChemicalExperiment) -> str:
    return "\n".join(f"{cas} {grams:g}" for cas, grams in plans.weighed_of(experiment).items())


def _may_edit(experiment: ChemicalExperiment) -> bool:
    user = g.get("user")
    return bool(user and (user.role == "admin" or user.username == experiment.created_by))


# ---------------------------------------------------------------- pages

@bp.get("")
def index():
    """Every plan the signed-in person may see: templates, working
    copies and finished records, newest first."""
    with SessionLocal() as s:
        courses = list(s.scalars(select(ExperimentCourse).order_by(ExperimentCourse.name)))
        experiments = list(s.scalars(select(ChemicalExperiment).order_by(
            ChemicalExperiment.created_at.desc(), ChemicalExperiment.id.desc()).limit(200)))
        rows = []
        for e in experiments:
            rows.append({"experiment": e, "course": s.get(ExperimentCourse, e.course_id) if e.course_id else None,
                         "reagents": len(plans.reagents_of(e)),
                         "mine": e.created_by == g.user.username or g.user.role == "admin"})
    return render_template("chem_experiments.html", rows=rows, courses=courses,
                           kinds=CHEMICAL_EXPERIMENT_KINDS)


@bp.get("/new")
def new():
    with SessionLocal() as s:
        courses = list(s.scalars(select(ExperimentCourse).order_by(ExperimentCourse.name)))
    return render_template("chem_experiment.html", experiment=None, courses=courses,
                           kinds=CHEMICAL_EXPERIMENT_KINDS, roles=plans.REAGENT_ROLES,
                           reaction_text="--", reagents_text="", weighed_text="",
                           stock=[], quantities=None, stock_error="", may_edit=True)


@bp.post("")
def create():
    form = request.form
    reactants, products = _parse_sides(form.get("reaction", ""))
    if not reactants or not products:
        flash("方案至少需要一行反应物、一行 -- 和一行产物", "error")
        return redirect(url_for("chem.new"))
    kind = form.get("kind") or "synthesis"
    if kind not in CHEMICAL_EXPERIMENT_KINDS:
        kind = "synthesis"
    course_id = form.get("course_id") or None
    with SessionLocal() as s:
        experiment = ChemicalExperiment(
            title=(form.get("title") or "").strip()[:200] or "未命名实验",
            kind=kind, course_id=int(course_id) if course_id else None,
            reaction_json=plans.reaction_to_json(Reaction(reactants=reactants, products=products)),
            reagents_json=json.dumps(_parse_reagents(form.get("reagents", ""))),
            weighed_json=json.dumps(_parse_weighed(form.get("weighed", ""))),
            procedure=form.get("procedure") or "",
            product_cas=(form.get("product_cas") or "").strip()[:20],
            status=(form.get("status") or "template") if (form.get("status") or "template")
            in ("template", "active") else "template",
            created_by=g.user.username)
        s.add(experiment)
        s.flush()
        with audit.batch(s, "create", f"chemical experiment {experiment.title}"[:200],
                         "chemical_experiments"):
            pass
        s.commit()
        return redirect(url_for("chem.detail", experiment_id=experiment.id))


@bp.get("/<int:experiment_id>")
def detail(experiment_id: int):
    with SessionLocal() as s:
        experiment = s.get(ChemicalExperiment, experiment_id)
        if experiment is None:
            abort(404)
        courses = list(s.scalars(select(ExperimentCourse).order_by(ExperimentCourse.name)))
        stock = plans.stock_check(s, experiment)
        quantities = plans.quantities(s, experiment)
        from app.models import CHEMICAL_EXPERIMENT_KINDS
        return render_template("chem_experiment.html", experiment=experiment, courses=courses,
                               kinds=CHEMICAL_EXPERIMENT_KINDS, roles=plans.REAGENT_ROLES,
                               reaction_text=_reaction_text(experiment),
                               reagents_text=_reagents_text(experiment),
                               weighed_text=_weighed_text(experiment),
                               stock=stock, quantities=quantities, stock_error="",
                               may_edit=_may_edit(experiment))


@bp.post("/<int:experiment_id>/update")
def update(experiment_id: int):
    with SessionLocal() as s:
        experiment = s.get(ChemicalExperiment, experiment_id)
        if experiment is None:
            abort(404)
        if not _may_edit(experiment):
            abort(403)
        form = request.form
        reactants, products = _parse_sides(form.get("reaction", ""))
        experiment.title = (form.get("title") or "").strip()[:200] or experiment.title
        experiment.procedure = form.get("procedure") or ""
        experiment.product_cas = (form.get("product_cas") or "").strip()[:20]
        course_id = form.get("course_id") or None
        experiment.course_id = int(course_id) if course_id else None
        if reactants and products:
            experiment.reaction_json = plans.reaction_to_json(
                plans.Reaction(reactants=reactants, products=products))
        experiment.reagents_json = json.dumps(_parse_reagents(form.get("reagents", "")))
        experiment.weighed_json = json.dumps(_parse_weighed(form.get("weighed", "")))
        with audit.batch(s, "update", f"chemical experiment {experiment.title}"[:200],
                         "chemical_experiments"):
            pass
        s.commit()
    return redirect(url_for("chem.detail", experiment_id=experiment_id))


@bp.post("/<int:experiment_id>/demands")
def demands(experiment_id: int):
    """Ask for what the lab has none of, so the purchase route starts
    from the bench rather than from memory."""
    with SessionLocal() as s:
        experiment = s.get(ChemicalExperiment, experiment_id)
        if experiment is None:
            abort(404)
        made = plans.missing_demands(s, experiment, requester=g.user.username)
        with audit.batch(s, "mixed", f"demands from chemical experiment {experiment.title}"[:200],
                         "chemical_experiments"):
            pass
        s.commit()
    flash(f"已生成 {len(made)} 条采购需求" if made else "所需试剂都有库存，无需生成需求", "info")
    return redirect(url_for("chem.detail", experiment_id=experiment_id))


@bp.post("/<int:experiment_id>/yield")
def record_yield(experiment_id: int):
    """The mass that came out, against what the equation says should
    have. The percent and chemlib's warning are written onto the record."""
    with SessionLocal() as s:
        experiment = s.get(ChemicalExperiment, experiment_id)
        if experiment is None:
            abort(404)
        raw = (request.form.get("actual_grams") or "").replace(",", ".").strip()
        try:
            actual = float(raw)
        except ValueError:
            flash("请填写实际产量（克）", "error")
            return redirect(url_for("chem.detail", experiment_id=experiment_id))
        try:
            result = plans.record_yield(s, experiment, actual)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("chem.detail", experiment_id=experiment_id))
        audit_msg = f"yield {result['percent']}% for chemical experiment {experiment.title}"[:200]
        with audit.batch(s, "update", audit_msg, "chemical_experiments"):
            pass
        s.commit()
    message = f"产率 {result['percent']}%（理论 {result['theoretical_grams']} g）"
    if result["warning"]:
        message += f"——{result['warning']}"
    flash(message, "info")
    return redirect(url_for("chem.detail", experiment_id=experiment_id))


@bp.post("/<int:experiment_id>/product")
def register_product(experiment_id: int):
    """A substance the lab made joins the references, so the next plan
    can use it by CAS number."""
    with SessionLocal() as s:
        experiment = s.get(ChemicalExperiment, experiment_id)
        if experiment is None:
            abort(404)
        cas = (request.form.get("cas") or "").strip() or experiment.product_cas
        formula = (request.form.get("formula") or "").strip()
        name = (request.form.get("name") or "").strip()
        if not cas:
            flash("请填写产物的 CAS 号", "error")
            return redirect(url_for("chem.detail", experiment_id=experiment_id))
        try:
            plans.register_product(s, cas, formula, name)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("chem.detail", experiment_id=experiment_id))
        with audit.batch(s, "update", f"product {name or cas} registered from an experiment"[:200],
                         "chemical_experiments"):
            pass
        s.commit()
    flash(f"{name or cas} 已登记为化学品档案", "info")
    return redirect(url_for("chem.detail", experiment_id=experiment_id))


@bp.post("/<int:experiment_id>/start")
def start(experiment_id: int):
    """A course's template becomes the signed-in person's working copy:
    same plan, own record, own bench notes."""
    with SessionLocal() as s:
        template = s.get(ChemicalExperiment, experiment_id)
        if template is None:
            abort(404)
        copy = plans.start_from_template(s, template, student=g.user.username)
        with audit.batch(s, "create", f"working copy of chemical experiment {template.title}"[:200],
                         "chemical_experiments"):
            pass
        s.commit()
        return redirect(url_for("chem.detail", experiment_id=copy.id))
