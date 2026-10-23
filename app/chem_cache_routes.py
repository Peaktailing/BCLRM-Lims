"""The read side of the shelf: a cache a phone keeps, and one bottle's detail.

Three routes, one rule — this is a read-only view. Nothing here changes a
bottle; issuing, returning, moving and handing over are on the server, in
app/reagent_workflow.py, and they name the version they saw.

    GET /api/chem/cache                     the shelf, first page (or ?after=ID)
    GET /api/chem/cache?since=<cursor>      only what changed
    GET /api/chem/bottle/<id>               one bottle, everything about it

A phone stores the pages it has read and the cursor from the last answer.
Opening the shelf shows the cache at once, then asks `?since=` and patches
in what came back. No signal means a stale shelf, never a second copy of the
truth: a write needs the server, and the version check is what stops a
stale form from winning.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, make_response, request
from sqlalchemy import select

from . import chem_cache, lab
from .db import SessionLocal
from .models import ChemBottle, ChemPlacement, InventoryItem, InventoryModule

bp = Blueprint("chemcache", __name__, url_prefix="/api/chem")

# What one answer may cost. A phone on a shared connection asks for less.
MIN_PAGE, MAX_PAGE = 20, 1000


def _user():
    user = g.get("user")
    if user is None:
        abort(make_response(jsonify({"ok": False, "error": "Not signed in"}), 401))
    return user


def _int(name: str, default: int = 0) -> int:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        abort(make_response(jsonify({"ok": False, "error": f"{name} 必须是整数"}), 400))


@bp.get("/cache")
def cache():
    """The shelf, or the part of it that changed."""
    user = _user()
    limit = max(MIN_PAGE, min(MAX_PAGE, _int("limit", chem_cache.PAGE)))
    since = request.args.get("since")
    with SessionLocal() as s:
        if since is None or since == "":
            data = chem_cache.page(s, user, after=_int("after", 0), limit=limit)
        else:
            data = chem_cache.delta(s, user, _int("since"), limit=min(limit, chem_cache.MAX_DELTA))
    answer = make_response(jsonify({"ok": True, **data}))
    # The client keeps the copy; this answer is the patch, not a cacheable
    # resource. A proxy between the phone and the server must not serve an
    # older cursor back as if it were the shelf.
    answer.headers["Cache-Control"] = "no-store"
    return answer


@bp.get("/bottle/<int:item_id>")
def bottle(item_id: int):
    """One bottle in full: what the list does not carry, asked for only when
    a person opens that bottle."""
    user = _user()
    with SessionLocal() as s:
        item = s.get(InventoryItem, item_id)
        if item is None:
            abort(make_response(jsonify({"ok": False, "error": "没有这瓶试剂"}), 404))
        module = s.get(InventoryModule, item.module_id_fk)
        if module is None or module.kind != chem_cache.CHEMICAL_KIND or not lab.can_see(module, user):
            abort(make_response(jsonify({"ok": False, "error": "没有这瓶试剂"}), 403))
        # A bottle created after the extension tables existed may have no row
        # yet; it is still a bottle, and its detail is what the item says.
        row = s.get(ChemBottle, item_id)
        moves = s.scalars(select(ChemPlacement).where(ChemPlacement.item_id_fk == item_id)
                          .order_by(ChemPlacement.id.desc()).limit(10)).all()
        answer = _detail(item, row, moves)
    return jsonify({"ok": True, "bottle": answer})


def _detail(item: InventoryItem, row: ChemBottle | None, moves) -> dict:
    from .chem_cache import _cas, _state, version
    substance = row.substance if row is not None else None
    lot = row.lot if row is not None else None
    return {
        "id": item.id, "no": item.number, "name": item.name or "",
        "status": item.status or "", "qty": item.quantity or "", "unit": item.unit or "",
        "state": _state(item, row),
        "cas": _cas(item, row),
        "v": version(item, row, lot),
        "substance": None if substance is None else {
            "id": substance.id, "name": substance.name, "cas": substance.cas or "",
            "formula": substance.formula or "", "mw": substance.molecular_weight,
            "density": getattr(substance, "density", None),
            "purity": substance.purity_default, "grade": substance.grade_default or "",
            "hazard": substance.hazard or "", "storage": substance.storage_class or "",
            "msds": substance.msds_url or ""},
        "lot": None if lot is None else {
            "id": lot.id, "vendor": lot.vendor or "", "catalog": lot.catalog_number or "",
            "lot_no": lot.lot_no or "", "price": lot.unit_price,
            "produced": _d(lot.produced_on), "received": _d(lot.received_on),
            "expires": _d(lot.expires_on), "pack": lot.pack_size or ""},
        "custodian": (row.custodian if row is not None and row.custodian else item.owner) or "",
        "grade": (row.grade if row is not None else "") or "",
        "purity": row.purity if row is not None else None,
        "opened": _d(row.opened_on) if row is not None else "",
        "keeps_months": row.keeps_months if row is not None else None,
        "course": row.course_id if row is not None else None,
        # The last few moves, newest first: "when did this get to the student
        # bench, and who carried it" is the question a teaching lab asks.
        "moves": [{"at": _d(m.moved_at), "by": m.moved_by or "", "place": m.location_note or "",
                   "rack": m.rack_id_fk, "row": m.rack_row, "col": m.rack_col} for m in moves],
        "notes": item.notes or "",
    }


def _d(value) -> str:
    return value.isoformat() if value else ""
