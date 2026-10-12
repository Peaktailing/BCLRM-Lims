"""A mouse's strain: its background, C57BL/6J, BALB/cJ or mixed, in a
column of its own after the Custom tag. Until now it went in the genotype
or the notes, where neither a filter nor a sort could find it. Every mouse
starts with none.

The Strain column offers the colony's strain choices (Dropdowns), and a
lab that has none yet starts with the strains most mouse labs keep.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import add_column, has_table

revision = "0039_mouse_strain"
down_revision = "0038_upload_owners"
branch_labels = None
depends_on = None

DEFAULTS = ("C57BL/6J", "C57BL/6N", "BALB/cJ", "129S1/SvImJ", "FVB/NJ", "DBA/2J",
            "C3H/HeJ", "NOD/ShiLtJ", "CD-1", "Mixed")


def upgrade() -> None:
    add_column("mice", sa.Column("strain", sa.String(120), nullable=False, server_default=""))
    if has_table("dropdown_options"):
        bind = op.get_bind()
        has_any = bind.execute(sa.text(
            "SELECT 1 FROM dropdown_options WHERE field_name = 'strain'")).first()
        if has_any is None:
            for value in DEFAULTS:
                bind.execute(sa.text("INSERT INTO dropdown_options (field_name, option_value, created_at) "
                                     "VALUES ('strain', :v, CURRENT_TIMESTAMP)"), {"v": value})


def downgrade() -> None:
    pass
