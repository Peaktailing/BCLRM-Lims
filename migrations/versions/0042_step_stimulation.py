"""A stimulation's settings on an experiment's manipulation: frequency,
intensity, pulse width and duration, each as typed (20 Hz, 5 mW, 5 ms,
30 min), for the new Stimulation kind (optogenetic, electrical, TMS…).
Every manipulation made before starts with none.
"""
from __future__ import annotations

import sqlalchemy as sa

from migrations.helpers import add_column

revision = "0042_step_stimulation"
down_revision = "0041_sample_types"
branch_labels = None
depends_on = None

COLUMNS = ("frequency", "intensity", "pulse_width", "duration")


def upgrade() -> None:
    for name in COLUMNS:
        add_column("experiment_steps", sa.Column(name, sa.String(60), nullable=False, server_default=""))


def downgrade() -> None:
    pass
