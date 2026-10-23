"""A version on the bottle itself, so the shelf can be read in pieces.

The chemical shelf is written in one place — the server, in one transaction —
and read from many. A phone does not keep a second copy it may edit; it keeps
a cache and asks what changed since it last looked. That question needs one
number per bottle that moves whenever anything about that bottle moves, and
the bottle until now had none: `sync_version` was on the document tables
(the orders, the courses) but not on `inventory_items`, which is the row a
bottle actually is.

Two jobs, one column:

  the cache   `GET /api/chem/cache?since=N` returns the bottles above N, and
              only the fields a shelf list shows (app/chem_cache.py)
  the write   issuing or returning a bottle names the version it saw; if the
              row is past it, someone else changed it first, and the operation
              is refused instead of written over (reagent_workflow.py)

This is not an offline watermark. Nothing is edited on a device. The animal
facility's phones still queue actions and send them later (app/sync.py); the
chemical shelf does not, because "one bottle, one state" is only true if the
server is the only writer.

The three tables a bottle is described by carry the same count:
`chem_bottle` (custodian, opening date, state), `chem_lot` (a corrected
expiry), `chem_placement` (a move). A change that touches only one of them
must still reach a cache, and a bottle's version is the newest of the four —
one number for the phone to compare, not four.

Existing rows start at 0 — older than any number the clock will hand out — so
a first read from cursor 0 returns the whole shelf once, and never again.

Revision ID: 0051_inventory_item_version
Revises: 0050_chem_tables_normalised
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import has_column, has_index, has_table

revision = "0051_inventory_item_version"
down_revision = "0050_chem_tables_normalised"
branch_labels = None
depends_on = None

TABLE = "inventory_items"
COLUMN = "sync_version"
INDEX = "ix_inventory_items_sync_version"

# The tables a bottle is described by. A change that touches only one of them
# (a custodian, a corrected expiry, a move to the student bench) still has to
# reach the cache, and a bottle's version is the newest of the four — so each
# carries the count as well.
EXTENSIONS = ("chem_bottle", "chem_lot", "chem_placement")


def upgrade() -> None:
    if not has_table(TABLE):
        return
    if not has_column(TABLE, COLUMN):
        # Not nullable with a server default: every existing bottle gets 0 in
        # the same statement, and a bottle inserted by an older process during
        # the upgrade still gets a number instead of failing.
        op.add_column(TABLE, sa.Column(COLUMN, sa.BigInteger(), nullable=False, server_default="0"))
    if not has_index(TABLE, INDEX):
        op.create_index(INDEX, TABLE, [COLUMN])
    for name in EXTENSIONS:
        index = f"ix_{name}_sync_version"
        if not has_table(name):
            continue
        if not has_column(name, COLUMN):
            op.add_column(name, sa.Column(COLUMN, sa.BigInteger(), nullable=False, server_default="0"))
        if not has_index(name, index):
            op.create_index(index, name, [COLUMN])


def downgrade() -> None:
    for name in EXTENSIONS:
        index = f"ix_{name}_sync_version"
        if not has_table(name):
            continue
        if has_index(name, index):
            op.drop_index(index, table_name=name)
        if has_column(name, COLUMN):
            op.drop_column(name, COLUMN)
    if not has_table(TABLE):
        return
    if has_index(TABLE, INDEX):
        op.drop_index(INDEX, table_name=TABLE)
    if has_column(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
