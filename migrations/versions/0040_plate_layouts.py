"""Plate layouts: which of an experiment's animals is in which well of a
96- or 384-well plate (with blanks and standards), kept to read the next
plate onto; and the plates read onto them, each kept with its values, the
choices made and the file it came from, as the source of the readings it
saved (app/plates.py). Two new tables; nothing before changes.
"""
from __future__ import annotations

from migrations.helpers import create_table

revision = "0040_plate_layouts"
down_revision = "0039_mouse_strain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table("plate_layouts")
    create_table("plate_reads")


def downgrade() -> None:
    pass
