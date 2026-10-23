"""A chemical experiment: the plan, and the yield it gave.

The planned experiments this app already had are about animals and
statistics. A chemistry experiment is about a reaction: what goes in, in
what ratio, what comes out, and how much of it. The plan is the equation
(chemlib.Reaction, as JSON of CAS numbers and coefficients) plus the
roles each substance plays; the result is the mass actually weighed and
the percent yield it comes to. The table is registered with the audit
log and the sync clock like the rest of the lab's records.
"""
from __future__ import annotations

from migrations.helpers import create_table

revision = "0048_chemical_experiments"
down_revision = "0047_controlled_list"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table("chem_experiment")


def downgrade() -> None:
    pass
