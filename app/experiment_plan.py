"""An experiment's design, fixed at Start, and the changes from it.

An experiment can be designed before it starts: status "planned" (an
assistant proposes one so, `actions.experiment_new`). Nothing of a planned
experiment is due: its days are not on Home, the calendar or in
notifications, and its page shows each day as planned. **Start**, a
person's button, sets day 1 (today, unless a start date is set), makes it
active and keeps a copy of the design in `experiments.plan_json`
(`snapshot`): the treatment groups and their animals, the main readout and
its day, the regimen and the statistical test planned.

From then on four kinds of change are changes from the plan, and each asks
for a one-line reason (`note`), kept in `experiment_deviations`:

- `readout`, `readout_day`: the main measurement or its day;
- `groups`: an animal added or taken out, moved to another group, a group
  renamed or merged, a group's count at the start changed;
- `left_out`: an animal left out of the analysis, or put back;
- `test`: the statistical test.

Nothing is ever refused for good: the change waits for its reason. More
changes of the same kind by the same person within CONTINUE_WITHIN join
the last one (its `after` follows, `detail` grows) rather than asking
again; an animal left out always asks. Dates, notes, the regimen and other
readouts never ask. An experiment started before this has no copy and
never asks.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from flask import g, jsonify
from sqlalchemy import select

from . import i18n
from .i18n import gettext
from .models import Experiment, ExperimentDeviation

# The tests app/exp_stats.py runs, by key: (name as exp_stats says it, when it fits).
TESTS = {
    "welch": ("Welch's t-test", "two groups, a number each"),
    "anova": ("One-way ANOVA", "more than two groups, a number each"),
    "chi2": ("χ² test", "how many of those at the start: survival, a phenotype"),
}

WHAT = {
    "readout": "Main readout",
    "readout_day": "Day of the main readout",
    "groups": "Groups",
    "left_out": "Left out of the analysis",
    "test": "Statistical test",
}

IN_ANALYSIS = "In the analysis"
LEFT_OUT = "Left out"
CONTINUE_WITHIN = timedelta(minutes=10)
NONE = "—"


# ---------------------------------------------------------------- reading the plan

def plan_of(exp: Experiment) -> dict:
    """The copy kept at Start ({} when there is none)."""
    try:
        plan = json.loads(exp.plan_json or "{}")
    except ValueError:
        return {}
    return plan if isinstance(plan, dict) else {}


def fixed(exp: Experiment) -> bool:
    """Started with a plan: the four kinds of change now ask for a reason."""
    return bool(plan_of(exp)) and (exp.status or "") != "planned"


def test_name(key: str) -> str:
    return TESTS[key][0] if key in TESTS else ""


def tests() -> list[dict]:
    return [{"key": k, "label": i18n.translate_value(name), "hint": i18n.translate_value(hint)}
            for k, (name, hint) in TESTS.items()]


def readout_text(readout: dict) -> str:
    """The readout's name; one worked out against a control group names
    that group too, so changing it after Start is a change from the plan."""
    label = str((readout or {}).get("label") or "")
    control = str((readout or {}).get("control") or "")
    return f"{label} · {control}" if label and control else label


# ---------------------------------------------------------------- the animals and their groups

def members(session, exp: Experiment, place) -> dict[str, tuple[str, str, int | None]]:
    """{subject key: (label, group, at the start)}, to compare before and after a change."""
    from . import experiments as ex
    session.flush()
    session.expire(exp, ["memberships"])
    return {x.key: (x.label, x.group, x.start if x.kind != "mouse" else None) for x in ex.subjects(session, exp, place)}


def group_sizes(subs: dict) -> str:
    """"HDM: 5 · vehicle: 5" (a row of fish or a vial counts as the animals it started with)."""
    sizes: dict[str, int] = {}
    for _label, group, start in subs.values():
        sizes[group or NONE] = sizes.get(group or NONE, 0) + (start or 1)
    return " · ".join(f"{name}: {n}" for name, n in sorted(sizes.items(), key=lambda kv: kv[0].lower()))


def _diff(before: dict, after: dict) -> list[str]:
    lines = []
    for key, (label, group, _s) in after.items():
        if key not in before:
            lines.append(f"+ {label} ({group or NONE})")
    for key, (label, group, _s) in before.items():
        if key not in after:
            lines.append(f"− {label} ({group or NONE})")
    for key, (label, group, start) in after.items():
        if key not in before:
            continue
        _l, old_group, old_start = before[key]
        if (old_group or "").strip() != (group or "").strip():
            lines.append(f"{label}: {old_group or NONE} → {group or NONE}")
        if old_start is not None and old_start != start:
            lines.append(f"{label}: n {old_start} → {start if start is not None else NONE}")
    return lines


def groups_changed(session, exp: Experiment, place, before: dict, reason: str = "") -> str | None:
    """After a change to the animals (flushed, not committed): keep it as a
    change from the plan, or a sentence asking why."""
    if not fixed(exp):
        return None
    after = members(session, exp, place)
    lines = _diff(before, after)
    if not lines:
        return None
    return note(session, exp, "groups", group_sizes(before), group_sizes(after), reason, lines)


# ---------------------------------------------------------------- keeping a change

# What a change touches, in the sentence that asks why.
CHANGES = {
    "readout": "the main readout",
    "readout_day": "the day of the main readout",
    "groups": "the groups",
    "left_out": "which animals are in the analysis",
    "test": "the statistical test",
}


def asking(what: str) -> str:
    return gettext("This changes %(what)s, which the plan kept at Start fixed. Give a reason: it is kept under Changes from the plan.", what=i18n.translate_value(CHANGES[what]))  # noqa: E501


def note(session, exp: Experiment, what: str, before: str, after: str, reason: str = "",
         lines: list[str] | None = None) -> str | None:
    """Keep one change from the plan with its reason. None when kept (or
    when there is no plan to change); else the sentence that asks why."""
    if not fixed(exp) or before == after and not lines:
        return None
    reason = (reason or "").strip()[:500]
    who = g.user.username if g.get("user") is not None else ""
    now = datetime.utcnow()
    detail = "\n".join(lines or [])
    if not reason:
        last = session.scalar(select(ExperimentDeviation).where(
            ExperimentDeviation.experiment_id_fk == exp.id, ExperimentDeviation.what == what,
            ExperimentDeviation.username == who).order_by(ExperimentDeviation.id.desc()).limit(1))
        if what != "left_out" and last is not None and (last.updated_at or last.created_at) >= now - CONTINUE_WITHIN:
            last.after = after
            last.detail = "\n".join(filter(None, [last.detail, detail]))
            last.updated_at = now
            return None
        return asking(what)
    session.add(ExperimentDeviation(experiment_id_fk=exp.id, what=what, before=before, after=after,
                                    detail=detail, reason=reason, username=who, created_at=now, updated_at=now))
    return None


def ask_response(sentence: str):
    """The page's answer when a change waits for its reason: the page asks,
    and sends it again with `reason`."""
    return jsonify({"ok": False, "needs_reason": True, "error": sentence}), 409


# ---------------------------------------------------------------- Start

def snapshot(session, exp: Experiment, place) -> dict:
    from . import experiment_steps as xs
    from . import experiments as ex
    subs = ex.subjects(session, exp, place)
    groups: dict[str, list] = {}
    for x in subs:
        groups.setdefault(x.group, []).append(x)
    return {
        "started_on": (exp.start_date or date.today()).isoformat(),
        "started_by": g.user.username if g.get("user") is not None else "",
        "groups": [{"name": name, "n": sum((x.start or 1) if x.kind != "mouse" else 1 for x in xs_),
                    "animals": [{"key": x.key, "label": x.label, "start": x.start if x.kind != "mouse" else None,
                                 "left_out": _left_out(x)} for x in xs_]}
                   for name, xs_ in sorted(groups.items(), key=lambda kv: kv[0].lower())],
        "readout": ex.readout_of(exp, place),
        "readout_day": exp.readout_day,
        "test": exp.planned_test or "",
        "steps": [{"days": st.days, "kind": st.kind, "kind_label": ex.kind_info(place.family, st.kind)[0],
                   "agent": st.agent, "dose": st.dose, "route": st.route, "concentration": st.concentration,
                   **xs.stimulation(st),
                   "group": st.treatment_group, "day_count": len(xs.safe_days(st))} for st in exp.steps],
    }


def _left_out(subject) -> str:
    return (getattr(subject.row, "left_out", "") or "") if subject.row is not None else ""


# ---------------------------------------------------------------- what the page shows

def _shown(what: str, raw: str) -> str:
    if raw in ("", None):
        return NONE
    if what == "readout_day":
        return gettext("Day %(n)s", n=raw)
    return i18n.translate_value(raw)


def deviations(exp: Experiment) -> list[dict]:
    return [{"id": d.id, "what": d.what, "what_label": i18n.translate_value(WHAT.get(d.what, d.what)),
             "before": _shown(d.what, d.before), "after": _shown(d.what, d.after),
             "detail": [line for line in (d.detail or "").split("\n") if line],
             "reason": d.reason, "who": d.username,
             "when": (d.updated_at or d.created_at).isoformat(timespec="minutes") if (d.updated_at or d.created_at) else "",
             "raw": {"before": d.before, "after": d.after}}
            for d in exp.deviations]


def _regimen(steps: list[dict]) -> str:
    days = sum(int(s.get("day_count") or 0) for s in steps)
    if not steps:
        return NONE
    return gettext("%(lines)s lines, %(days)s days", lines=len(steps), days=days)


def _step_sig(st: dict) -> tuple:
    return tuple(str(st.get(k) or "") for k in ("days", "kind", "agent", "dose", "route", "concentration",
                                                "frequency", "intensity", "pulse_width", "duration", "group"))


def comparison(session, exp: Experiment, place, subs, table: dict) -> list[dict]:
    """Planned → done: each part of the plan as kept at Start, and as it is."""
    from . import experiment_steps as xs
    from . import experiments as ex
    plan = plan_of(exp)
    if not plan:
        return []
    rows = []
    now_members = {x.key: (x.label, x.group, x.start if x.kind != "mouse" else None) for x in subs}
    planned_members = {a["key"]: (a["label"], grp["name"], a.get("start")) for grp in plan.get("groups", [])
                       for a in grp.get("animals", [])}
    rows.append({"what": i18n.translate_value(WHAT["groups"]), "planned": group_sizes(planned_members) or NONE,
                 "done": group_sizes(now_members) or NONE, "changed": bool(_diff(planned_members, now_members))})
    left_now = [x.label for x in subs if _left_out(x)]
    left_planned = [a["label"] for grp in plan.get("groups", []) for a in grp.get("animals", []) if a.get("left_out")]
    rows.append({"what": i18n.translate_value(WHAT["left_out"]),
                 "planned": ", ".join(left_planned) or NONE, "done": ", ".join(left_now) or NONE,
                 "changed": sorted(left_planned) != sorted(left_now)})
    readout = ex.readout_of(exp, place)
    rows.append({"what": i18n.translate_value(WHAT["readout"]),
                 "planned": i18n.translate_value(readout_text(plan.get("readout") or {})) or NONE,
                 "done": i18n.translate_value(readout_text(readout)) or NONE,
                 "changed": readout_text(plan.get("readout") or {}) != readout_text(readout)})
    day_done = NONE
    if exp.readout_day:
        when = xs.day_date(exp.start_date, exp.readout_day)
        measured = when is not None and when.isoformat() in table.get("dates", [])
        day_done = gettext("Day %(n)s", n=exp.readout_day) + " · " + (
            gettext("measured") if measured else gettext("not measured yet"))
    rows.append({"what": i18n.translate_value(WHAT["readout_day"]),
                 "planned": _shown("readout_day", str(plan.get("readout_day") or "")), "done": day_done,
                 "changed": (plan.get("readout_day") or None) != (exp.readout_day or None)})
    ran = ""
    if exp.readout_day and exp.start_date:
        on = xs.day_date(exp.start_date, exp.readout_day).isoformat()
        ran = next((st["test"] for st in table.get("stats", {}).get("raw", []) if st["date"] == on and st["test"]), "")
    planned_test = test_name(plan.get("test") or "")
    now_test = test_name(exp.planned_test or "")
    done_test = i18n.translate_value(now_test) if now_test else NONE
    if ran:
        done_test = gettext("%(test)s (run on the readout day: %(ran)s)", test=done_test, ran=i18n.translate_value(ran))
    rows.append({"what": i18n.translate_value(WHAT["test"]),
                 "planned": i18n.translate_value(planned_test) or NONE, "done": done_test,
                 "changed": (plan.get("test") or "") != (exp.planned_test or "")})
    steps_now = [{"days": st.days, "kind": st.kind, "agent": st.agent, "dose": st.dose, "route": st.route,
                  "concentration": st.concentration, **xs.stimulation(st), "group": st.treatment_group,
                  "day_count": len(xs.safe_days(st))}
                 for st in exp.steps]
    done_days = sum(len(st.records) for st in exp.steps)
    regimen_now = _regimen(steps_now)
    if steps_now:
        regimen_now += " · " + gettext("%(done)s done", done=done_days)
    rows.append({"what": i18n.translate_value("Regimen"), "planned": _regimen(plan.get("steps") or []),
                 "done": regimen_now,
                 "changed": [_step_sig(s) for s in plan.get("steps") or []] != [_step_sig(s) for s in steps_now]})
    return rows


def page_data(session, exp: Experiment, place, subs, table: dict) -> dict:
    """What the experiment page and the API add for the plan."""
    plan = plan_of(exp)
    return {"planned": (exp.status or "") == "planned", "fixed": fixed(exp), "plan": plan or None,
            "readout_day": exp.readout_day, "planned_test": exp.planned_test or "",
            "planned_test_label": i18n.translate_value(test_name(exp.planned_test or "")),
            "tests": tests(), "deviations": deviations(exp),
            "comparison": comparison(session, exp, place, subs, table) if plan else []}


# ---------------------------------------------------------------- the export

def export_rows(session, exp: Experiment, place) -> list[list]:
    """The "Plan and deviations" sheet: the plan as kept at Start, then
    each change from it (stored English, as the other sheets)."""
    plan = plan_of(exp)
    if not plan:
        return []
    rows: list[list] = [["Plan kept at Start", plan.get("started_on", ""), "by " + (plan.get("started_by") or "")], []]
    rows.append(["Main readout", readout_text(plan.get("readout") or {}), (plan.get("readout") or {}).get("unit", "")])
    rows.append(["Day of the main readout", plan.get("readout_day") or ""])
    rows.append(["Statistical test", test_name(plan.get("test") or "")])
    rows.append([])
    rows.append(["Group", "Animals", "n", "Left out"])
    for grp in plan.get("groups", []):
        rows.append([grp["name"] or "(no group)", ", ".join(a["label"] for a in grp.get("animals", [])), grp.get("n"),
                     "; ".join(f"{a['label']}: {a['left_out']}" for a in grp.get("animals", []) if a.get("left_out"))])
    rows.append([])
    rows.append(["Regimen: days", "Kind", "What", "Dose", "Route", "Solution", "Group", "Stimulation"])
    for st in plan.get("steps", []):
        rows.append([st.get("days"), st.get("kind_label") or st.get("kind"), st.get("agent"), st.get("dose"),
                     st.get("route"), st.get("concentration"), st.get("group"),
                     " ".join(str(st.get(k) or "") for k in ("frequency", "intensity", "pulse_width", "duration")
                              if st.get(k))])
    rows.append([])
    rows.append(["Changes from the plan", "Before", "After", "Reason", "Who", "When", "Each change"])
    for d in exp.deviations:
        when = d.updated_at or d.created_at
        rows.append([WHAT.get(d.what, d.what), d.before, d.after, d.reason, d.username,
                     when.isoformat(sep=" ", timespec="minutes") if when else "", "; ".join((d.detail or "").split("\n"))])
    if not exp.deviations:
        rows.append(["None"])
    return rows
