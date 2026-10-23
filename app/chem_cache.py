"""The shelf as a phone reads it: only what changed, only what a list shows.

The chemical shelf has one writer — this server, in one transaction. Nothing
is edited on a device. A phone keeps a cache so that opening the shelf is not
a download of the whole store room, and asks two questions:

    GET /api/chem/cache                     the first page, by id
    GET /api/chem/cache?since=<cursor>      only the bottles that changed
    GET /api/chem/cache?after=<id>          the next page, by id

Every answer carries `cursor`: the lab's change count at the moment it was
read. Passing it back returns the changes made since, and nothing else.

Three decisions worth knowing:

**A bottle's version is the newest of four rows.** A bottle is an
`inventory_items` row, and what happens to it lands in one of three
extension tables: a custodian change in `chem_bottle`, a corrected expiry in
`chem_lot`, a move in `chem_placement`. Each is stamped by the same lab
count (app/sync_clock.py), so the newest of the four is a version that moves
whenever anything about that bottle moves — one number, not four to compare.
The same number is what a write names when it says which state it saw
(`require`).

**The projection is fixed and short.** `FIELDS` is what a shelf list shows
and nothing else — no vendor, no price, no notes, no molecular weight. A
phone that needs a detail asks for that one bottle. Adding a field here is a
decision about the wire, not about the table.

**Too much changed means start again.** If more than `MAX_DELTA` bottles are
past the cursor, the answer says `reset` and the phone pages the shelf by id
instead. Sending 20 000 rows to save a round trip is not a saving.

Read-only: this module never writes. Writes are in
app/reagent_workflow.py, on the server, guarded by the same version.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import func, select

from . import lab, sync_clock
from .models import ChemBottle, ChemLot, ChemPlacement, InventoryItem, InventoryModule, SyncDeletion

# What a shelf list shows. The order is the wire order; a client may rely on
# the names, never on the positions.
FIELDS = ("id", "no", "name", "cas", "qty", "unit", "state", "custodian", "place", "expires", "v")

# A page of the shelf, and the most changes worth sending in one answer.
PAGE = 500
MAX_DELTA = 2000

# The preset a bottle database came from (inventory_modules.kind). A bottle is
# recognised by the database it lives in, not by whether its extension row
# exists yet: a bottle just created through the page has no chem_bottle row
# until something writes to it, and it is still a bottle.
CHEMICAL_KIND = "chemical_reagents"

# The preset's words for a bottle that is out, used when there is no
# chem_bottle row to say it (inventory_modules statuses).
STATE_BY_ITEM_STATUS = {"in use": "borrowed", "empty": "empty", "discarded": "discarded"}


class Stale(Exception):
    """The bottle is past the version the caller read.

    Not an error to retry blindly: someone issued, returned or moved that
    bottle first, and the caller is holding a shelf that no longer exists.
    """


# ------------------------------------------------------------------ versions

def version(item: InventoryItem, bottle: ChemBottle | None = None,
            lot: ChemLot | None = None) -> int:
    """The number this bottle is at: the newest of the rows that describe it."""
    return max(int(getattr(item, "sync_version", 0) or 0),
               int(getattr(bottle, "sync_version", 0) or 0) if bottle is not None else 0,
               int(getattr(lot, "sync_version", 0) or 0) if lot is not None else 0)


def require(item: InventoryItem, expected: int | None, bottle: ChemBottle | None = None,
            lot: ChemLot | None = None) -> None:
    """Refuse a write made against a shelf that has moved on.

    `expected` is what the operator's form said it saw. None means "I did not
    look" (an admin tool, an import): allowed, since the state checks in the
    write path still hold. A number means "exactly this state", and anything
    else raises Stale.
    """
    if expected is None:
        return
    current = version(item, bottle, lot)
    if current != int(expected):
        raise Stale(f"这瓶在你查看之后已经被改动过（你看的是第 {int(expected)} 版，现在是第 {current} 版）")


# ------------------------------------------------------------------ loading

def _modules(session, user) -> dict[int, InventoryModule]:
    """The reagent databases this person may open, by id."""
    return {m.id: m for m in session.scalars(select(InventoryModule))
            if m.kind == CHEMICAL_KIND and lab.can_see(m, user)}


def _place_of(session, item_ids: Iterable[int]) -> dict[int, str]:
    """Each bottle's current place: the newest placement row, not the latest
    timestamp. Two moves in the same second are ordered by id, and only id
    is written in commit order."""
    ids = list(item_ids)
    if not ids:
        return {}
    newest = select(ChemPlacement.item_id_fk, func.max(ChemPlacement.id).label("pid")).where(
        ChemPlacement.item_id_fk.in_(ids)).group_by(ChemPlacement.item_id_fk).subquery()
    rows = session.execute(select(ChemPlacement.item_id_fk, ChemPlacement.location_note)
                           .join(newest, ChemPlacement.id == newest.c.pid))
    return {item_id: note or "" for item_id, note in rows}


def _bottles_of(session, ids: list[int]) -> dict[int, ChemBottle]:
    if not ids:
        return {}
    return {b.item_id_fk: b for b in session.scalars(select(ChemBottle).where(ChemBottle.item_id_fk.in_(ids)))}


def _state(item: InventoryItem, bottle: ChemBottle | None) -> str:
    """The bottle's state: its own row's, or — before anything has written one
    — the preset's word on the inventory item ("in use" is out)."""
    if bottle is not None and bottle.state:
        return bottle.state
    return STATE_BY_ITEM_STATUS.get(item.status or "", "in_stock")


def _cas(item: InventoryItem, bottle: ChemBottle | None) -> str:
    """The CAS as the substance says it, falling back to the bottle's own copy
    (a bottle whose substance was never linked keeps what it was catalogued
    with)."""
    if bottle is not None and bottle.substance is not None and bottle.substance.cas:
        return bottle.substance.cas
    return str(item.attrs_dict.get("cas") or "")


def _row(item: InventoryItem, bottle: ChemBottle | None, place: str) -> dict:
    lot = bottle.lot if bottle is not None else None
    expires = (lot.expires_on if lot is not None and lot.expires_on else item.expires_on)
    return {"id": item.id,
            "no": item.number,
            "name": item.name or "",
            "cas": _cas(item, bottle),
            "qty": item.quantity or "",
            "unit": item.unit or "",
            "state": _state(item, bottle),
            "custodian": (bottle.custodian if bottle is not None and bottle.custodian else item.owner) or "",
            "place": place,
            "expires": expires.isoformat() if isinstance(expires, date) else "",
            "v": version(item, bottle, lot)}


def _load(session, ids: list[int], modules: dict[int, InventoryModule]) -> list[dict]:
    """The shelf rows for these ids, as this person may see them."""
    if not ids:
        return []
    items = [i for i in session.scalars(select(InventoryItem).where(InventoryItem.id.in_(ids)))
             if i.module_id_fk in modules]
    if not items:
        return []
    bottles = _bottles_of(session, [i.id for i in items])
    places = _place_of(session, [i.id for i in items])
    rows = [_row(i, bottles.get(i.id), places.get(i.id, "")) for i in items]
    rows.sort(key=lambda r: r["id"])
    return rows


def _visible_ids(session, modules: dict[int, InventoryModule]) -> set[int]:
    return {i for i in session.scalars(select(InventoryItem.id).where(
        InventoryItem.module_id_fk.in_(list(modules))))} if modules else set()


# ------------------------------------------------------------------ reading

def page(session, user, *, after: int = 0, limit: int = PAGE) -> dict:
    """The shelf in id order, from `after`. For a phone's first copy, and for
    the case where too much changed to send as a delta."""
    modules = _modules(session, user)
    cursor = sync_clock.current(session)
    rows = _load(session, list(session.scalars(
        select(InventoryItem.id).where(InventoryItem.module_id_fk.in_(list(modules)),
                                       InventoryItem.id > after)
        .order_by(InventoryItem.id).limit(limit + 1))) if modules else [], modules)
    more = len(rows) > limit
    rows = rows[:limit]
    return {"cursor": cursor, "reset": False, "fields": list(FIELDS), "bottles": rows,
            "gone": [], "more": more, "after": rows[-1]["id"] if rows and more else 0}


def delta(session, user, since: int, *, limit: int = MAX_DELTA) -> dict:
    """The bottles changed after `since`, and those that went.

    The cursor is read *before* the rows, so a change committed while this
    answer is being built is not lost: it lands above the cursor we return,
    and comes again with the next question.
    """
    modules = _modules(session, user)
    cursor = sync_clock.current(session)
    if since > cursor:                     # a cursor from another lab, or a database replaced
        return {"cursor": cursor, "reset": True, "fields": list(FIELDS), "bottles": [],
                "gone": [], "more": False, "after": 0}
    changed: set[int] = set()
    if modules:
        changed |= set(session.scalars(select(InventoryItem.id).where(
            InventoryItem.sync_version > since, InventoryItem.module_id_fk.in_(list(modules)))))
        changed |= set(session.scalars(select(ChemBottle.item_id_fk).where(ChemBottle.sync_version > since)))
        lot_ids = list(session.scalars(select(ChemLot.id).where(ChemLot.sync_version > since)))
        if lot_ids:
            changed |= set(session.scalars(select(ChemBottle.item_id_fk).where(ChemBottle.lot_id_fk.in_(lot_ids))))
        changed |= set(session.scalars(select(ChemPlacement.item_id_fk).where(ChemPlacement.sync_version > since)))
    if len(changed) > limit:
        # More than a delta is worth: the phone pages the shelf instead. The
        # cursor stays where it was, so nothing is skipped by accident.
        return {"cursor": since, "reset": True, "fields": list(FIELDS), "bottles": [],
                "gone": [], "more": True, "after": 0}
    rows = _load(session, sorted(changed), modules)
    seen = {r["id"] for r in rows}
    gone = [d.record_id for d in session.scalars(select(SyncDeletion).where(
        SyncDeletion.table_name == "inventory_items", SyncDeletion.sync_version > since))
        if d.record_id not in seen]
    # A bottle still there but no longer visible (its database was made
    # private, or it was moved to one this person cannot open) goes too.
    visible = _visible_ids(session, modules)
    gone += [i for i in changed if i not in visible and i not in gone]
    return {"cursor": cursor, "reset": False, "fields": list(FIELDS), "bottles": rows,
            "gone": sorted(set(gone)), "more": False, "after": 0}
