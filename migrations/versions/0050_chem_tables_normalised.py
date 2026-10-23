"""The chemical tables get one naming rule, and the bottle table loses its
columns to the three tables they belonged to.

Two changes, deliberately in one revision because they touch the same rows:

1. **Naming.** Every chemical-domain table becomes `chem_` + a singular
   noun (docs/化学表规范与范式化设计.md). The prefix groups the tables that
   arrived together and will be merged into the main repo together; the
   singular matches the main repo's own naming, so the eventual merge is a
   column map, not a second rename.

2. **Normalisation.** A bottle used to carry everything: its substance's
   CAS, formula and hazard in an attrs key, its delivery's vendor and lot as
   columns, its place as three columns, its custodian and opening date in
   attrs. Each of those is shared (ten bottles say the same CAS), or
   happens many times (a bottle moves), or is a fact about a delivery (five
   bottles came in one carton). They move to
   `chem_substance` / `chem_lot` / `chem_bottle` / `chem_placement`, and the
   bottle keeps being a row of `inventory_items` — one number, one bottle.

Nothing is dropped and nothing is required to move at once: the old columns
and attrs keys stay, `v_chem_bottle_state` reads the new tables and shows the
old flat shape, and `v_chem_borrow_order_line` turns the new order lines into
the old one-bottle-per-order shape. That is the "expand" step; dropping the
old columns waits for the read paths (design note §5.3–5.4).

One order can now hold several bottles: the head keeps who/why/by when, and
`chem_borrow_order_item` holds one row per bottle, with the amount asked for,
issued and returned kept apart — because they differ whenever the shelf is
short, and "not issued" has to be a queryable fact rather than an inference.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op

from migrations.helpers import add_column, create_index, create_table, has_column, has_table

revision = "0050_chem_tables_normalised"
down_revision = "0049_chemical_experiment_template"
branch_labels = None
depends_on = None


# Old name -> new name. The order matters only in that a renamed table's own
# foreign keys have to point at names that exist by the time it is renamed;
# SQLite rewrites a referring column when the referred table is renamed, so
# renaming referred tables first (courses, substance, plans) is the safe way.
RENAMES = [
    ("experiment_courses", "chem_course"),
    ("chemical_references", "chem_substance"),
    ("controlled_list", "chem_controlled_list"),
    ("reagent_borrow_orders", "chem_borrow_order"),
    ("reagent_return_records", "chem_return_record"),
    ("reagent_allocation_orders", "chem_allocation_order"),
    ("reagent_demands", "chem_demand"),
    ("manager_change_logs", "chem_manager_change_log"),
    ("reagent_purchase_plans", "chem_purchase_plan"),
    ("reagent_purchase_orders", "chem_purchase_order"),
    ("chemical_experiments", "chem_experiment"),
]

# The new tables, in dependency order: a lot names its substance, a bottle
# names its lot, a placement names a bottle's item.
NEW_TABLES = ["chem_borrow_order_item", "chem_lot", "chem_bottle", "chem_placement"]

CHEMICAL_MODULE_KINDS = ("chemical_reagents", "chemicals")

# A bottle's status words on the inventory side, and the state they mean to a
# chemical bottle. "low" has no separate state: a bottle is either on the
# shelf, out, empty or gone, and how little is left is the shelf level's word.
STATE_BY_STATUS = {
    "in stock": "in_stock",
    "in use": "borrowed",
    "low": "in_stock",
    "empty": "empty",
    "used up": "empty",
    "discarded": "discarded",
}


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite holds a foreign key to a table it will not let go of while
    # enforcement is on; the rename below rewrites those references anyway.
    # PostgreSQL needs no such thing, and refuses the pragma.
    if _sqlite():
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")

    _rename_tables()
    _widen_substance()
    _widen_controlled_list()
    _make_bottle_id_optional()
    for name in NEW_TABLES:
        create_table(name)
    _backfill(bind)
    _views(bind)

    if _sqlite():
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """Left to the expand step on purpose.

    The columns this revision stops writing still exist, so the data is not
    lost: a downgrade would have to copy the facts back out of
    chem_bottle / chem_lot / chem_placement, which is a different migration
    than the opposite of this one. Until the read paths move (§5.3) this
    schema is additive, and downgrading the names alone would leave the
    models unable to load.
    """
    pass


# ── 1. names ──────────────────────────────────────────────────────────────

def _rename_tables() -> None:
    for old, new in RENAMES:
        if has_table(old) and not has_table(new):
            op.rename_table(old, new)


# ── 2. the shared facts ───────────────────────────────────────────────────

def _widen_substance() -> None:
    """What every bottle of a substance repeats, said once."""
    columns = [
        sa.Column("alias", sa.String(300), server_default=""),
        # g/mL. Nullable on purpose: a solid's density is not a number a lab
        # is asked for, and a conversion that needs one is refused rather
        # than guessed.
        sa.Column("density", sa.Float, nullable=True),
        sa.Column("purity_default", sa.Float, nullable=True),
        sa.Column("grade_default", sa.String(60), server_default=""),
        sa.Column("dangerous_type", sa.String(40), server_default=""),
        sa.Column("storage_class", sa.String(40), server_default=""),
        sa.Column("sealed_shelf_life", sa.Integer, nullable=True),
        sa.Column("unsealed_shelf_life", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    ]
    for column in columns:
        add_column("chem_substance", column)
    # The CAS index followed the table's new name. Both are the same claim
    # (one CAS, one substance), so the old name is dropped rather than kept
    # beside it — two indexes on one column would be maintained twice.
    if not has_table("chem_substance"):
        return
    existing = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("chem_substance")}
    if "ix_chemical_references_cas" in existing:
        op.drop_index("ix_chemical_references_cas", table_name="chem_substance")
    if "ix_chem_substance_cas" not in existing:
        empty = "cas != ''" if _sqlite() else "cas <> ''"
        op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_chem_substance_cas "
                   f"ON chem_substance (cas) WHERE {empty}")


def _widen_controlled_list() -> None:
    """The main repo's audit column, and its one-row-per-substance rule.

    `updated_at` is the whole of what the main repo's `controlled_list` had
    that this one did not; `notes` and `sync_version` travel the other way
    when the main repo takes them.
    """
    add_column("chem_controlled_list", sa.Column("updated_at", sa.DateTime, nullable=True))
    _add_unique_constraint("chem_controlled_list", "uq_chem_controlled_list_entry",
                           ["chemical_name", "cas_number"])


def _add_unique_constraint(table: str, name: str, columns: list[str]) -> None:
    """A unique index, which both engines treat as the constraint it is."""
    if not has_table(table):
        return
    for index in sa.inspect(op.get_bind()).get_indexes(table):
        if index.get("unique") and list(index["column_names"]) == columns:
            return
    # A constraint the database already violates would fail here; the list is
    # seeded with no duplicates, and a duplicate is a data problem the read
    # side reports better than a failed upgrade does.
    try:
        create_index(table, name, columns, unique=True)
    except Exception:  # noqa: BLE001 — a duplicate row, see above
        pass


# ── 3. the order's head stops naming one bottle ───────────────────────────

def _make_bottle_id_optional() -> None:
    """`bottle_id` described the order; now the order's items do.

    It stays, meaning "the single-line form", and a multi-line order leaves
    it NULL. SQLite can only loosen a constraint by rebuilding the table,
    which is what batch_alter_table does — the same route helpers.add_column
    takes for every column this project has added.
    """
    if not has_table("chem_borrow_order") or not has_column("chem_borrow_order", "bottle_id"):
        return
    columns = {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("chem_borrow_order")}
    if columns["bottle_id"]["nullable"]:
        return
    with op.batch_alter_table("chem_borrow_order") as batch:
        batch.alter_column("bottle_id", existing_type=sa.Integer, nullable=True)


# ── 4. what was in attrs and in the columns beside it ─────────────────────

def _backfill(bind) -> None:
    """Move each bottle's repeated facts to where they are said once.

    Done in Python rather than as a handful of correlated INSERT…SELECTs:
    the source is a JSON column, and the same substance's attributes have to
    agree across bottles, which a set-returning statement cannot reconcile
    on SQLite the way it can on PostgreSQL. Only rows that exist are read;
    a lab that keeps no bottles gets no rows.
    """
    if not (has_table("inventory_items") and has_table("chem_bottle")):
        return

    items = bind.execute(sa.text(
        "SELECT i.id, i.name, i.status, i.vendor, i.catalog_number, i.lot, i.received_on, "
        "       i.expires_on, i.pack_size, i.rack_id_fk, i.rack_row, i.rack_col, "
        "       i.location_note, i.created_at, i.attrs, m.kind "
        "FROM inventory_items i JOIN inventory_modules m ON m.id = i.module_id_fk "
        "WHERE m.kind IN :kinds").bindparams(
            sa.bindparam("kinds", value=list(CHEMICAL_MODULE_KINDS), expanding=True))).fetchall()

    if not items:
        return

    substance_id_by_cas: dict[str, int] = {}
    substance_id_by_name: dict[str, int] = {}
    for row in bind.execute(sa.text("SELECT id, name, cas FROM chem_substance")).fetchall():
        substance_id_by_name[_key(row[1])] = row[0]
        if row[2]:
            substance_id_by_cas[_key(row[2])] = row[0]

    course_id_by_name = {}
    if has_table("chem_course"):
        for row in bind.execute(sa.text("SELECT id, name FROM chem_course")).fetchall():
            course_id_by_name[_key(row[1])] = row[0]

    known_bottles = {r[0] for r in bind.execute(sa.text("SELECT item_id_fk FROM chem_bottle")).fetchall()}
    known_places = {r[0] for r in bind.execute(sa.text("SELECT item_id_fk FROM chem_placement")).fetchall()
                    if r[0] is not None} if has_table("chem_placement") else set()

    lot_ids: dict[tuple, int] = {}
    for item in items:
        (item_id, name, status, vendor, catalog, lot_no, received_on, expires_on, pack_size,
         rack_id, rack_row, rack_col, location_note, created_at, raw_attrs, _kind) = item
        attrs = _attrs(raw_attrs)
        cas = _text(attrs.get("cas"))
        substance_id = (substance_id_by_cas.get(_key(cas)) if cas else None) \
            or substance_id_by_name.get(_key(name))

        # A bottle whose substance nobody has on file yet gets a substance
        # row of its own, from what the bottle says. It is the whole point of
        # the split: the next bottle of it finds the row instead of making a
        # second copy of the same facts.
        if substance_id is None:
            substance_id = _new_substance(bind, name, cas, attrs)
            if substance_id is not None:
                substance_id_by_name[_key(name)] = substance_id
                if cas:
                    substance_id_by_cas[_key(cas)] = substance_id
        elif cas and item_id is not None:
            _fill_substance_defaults(bind, substance_id, attrs)

        lot_id = None
        if substance_id is not None and has_table("chem_lot"):
            signature = (substance_id, _text(vendor), _text(catalog), _text(lot_no))
            lot_id = lot_ids.get(signature)
            if lot_id is None:
                lot_id = _new_lot(bind, signature, received_on, expires_on, pack_size)
                lot_ids[signature] = lot_id

        if item_id not in known_bottles:
            _new_bottle(bind, item_id, substance_id, lot_id, status, attrs,
                        course_id_by_name.get(_key(attrs.get("course"))))

        if has_table("chem_placement") and item_id not in known_places:
            bind.execute(sa.text(
                "INSERT INTO chem_placement (item_id_fk, rack_id_fk, rack_row, rack_col, "
                "location_note, moved_at, moved_by) VALUES (:i, :r, :row, :col, :note, :at, '')"),
                {"i": item_id, "r": rack_id, "row": rack_row, "col": rack_col,
                 "note": _text(location_note), "at": created_at})


def _new_substance(bind, name: str, cas: str, attrs: dict) -> int | None:
    if not _text(name):
        return None
    mw = _number(attrs.get("mw")) or 0.0
    density = _number(attrs.get("density"))
    purity = _number(attrs.get("purity"))
    bind.execute(sa.text(
        "INSERT INTO chem_substance (name, molecular_weight, notes, cas, formula, mw_source, "
        "hazard, msds_url, alias, density, purity_default, grade_default, dangerous_type, "
        "storage_class, updated_at) "
        "VALUES (:name, :mw, '', :cas, :formula, :src, :hazard, '', :alias, :density, :purity, "
        ":grade, '', :storage, :now)"),
        {"name": _text(name), "mw": mw, "cas": cas, "formula": _text(attrs.get("formula")),
         "src": "manual", "hazard": _first(attrs.get("hazard")), "alias": _text(attrs.get("abbreviation")),
         "density": density, "purity": purity, "grade": _text(attrs.get("grade")),
         "storage": _text(attrs.get("storage_temp")), "now": _now()})
    found = bind.execute(sa.text("SELECT id FROM chem_substance WHERE name = :n"), {"n": _text(name)}).scalar()
    return int(found) if found is not None else None


def _fill_substance_defaults(bind, substance_id: int, attrs: dict) -> None:
    """Fill an empty default from the bottle, never overwrite a filled one.

    A bottle that says 99.5% does not get to overwrite the substance's 99%:
    the substance's is the default, and a bottle's own purity stays its own.
    """
    bind.execute(sa.text(
        "UPDATE chem_substance SET "
        "  density = COALESCE(density, :density), "
        "  purity_default = COALESCE(purity_default, :purity), "
        "  grade_default = CASE WHEN COALESCE(grade_default, '') = '' THEN :grade ELSE grade_default END, "
        "  storage_class = CASE WHEN COALESCE(storage_class, '') = '' THEN :storage ELSE storage_class END "
        "WHERE id = :id"),
        {"id": substance_id, "density": _number(attrs.get("density")),
         "purity": _number(attrs.get("purity")), "grade": _text(attrs.get("grade")),
         "storage": _text(attrs.get("storage_temp"))})


def _new_lot(bind, signature: tuple, received_on, expires_on, pack_size) -> int:
    substance_id, vendor, catalog, lot_no = signature
    bind.execute(sa.text(
        "INSERT INTO chem_lot (substance_id_fk, vendor, catalog_number, lot_no, produced_on, "
        "received_on, expires_on, pack_size, pack_unit, notes, created_at) "
        "VALUES (:s, :v, :c, :l, NULL, :received, :expires, :pack, '', '', :now)"),
        {"s": substance_id, "v": vendor, "c": catalog, "l": lot_no,
         "received": _date(received_on), "expires": _date(expires_on),
         "pack": _text(pack_size), "now": _now()})
    return int(bind.execute(sa.text("SELECT max(id) FROM chem_lot")).scalar())


def _new_bottle(bind, item_id, substance_id, lot_id, status, attrs, course_id) -> None:
    bind.execute(sa.text(
        "INSERT INTO chem_bottle (item_id_fk, substance_id_fk, lot_id_fk, custodian, grade, purity, "
        "opened_on, keeps_months, course_id, state, created_at, updated_at) "
        "VALUES (:i, :s, :l, :custodian, :grade, :purity, :opened, :keeps, :course, :state, :now, NULL)"),
        {"i": item_id, "s": substance_id, "l": lot_id,
         "custodian": _text(attrs.get("custodian")), "grade": _text(attrs.get("grade")),
         "purity": _number(attrs.get("purity")), "opened": _date(attrs.get("opened")),
         "keeps": _int(attrs.get("keeps_months")), "course": course_id,
         "state": STATE_BY_STATUS.get(_text(status).casefold(), "in_stock"),
         "now": _now()})


# ── 5. the readings that let the old shape stay readable ──────────────────

def _views(bind) -> None:
    for name, body in VIEWS:
        bind.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
        bind.exec_driver_sql(f"CREATE VIEW {name} AS {body}")


VIEWS = [
    # A bottle as the sheets read it before the split: its own columns, then
    # what the substance and the delivery say, then the state. A fact the old
    # row had in a column and the new one has in a table reads from the table
    # first and falls back to the column, so a bottle the backfill could not
    # place still reads correctly.
    ("v_chem_bottle_state", """
        SELECT i.id                        AS item_id,
               i.number                    AS number,
               i.module_id_fk              AS module_id,
               i.name                      AS name,
               i.category                  AS category,
               i.status                    AS status,
               i.owner                     AS owner,
               i.quantity                  AS quantity,
               i.unit                      AS unit,
               s.cas                       AS cas,
               s.formula                   AS formula,
               s.molecular_weight          AS molecular_weight,
               s.density                   AS density,
               COALESCE(b.purity, s.purity_default)  AS purity,
               COALESCE(NULLIF(b.grade, ''), s.grade_default) AS grade,
               s.hazard                    AS hazard,
               s.dangerous_type            AS dangerous_type,
               s.storage_class             AS storage_class,
               b.custodian                 AS custodian,
               b.opened_on                 AS opened_on,
               b.keeps_months              AS keeps_months,
               c.name                      AS course,
               COALESCE(NULLIF(l.vendor, ''), i.vendor)               AS vendor,
               COALESCE(NULLIF(l.catalog_number, ''), i.catalog_number) AS catalog_number,
               COALESCE(NULLIF(l.lot_no, ''), i.lot)                  AS lot,
               COALESCE(l.received_on, i.received_on)                 AS received_on,
               COALESCE(l.expires_on, i.expires_on)                   AS expires_on,
               COALESCE(NULLIF(l.pack_size, ''), i.pack_size)         AS pack_size,
               COALESCE(b.state, 'in_stock') AS state
        FROM inventory_items i
        LEFT JOIN chem_bottle      b ON b.item_id_fk = i.id
        LEFT JOIN chem_substance   s ON s.id = b.substance_id_fk
        LEFT JOIN chem_lot         l ON l.id = b.lot_id_fk
        LEFT JOIN chem_course      c ON c.id = b.course_id
    """),
    # One line per bottle, whether the order kept its amount on the head (the
    # orders written before this revision) or on a line (the ones after).
    ("v_chem_borrow_order_line", """
        SELECT o.id            AS order_id,
               o.number        AS number,
               o.requester     AS requester,
               o.status        AS status,
               o.purpose       AS purpose,
               o.course_id     AS course_id,
               o.due_at        AS due_at,
               COALESCE(it.item_id_fk, o.bottle_id) AS bottle_id,
               COALESCE(it.quantity, o.quantity)    AS quantity,
               COALESCE(NULLIF(it.unit, ''), o.unit) AS unit,
               COALESCE(it.issued_qty, CASE WHEN o.status IN ('borrowed', 'returned')
                                            THEN o.quantity ELSE 0 END) AS issued_qty,
               COALESCE(it.returned_qty, 0)          AS returned_qty,
               COALESCE(it.state, o.status)          AS state
        FROM chem_borrow_order o
        LEFT JOIN chem_borrow_order_item it ON it.order_id_fk = o.id
    """),
]


# ── helpers ───────────────────────────────────────────────────────────────

def _attrs(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v not in (None, ""))
    return str(value).strip()


def _key(value) -> str:
    return _text(value).casefold()


def _first(value) -> str:
    """The hazard column is one word; a multi-select's first is the closest
    single answer, and the full list stays in the bottle's attrs."""
    if isinstance(value, (list, tuple)):
        return _text(value[0])[:40] if value else ""
    return _text(value)[:40]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _date(value):
    """A date the way SQLAlchemy's Date wants it: the object, not its text."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.utcnow()
