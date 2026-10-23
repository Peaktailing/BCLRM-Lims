"""The reagent document flow (teaching labs): every bottle that leaves the
shelf is asked for on a demand, signed out on a borrow order, brought back
on a return record, moved between holders on an allocation order, and
replenished on a purchase plan with its orders. The bottles themselves stay
inventory items (the chemical_reagents preset); these orders only reference
them, so a lab that keeps no bottles keeps no orders either.

Also here: experiment_courses, what a teaching lab signs bottles out
against — students borrow per course, and the semester's usage is counted
per course.
"""
from __future__ import annotations

from migrations.helpers import create_table

revision = "0045_chemical_reagent_orders"
down_revision = "0044_colony_indexes"
branch_labels = None
depends_on = None

TABLES = [
    "chem_course",
    "chem_borrow_order",
    "chem_return_record",
    "chem_allocation_order",
    "chem_demand",
    "chem_manager_change_log",
    "chem_purchase_plan",
    "chem_purchase_order",
]


def upgrade() -> None:
    # The table structures come from the models (app/models.py); the helper
    # only creates what is missing, since create_all() may have run first.
    for name in TABLES:
        create_table(name)


def downgrade() -> None:
    pass
