"""The reagent document flow: borrow, approve, sign out, return.

The tables came with the reagent work (app/models.py: chem_borrow_order,
chem_return_record); this is their state machine and the chain off a
chemical plan. A plan knows what the lab has of each substance
(app/chemical_experiments.py bottles_for); a borrow order is what turns a
bottle on the shelf into a bottle at a bench:

    from_plan(experiment)     one order per bottle of every substance
    decide(order, approve)    pending → approved / rejected
    sign_out(order)           approved → borrowed (the bottle: "borrowed")
    record_return(order, …)   borrowed → returned (the bottle: in stock,
                              its opening date recorded)

A controlled bottle (app/controlled.py) is created pending and its
borrower may not approve it — the list decides, not the requester.

**These writes are online-only.** There is no queue and no replay: a bottle
changes state here, on the server, in one transaction, or it does not
change. That is what "one bottle, one state" means — a phone keeps a
read-only cache of the shelf (app/chem_cache.py) and never edits one.

Two guards make it hold when two people act at once:

  state first   a bottle only leaves the shelf if it is on the shelf; an
                approved order for a bottle already out is refused rather
                than issued twice
  version       the form carries the version it showed (`v`, from
                chem_cache); if the bottle moved on, the write is refused
                with "someone changed it first" instead of overwriting

An order is an intention; the bottle is the fact. Two orders may ask for the
same bottle — a plan for another course, a second click on 生成领用单 — and
that is allowed to stand, because an order is a thing a person can cancel.
What may not happen is both of them taking the bottle: the second sign-out
finds it out of stock and is refused, which is the check that matters.

The order's own status machine stops a double submit (a second sign-out
finds "borrowed", not "approved"). Neither guard is optional: the status
check protects the order, the version check protects the bottle.

No HTTP here: the routes parse and render, this decides and computes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from . import controlled
from .models import (ChemBottle, InventoryItem, InventoryModule, ReagentBorrowOrder,
                     ReagentReturnRecord, ExperimentCourse)

# The states a borrow order moves through; rejected and cancelled are the
# two ways out of pending without a bottle leaving the shelf.
BORROW_STATUSES = ["pending", "approved", "borrowed", "returned", "rejected", "cancelled"]

# What the page calls each state.
STATUS_LABELS = {"pending": "待审批", "approved": "已批准", "borrowed": "已领出",
                 "returned": "已归还", "rejected": "已拒绝", "cancelled": "已取消"}

# A bottle's own state (chem_bottle.state). Empty counts as in stock: a bottle
# written before the extension existed says nothing, and nothing is not "out".
BOTTLE_LABELS = {"in_stock": "在库", "borrowed": "已领出", "empty": "已用尽", "discarded": "已处置"}

RETURN_OUTCOMES = {"returned": "已归还", "partially_returned": "部分归还", "written_off": "损耗核销"}


def _next_number(session) -> int:
    return (session.scalar(select(func.max(ReagentBorrowOrder.number))) or 0) + 1


def _bottle_label(session, bottle_id: int) -> str:
    item = session.get(InventoryItem, bottle_id)
    if item is None:
        return f"#{bottle_id}"
    return item.name or f"#{bottle_id}"


def _bottle_row(session, bottle: InventoryItem) -> ChemBottle:
    """The bottle's extension row, made now if this bottle was created after
    the extension tables existed.

    Not a migration, and not a second source of truth: the row is where a
    bottle's state, custodian and opening date live, and a bottle may be
    created through the inventory page before anything has written to it.
    Making it here means the first write leaves a complete record rather than
    a row that only some paths fill in.
    """
    row = session.get(ChemBottle, bottle.id)
    if row is None:
        row = ChemBottle(item_id_fk=bottle.id, custodian=bottle.owner or "",
                         grade=str(bottle.attrs_dict.get("grade") or ""),
                         state="in_stock")
        session.add(row)
        session.flush()
    return row


def _guard(session, bottle: InventoryItem | None, expected: int | None, *, must_be_in_stock: bool) -> str:
    """The two checks every bottle write makes. Returns a message, or "".

    `expected` is the version the operator's form showed. None means the
    caller did not show one (a script, an import) and only the state check
    applies.
    """
    from . import chem_cache
    if bottle is None:
        return "领用单指向的试剂瓶已不存在"
    row = session.get(ChemBottle, bottle.id)
    try:
        chem_cache.require(bottle, expected, row, row.lot if row is not None else None)
    except chem_cache.Stale as stale:
        return str(stale)
    if must_be_in_stock and row is not None:
        state = row.state or "in_stock"
        if state != "in_stock":
            return f"这瓶现在是「{BOTTLE_LABELS.get(state, state)}」，不能领出"
    return ""


def orders(session, *, status: str = "", course_id: int | None = None,
           mine: str = "") -> list[dict]:
    """The borrow orders, newest first, with what the list page shows:
    the bottle, the course, and whether a signed-out one is overdue."""
    stmt = select(ReagentBorrowOrder)
    if status in BORROW_STATUSES:
        stmt = stmt.where(ReagentBorrowOrder.status == status)
    if course_id is not None:
        stmt = stmt.where(ReagentBorrowOrder.course_id == course_id)
    if mine:
        stmt = stmt.where(ReagentBorrowOrder.requester == mine)
    rows = []
    now = datetime.utcnow()
    listing = list(session.scalars(stmt.order_by(ReagentBorrowOrder.id.desc()).limit(300)))
    # One query for all the bottles' extension rows, not one per order: the
    # page shows each bottle's version on its form (the write sends it back),
    # and a list of 300 orders should not cost 300 extra queries.
    ids = [o.bottle_id for o in listing if o.bottle_id]
    bottles = {b.item_id_fk: b for b in session.scalars(
        select(ChemBottle).where(ChemBottle.item_id_fk.in_(ids)))} if ids else {}
    from . import chem_cache
    for order in listing:
        course = session.get(ExperimentCourse, order.course_id) if order.course_id else None
        bottle = session.get(InventoryItem, order.bottle_id)
        cas = str((bottle.attrs_dict.get("cas") or "")) if bottle is not None else ""
        state = controlled.borrow_order_state(session, cas=cas, name=order.experiment_name)
        row = bottles.get(order.bottle_id)
        rows.append({"order": order, "bottle": _bottle_label(session, order.bottle_id),
                     "course": course.name if course else "",
                     "controlled": state["controlled"], "controlled_type": state["type"],
                     "bottle_state": (row.state or "in_stock") if row is not None else "in_stock",
                     # What the form shows and sends back with the write.
                     "v": chem_cache.version(bottle, row, row.lot if row is not None else None)
                          if bottle is not None else 0,
                     "overdue": order.status == "borrowed" and order.due_at is not None
                                and order.due_at < now})
    return rows


def may_decide(order: ReagentBorrowOrder, user) -> bool:
    """Who may approve a pending order: an admin, or anyone who is not the
    person who asked for it. A controlled order's borrower is never its
    approver — that is the whole point of the list."""
    if user is None:
        return False
    if getattr(user, "role", "") == "admin":
        return True
    return user.username != order.requester


def from_plan(session, experiment, requester: str, *, due_days: int = 14) -> dict:
    """A plan's substances become borrow orders, one per bottle the lab
    has of each. Controlled bottles wait for an approver; the rest are
    approved straight away — a member may sign out the lab's own stock
    on their own say-so, the list only stops what it names.

    Returns {"made": [ids], "pending": n, "skipped": [names]}.
    """
    from . import chemical_experiments as plans
    made: list[int] = []
    pending = 0
    skipped: list[str] = []
    due_at = datetime.utcnow() + timedelta(days=due_days)
    for row in plans.stock_check(session, experiment):
        if not row["in_stock"]:
            skipped.append(row["name"] or row["cas"])
            continue
        for bottle in row["bottles"]:
            if not bottle["available"]:
                continue
            state = controlled.borrow_order_state(session, cas=row["cas"], name=row["name"],
                                                  bottle_controlled=row["controlled"])
            order = ReagentBorrowOrder(
                number=_next_number(session), bottle_id=bottle["item_id"],
                requester=requester, status=state["status"] or "approved",
                quantity=0.0, unit="g",
                purpose=f"{experiment.title}（化学实验方案）",
                course_id=experiment.course_id, experiment_name=experiment.title,
                due_at=due_at if state["status"] else None,
                created_by=requester)
            session.add(order)
            session.flush()
            made.append(order.id)
            if state["status"] == "pending":
                pending += 1
    return {"made": made, "pending": pending, "skipped": skipped}


def decide(session, order_id: int, approver, approve: bool, *, expected_version: int | None = None) -> str:
    """Approve or reject a pending order. Returns a message for the page;
    an empty string means it went through."""
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
    if expected_version is not None and int(order.sync_version or 0) != int(expected_version):
        return "这条领用单在你查看之后已经被改动过，请刷新后重新确认"
    if order.status != "pending":
        return f"这条领用单已经处理过了（{STATUS_LABELS.get(order.status, order.status)}）"
    if not may_decide(order, approver):
        return "申请人不能审批自己的领用单"
    order.status = "approved" if approve else "rejected"
    order.approver = approver.username
    order.decided_at = datetime.utcnow()
    return ""


def _module_of(session, bottle: InventoryItem | None):
    """The bottle's database, for the status word list (an item carries
    its module's id, not the module)."""
    if bottle is None:
        return None
    return session.get(InventoryModule, bottle.module_id_fk)


def sign_out(session, order_id: int, actor, *, expected_version: int | None = None) -> str:
    """An approved order becomes a bottle at the bench: the order goes to
    "borrowed", the bottle to "borrowed" (chem_bottle.state) and to the
    preset's own word for it ("in use").

    Refused when the bottle is not on the shelf — it may have been signed
    out on another order, emptied or discarded since this order was
    approved — or when it is past the version the form showed."""
    from . import inventory_service as inventories
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
    if order.status != "approved":
        return f"只有已批准的领用单可以领出（当前：{STATUS_LABELS.get(order.status, order.status)}）"
    bottle = session.get(InventoryItem, order.bottle_id)
    problem = _guard(session, bottle, expected_version, must_be_in_stock=True)
    if problem:
        return problem
    order.status = "borrowed"
    row = _bottle_row(session, bottle)
    row.state = "borrowed"
    row.updated_at = datetime.utcnow()
    module = _module_of(session, bottle)
    if module is not None:
        mv = inventories.view(module)
        # A preset whose status list has no "in use" keeps its own word:
        # the order still records the signing-out.
        inventories.apply_status(mv, bottle, "in use")
    return ""


def record_return(session, order_id: int, actor, *, returned: float = 0.0,
                  loss: float = 0.0, outcome: str = "returned", remark: str = "",
                  expected_version: int | None = None) -> str:
    """The bottle comes back: a return record (how much, how much lost),
    the order to "returned", and the bottle to "in stock" with the day it
    was first opened written where the expiry arithmetic reads it — the
    bottle's own `opened_on`, and the item's attrs key for older readers
    (BCLRM's rule: label date unopened, opening + keeps_months after)."""
    from . import inventory_service as inventories
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
    if order.status != "borrowed":
        return f"只有已领出的领用单可以归还（当前：{STATUS_LABELS.get(order.status, order.status)}）"
    if outcome not in RETURN_OUTCOMES:
        outcome = "returned"
    bottle = session.get(InventoryItem, order.bottle_id)
    problem = _guard(session, bottle, expected_version, must_be_in_stock=False)
    if problem:
        return problem
    record = ReagentReturnRecord(
        borrow_id=order.id, bottle_id=order.bottle_id, returned_by=actor.username,
        quantity=returned, unit=order.unit or "g", loss=loss,
        outcome=outcome, remark=remark[:2000], created_by=actor.username)
    session.add(record)
    order.status = "returned"
    if bottle is not None:
        row = _bottle_row(session, bottle)
        if row.opened_on is None:
            row.opened_on = date.today()
        row.state = "in_stock"
        row.updated_at = datetime.utcnow()
        attrs = bottle.attrs_dict
        if not attrs.get("opened"):
            attrs["opened"] = date.today().isoformat()
            bottle.attrs = json.dumps(attrs)
        module = _module_of(session, bottle)
        if module is not None:
            mv = inventories.view(module)
            inventories.apply_status(mv, bottle, "in stock")
    return ""
