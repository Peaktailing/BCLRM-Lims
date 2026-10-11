"""Devices that join a lab, and what they do offline.

- lab_devices: each desktop app, phone app or browser someone uses the lab
  from, signed in on its own (app/devices.py), and device_pairings, an app
  joining with a code instead of a password.
- sync_version on the records a device keeps offline (mice, cages, litters,
  weights, to-dos, racks, vials, tanks) and the sync_clock that numbers each
  change, with sync_deletions for what was deleted (app/sync_clock.py).
- sync_ops and held_changes: what a device did offline, as sent, and the
  changes that wait under Needs your decision (app/sync.py).
- lab_keys: the lab's own key, which locks backups and lab files
  (app/lab_key.py). Made when first needed, not here.

Existing records start at sync_version 0, so a device's first copy takes
them all; every change from now on gets the next number.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import add_column, create_index, create_table, has_table

revision = "0034_devices_and_sync"
down_revision = "0033_planned_experiments"
branch_labels = None
depends_on = None

SYNCED = ("mice", "mouse_cages", "litters", "mouse_weights", "tasks", "mouse_racks", "stock_units", "tanks")


def upgrade() -> None:
    for table in ("lab_devices", "device_pairings", "sync_clock", "sync_deletions", "sync_ops", "held_changes",
                  "lab_keys"):
        create_table(table)
    for table in SYNCED:
        add_column(table, sa.Column("sync_version", sa.BigInteger(), nullable=False, server_default="0"))
        create_index(table, f"ix_{table}_sync_version", ["sync_version"])
    if has_table("sync_clock"):
        bind = op.get_bind()
        if not bind.execute(sa.text("SELECT 1 FROM sync_clock WHERE id = 1")).first():
            bind.execute(sa.text("INSERT INTO sync_clock (id, value) VALUES (1, 0)"))


def downgrade() -> None:
    pass
