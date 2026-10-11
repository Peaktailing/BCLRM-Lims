"""Amounts in a pack: an inventory item kept in ampoules, vials, tubes or
bottles can say what one of them holds (its "Pack size", "10 mL"), so an
amount used in mL or mg is taken off as part of one
(app/actions.py _used). Every item has none at first, so nothing changes
until a lab gives one.
"""
from __future__ import annotations

import sqlalchemy as sa

from migrations.helpers import add_column

revision = "0036_pack_size"
down_revision = "0035_box_places"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column("inventory_items", sa.Column("pack_size", sa.String(40), nullable=False, server_default=""))


def downgrade() -> None:
    pass
