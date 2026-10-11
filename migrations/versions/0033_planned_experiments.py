"""Planned experiments and changes from the plan: an experiment can be
designed ("planned") before it starts; Start keeps a copy of the design
(experiments.plan_json), with the main readout's day (readout_day) and the
statistical test planned (planned_test). Changes from it afterwards are
kept with their reason in experiment_deviations, and an animal can be left
out of the analysis (left_out, its reason) in experiment_mice and
experiment_subjects. Experiments already there have no plan copy and
behave as before (app/experiment_plan.py).
"""
from __future__ import annotations

import sqlalchemy as sa

from migrations.helpers import add_column, create_table

revision = "0033_planned_experiments"
down_revision = "0031_low_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column("experiments", sa.Column("plan_json", sa.Text(), nullable=True, server_default=""))
    add_column("experiments", sa.Column("readout_day", sa.Integer(), nullable=True))
    add_column("experiments", sa.Column("planned_test", sa.String(20), nullable=True, server_default=""))
    add_column("experiment_mice", sa.Column("left_out", sa.String(200), nullable=True, server_default=""))
    add_column("experiment_subjects", sa.Column("left_out", sa.String(200), nullable=True, server_default=""))
    create_table("experiment_deviations")


def downgrade() -> None:
    pass
