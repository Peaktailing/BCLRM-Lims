"""A Breeding cage can have more than one litter at a time.

A mating cage often holds two females, so a second litter comes a week or
two after the first, before the first is weaned. A cage kept one birth date
(`mouse_cages.date_give_birth`); each litter born in it is now its own row
in `cage_litters` (born, pups, dam, the litter Genotyping made of its pups,
weaned_on), with its own weaning and genotyping days. The cage's date stays,
as its oldest litter not yet weaned.

Every cage's current birth date becomes its first litter here, linked to
the litter of its pups when Genotyping made one, so nothing changes for a
lab until it records a second.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.helpers import create_table

revision = "0037_cage_litters"
down_revision = "0036_pack_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table("cage_litters")
    # A cage with a birth date and no litter row yet (start-up's create_all
    # may have made the table, empty, before this ran): its date is its
    # first litter. The litter of its pups is the one born that day with a
    # pup in the cage, as the app read it before.
    op.get_bind().execute(sa.text("""
        INSERT INTO cage_litters (cage_id_fk, born, pups, dam, litter_id_fk, weaned_on, created_at)
        SELECT c.id, c.date_give_birth, NULL, '',
               (SELECT MIN(l.id) FROM litters l JOIN mice m ON m.litter_id_fk = l.id
                 WHERE m.cage_id_fk = c.id AND l.date_of_birth = c.date_give_birth),
               NULL, CURRENT_TIMESTAMP
          FROM mouse_cages c
         WHERE c.date_give_birth IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM cage_litters x WHERE x.cage_id_fk = c.id)
    """))


def downgrade() -> None:
    pass
