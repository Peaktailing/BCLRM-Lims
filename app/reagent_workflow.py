"""The reagent document flow: borrow, approve, sign out, return.

The tables came with the reagent work (app/models.py: reagent_borrow_orders,
reagent_return_records); this is their state machine and the chain off a
chemical plan. A plan knows what the lab has of each substance
(app/chemical_experiments.py bottles_for); a borrow order is what turns a
bottle on the shelf into a bottle at a bench:

    from_plan(experiment)     one order per bottle of every substance
    decide(order, approve)    pending → approved / rejected
    sign_out(order)           approved → borrowed (the bottle: "in use")
    record_return(order, …)   borrowed → returned (the bottle: back in
                              stock, its opening date recorded)

A controlled bottle (app/controlled.py) is created pending and its
borrower may not approve it — the list decides, not the requester.

No HTTP here: the routes parse and render, this decides and computes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from . import controlled
from .models import (InventoryItem, InventoryModule, ReagentBorrowOrder,
                     ReagentReturnRecord, ExperimentCourse)

# The states a borrow order moves through; rejected and cancelled are the
# two ways out of pending without a bottle leaving the shelf.
BORROW_STATUSES = ["pending", "approved", "borrowed", "returned", "rejected", "cancelled"]

# What the page calls each state.
STATUS_LABELS = {"pending": "待审批", "approved": "已批准", "borrowed": "已领出",
                 "returned": "已归还", "rejected": "已拒绝", "cancelled": "已取消"}

RETURN_OUTCOMES = {"returned": "已归还", "partially_returned": "部分归还", "written_off": "损耗核销"}


def _next_number(session) -> int:
    return (session.scalar(select(func.max(ReagentBorrowOrder.number))) or 0) + 1


def _bottle_label(session, bottle_id: int) -> str:
    item = session.get(InventoryItem, bottle_id)
    if item is None:
        return f"#{bottle_id}"
    return item.name or f"#{bottle_id}"


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
    for order in session.scalars(stmt.order_by(ReagentBorrowOrder.id.desc()).limit(300)):
        course = session.get(ExperimentCourse, order.course_id) if order.course_id else None
        bottle = session.get(InventoryItem, order.bottle_id)
        cas = str((bottle.attrs_dict.get("cas") or "")) if bottle is not None else ""
        state = controlled.borrow_order_state(session, cas=cas, name=order.experiment_name)
        rows.append({"order": order, "bottle": _bottle_label(session, order.bottle_id),
                     "course": course.name if course else "",
                     "controlled": state["controlled"], "controlled_type": state["type"],
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


def decide(session, order_id: int, approver, approve: bool) -> str:
    """Approve or reject a pending order. Returns a message for the page;
    an empty string means it went through."""
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
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


def sign_out(session, order_id: int, actor) -> str:
    """An approved order becomes a bottle at the bench: the order goes to
    "borrowed", the bottle to "in use" (the preset's own word for it)."""
    from . import inventory_service as inventories
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
    if order.status != "approved":
        return f"只有已批准的领用单可以领出（当前：{STATUS_LABELS.get(order.status, order.status)}）"
    order.status = "borrowed"
    bottle = session.get(InventoryItem, order.bottle_id)
    module = _module_of(session, bottle)
    if module is not None:
        mv = inventories.view(module)
        # A preset whose status list has no "in use" keeps its own word:
        # the order still records the signing-out.
        inventories.apply_status(mv, bottle, "in use")
    return ""


def record_return(session, order_id: int, actor, *, returned: float = 0.0,
                  loss: float = 0.0, outcome: str = "returned", remark: str = "") -> str:
    """The bottle comes back: a return record (how much, how much lost),
    the order to "returned", and the bottle to "in stock" with the day
    it was first opened written into its attrs — the expiry arithmetic
    (BCLRM's rule: label date unopened, opening + keeps_months after)
    starts from that date."""
    from . import inventory_service as inventories
    order = session.get(ReagentBorrowOrder, order_id)
    if order is None:
        return "没有这条领用单"
    if order.status != "borrowed":
        return f"只有已领出的领用单可以归还（当前：{STATUS_LABELS.get(order.status, order.status)}）"
    if outcome not in RETURN_OUTCOMES:
        outcome = "returned"
    record = ReagentReturnRecord(
        borrow_id=order.id, bottle_id=order.bottle_id, returned_by=actor.username,
        quantity=returned, unit=order.unit or "g", loss=loss,
        outcome=outcome, remark=remark[:2000], created_by=actor.username)
    session.add(record)
    order.status = "returned"
    bottle = session.get(InventoryItem, order.bottle_id)
    if bottle is not None:
        attrs = bottle.attrs_dict
        if not attrs.get("opened"):
            attrs["opened"] = date.today().isoformat()
            bottle.attrs = json.dumps(attrs)
        module = _module_of(session, bottle)
        if module is not None:
            mv = inventories.view(module)
            inventories.apply_status(mv, bottle, "in stock")
    return ""
