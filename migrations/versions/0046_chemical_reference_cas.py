"""A chemical reference learns its CAS number and formula.

The built-in molecular weights were a name and a number, which is all a
Formulation needed. A reaction needs more: which substance is it really
(the CAS number, check digit and all), what it is made of (the formula,
so the molecular weight can be recomputed rather than trusted), whether
it is controlled, and where its safety data sheet hangs. All of it is
optional — a reference from an older version keeps working with the name
and weight it already had.

The unique index on the CAS number is partial: an empty CAS is not a
claim on a substance, and a database where nobody has filled one in yet
must not refuse a second row for it. The same index is in the model, so
a database created new has it before this revision runs; this only adds
it to one that is being upgraded.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import add_column, has_index

revision = "0046_chemical_reference_cas"
down_revision = "0045_chemical_reagent_orders"
branch_labels = None
depends_on = None

# The names an installation starts with (app/services.py seeds them), so a
# lab upgrading here can have its built-in weights given their CAS number
# and formula. Frozen in this revision on purpose: a migration must not
# change its mind when the seed list later does. The molecular weight the
# lab already has stays what it is — only the identity is filled in.
_BACKFILL = {
    "NaCl": ("7647-14-5", "NaCl"),
    "KCl": ("7447-40-7", "KCl"),
    "Tris base": ("77-86-1", "C4H11NO3"),
    "EDTA": ("60-00-4", "C10H16N2O8"),
    "Glucose": ("50-99-7", "C6H12O6"),
    "Sucrose": ("57-50-1", "C12H22O11"),
    "HEPES": ("7365-45-9", "C8H18N2O4S"),
    "CaCl2": ("10043-52-4", "CaCl2"),
    "MgCl2": ("7786-30-3", "MgCl2"),
}


def upgrade() -> None:
    add_column("chemical_references", sa.Column("cas", sa.String(20), nullable=False, server_default=""))
    add_column("chemical_references", sa.Column("formula", sa.String(120), nullable=False, server_default=""))
    add_column("chemical_references", sa.Column("mw_source", sa.String(10), nullable=False, server_default="manual"))
    add_column("chemical_references", sa.Column("hazard", sa.String(40), nullable=False, server_default=""))
    add_column("chemical_references", sa.Column("msds_url", sa.String(500), nullable=False, server_default=""))
    if not has_index("chemical_references", "ix_chemical_references_cas"):
        name = op.get_bind().dialect.name
        if name == "postgresql":
            op.create_index("ix_chemical_references_cas", "chemical_references", ["cas"],
                            unique=True, postgresql_where=sa.text("cas <> ''"))
        else:
            op.create_index("ix_chemical_references_cas", "chemical_references", ["cas"],
                            unique=True, sqlite_where=sa.text("cas != ''"))
    references = sa.table(
        "chemical_references",
        sa.column("name", sa.String), sa.column("cas", sa.String), sa.column("formula", sa.String))
    bind = op.get_bind()
    for name, (cas, formula) in _BACKFILL.items():
        bind.execute(references.update()
                     .where(references.c.name == name, references.c.cas == "")
                     .values(cas=cas, formula=formula))


def downgrade() -> None:
    try:
        op.drop_index("ix_chemical_references_cas", table_name="chemical_references")
    except Exception:
        pass
