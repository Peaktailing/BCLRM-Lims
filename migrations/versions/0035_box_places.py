"""Where a box is kept (#58): an inventory box, shelf or drawer can say
which fridge, freezer or cabinet it is in ("Kept in"), so a chemical is
found by its cabinet ("Fridge 2 › Box A · B3"). Every box has none at
first, so nothing changes until a lab says where its boxes are.
"""
from __future__ import annotations

import sqlalchemy as sa

from migrations.helpers import add_column

revision = "0035_box_places"
down_revision = "0034_devices_and_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column("inventory_racks", sa.Column("place", sa.String(120), nullable=False, server_default=""))


def downgrade() -> None:
    pass
