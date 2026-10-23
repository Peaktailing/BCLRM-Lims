"""A student's copy remembers the template it was started from.

The teaching loop starts a template (app/chemical_experiments.py
start_from_template) and each student works their own copy. Without a
link back, a course's report can only find the copies of a template by
matching titles — which two templates of the same experiment would
share. The copy now carries the template's id, and the copies already
made are matched up by course, title and the template being older.

The column is optional and indexed: a copy is the common case, a plan
made outside any course has no template and keeps a NULL.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import add_column, create_index, has_column

revision = "0049_chemical_experiment_template"
down_revision = "0048_chemical_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column("chem_experiment", sa.Column("template_id", sa.Integer, nullable=True))
    create_index("chem_experiment", "ix_chem_experiment_template_id", ["template_id"])
    if not has_column("chem_experiment", "template_id"):
        return
    # Copies already started: the template is the older row of the same
    # title in the same course. Done in Python rather than one correlated
    # UPDATE, whose inner "FROM chemical_experiments" shadows the table
    # being updated and quietly matches nothing on SQLite.
    bind = op.get_bind()
    copies = bind.execute(sa.text(
        "SELECT id, course_id, title FROM chemical_experiments "
        "WHERE status != 'template' AND template_id IS NULL")).fetchall()
    for copy_id, course_id, title in copies:
        if course_id is None or not title:
            continue
        template_id = bind.execute(sa.text(
            "SELECT id FROM chemical_experiments "
            "WHERE course_id = :course AND title = :title AND status = 'template' AND id < :copy "
            "ORDER BY id LIMIT 1"), {"course": course_id, "title": title, "copy": copy_id}).scalar()
        if template_id:
            bind.execute(sa.text("UPDATE chemical_experiments SET template_id = :template WHERE id = :copy"),
                         {"template": template_id, "copy": copy_id})


def downgrade() -> None:
    pass
