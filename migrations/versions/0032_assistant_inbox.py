"""The assistant's inbox: a proposal sent back with a reason, the captures
it was made from, and captures themselves (app/captures.py): what a person
wrote down or photographed at the bench, waiting to be turned into records.
"""
from __future__ import annotations

import sqlalchemy as sa

from migrations.helpers import add_column, create_table

revision = "0032_assistant_inbox"
down_revision = "0031_low_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column("proposals", sa.Column("reason", sa.Text(), nullable=False, server_default=""))
    add_column("proposals", sa.Column("captures_json", sa.Text(), nullable=False, server_default="[]"))
    create_table("captures")


def downgrade() -> None:
    pass
