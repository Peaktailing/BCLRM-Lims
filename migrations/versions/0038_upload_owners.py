"""What each uploaded file belongs to (upload_owners, app/uploads.py), so
/static/uploads/<name> is served only to someone who may see a record it
belongs to. From now on a record naming a file adds its row when it is
saved; this fills the table for everything saved before: every record
whose text names uploads/<name> (a notebook page's pictures and files, its
versions, templates, a plasmid's files, captures, anything else), found by
reading every text column of every table. Who uploaded a file was not kept
before, so a file nothing names stays its admins' only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.uploads import NOT_OWNERS, names_in
from migrations.helpers import create_table

revision = "0038_upload_owners"
down_revision = "0036_pack_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table("upload_owners")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    have = {tuple(row) for row in bind.execute(sa.text("SELECT name, source, record_id FROM upload_owners"))}
    rows = []
    for table in inspector.get_table_names():
        if table in NOT_OWNERS or table == "alembic_version":
            continue
        columns = inspector.get_columns(table)
        if "id" not in {c["name"] for c in columns}:
            continue
        for column in [c["name"] for c in columns if isinstance(c["type"], (sa.String, sa.Text))]:
            found = bind.execute(sa.text(f'SELECT id, "{column}" FROM "{table}" WHERE "{column}" LIKE :pattern'),
                                 {"pattern": "%uploads/%"})
            for record_id, value in found:
                if not isinstance(record_id, int):
                    continue
                for name in names_in(value if isinstance(value, str) else None):
                    if (name, table, record_id) not in have:
                        have.add((name, table, record_id))
                        rows.append({"name": name, "source": table, "record_id": record_id, "username": ""})
    if rows:
        owners = sa.table("upload_owners", sa.column("name"), sa.column("source"), sa.column("record_id"),
                          sa.column("username"), sa.column("created_at"))
        insert = owners.insert().values(created_at=sa.func.current_timestamp())
        for start in range(0, len(rows), 1000):
            bind.execute(insert, rows[start:start + 1000])


def downgrade() -> None:
    pass
