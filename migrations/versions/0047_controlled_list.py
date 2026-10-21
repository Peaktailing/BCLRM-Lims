"""The controlled substances list, and what a borrow order for one must do.

A bottle of a controlled substance does not leave the shelf on a lab
member's own say-so: the borrow order waits for an approver who is not
the borrower (app/controlled.py). The list is data — the published
catalogues as rows an admin keeps current — seeded here with the entries
a teaching lab meets in its first term. The same seed ships in
app/controlled.py for a database created new; it is frozen in this
revision, because a migration must not change its mind when the list
later does.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

from migrations.helpers import create_table

revision = "0047_controlled_list"
down_revision = "0046_chemical_reference_cas"
branch_labels = None
depends_on = None

# (name, aliases, CAS number, class, note) — every CAS number passes
# app/chemlib.cas_is_valid.
_SEED = [
    ("丙酮", "Acetone, Dimethyl ketone, 二甲酮", "67-64-1", "drug precursor", "易制毒第三类"),
    ("甲基乙基酮", "Butanone, MEK, 甲乙酮", "78-93-3", "drug precursor", "易制毒第三类"),
    ("硫酸", "Sulfuric acid", "7664-93-9", "drug precursor", "易制毒第三类"),
    ("盐酸", "Hydrochloric acid", "7647-01-0", "drug precursor", "易制毒第三类"),
    ("高锰酸钾", "Potassium permanganate, KMnO4, PP粉", "7722-64-7", "drug precursor", "易制毒第三类"),
    ("苯乙酸", "Phenylacetic acid", "103-82-2", "drug precursor", "易制毒第二类"),
    ("醋酸酐", "Acetic anhydride, 乙酸酐", "108-24-7", "drug precursor", "易制毒第二类"),
    ("三氯甲烷", "Chloroform, 氯仿", "67-66-3", "drug precursor", "易制毒第二类"),
    ("乙醚", "Diethyl ether", "60-29-7", "drug precursor", "易制毒第二类"),
    ("哌啶", "Piperidine, 六氢吡啶", "110-89-4", "drug precursor", "易制毒第二类"),
    ("麻黄素", "Ephedrine, 麻黄碱", "299-42-3", "drug precursor", "易制毒第一类"),
    ("黄樟素", "Safrole", "94-59-7", "drug precursor", "易制毒第一类"),
    ("胡椒醛", "Piperonal, 天芥菜精", "120-57-0", "drug precursor", "易制毒第一类"),
    ("硝酸钾", "Potassium nitrate, 火硝", "7757-79-1", "explosive precursor", "易制爆"),
    ("硝酸钠", "Sodium nitrate", "7631-99-4", "explosive precursor", "易制爆"),
    ("硝酸钡", "Barium nitrate", "10022-31-8", "explosive precursor", "易制爆"),
    ("氯酸钾", "Potassium chlorate, 白药粉", "3811-04-9", "explosive precursor", "易制爆"),
    ("高氯酸钾", "Potassium perchlorate", "7778-74-7", "explosive precursor", "易制爆"),
    ("氯酸钠", "Sodium chlorate", "7775-09-9", "explosive precursor", "易制爆"),
    ("高氯酸钠", "Sodium perchlorate", "7601-89-0", "explosive precursor", "易制爆"),
    ("重铬酸钾", "Potassium dichromate, 红矾钾", "7778-50-9", "explosive precursor", "易制爆"),
    ("氰化钾", "Potassium cyanide, KCN", "151-50-8", "highly toxic", "剧毒"),
    ("氰化钠", "Sodium cyanide, NaCN", "143-33-9", "highly toxic", "剧毒"),
    ("三氧化二砷", "Arsenic trioxide, 砒霜, 白砒", "1327-53-3", "highly toxic", "剧毒"),
    ("五氧化二砷", "Arsenic pentoxide", "1303-28-2", "highly toxic", "剧毒"),
    ("氯化汞", "Mercuric chloride, 升汞", "7487-94-7", "highly toxic", "剧毒"),
    ("吗啡", "Morphine", "57-27-2", "narcotic or psychotropic", "麻醉药品"),
    ("咖啡因", "Caffeine", "58-08-2", "narcotic or psychotropic", "精神药品第二类"),
    ("蒂巴因", "Thebaine", "115-32-2", "narcotic or psychotropic", "麻醉药品"),
]


def upgrade() -> None:
    create_table("controlled_list")
    bind = op.get_bind()
    have = bind.execute(sa.text("select count(*) from controlled_list")).scalar()
    if not have:
        # created_at is the model's own Python-side default; a raw insert
        # has to say it, so it does, in the same words SQLite stores.
        for name, aliases, cas, dangerous_type, note in _SEED:
            bind.execute(sa.text(
                "insert into controlled_list "
                "(chemical_name, alias, cas_number, dangerous_type, notes, created_at) "
                "values (:name, :alias, :cas, :type, :note, CURRENT_TIMESTAMP)"),
                {"name": name, "alias": aliases, "cas": cas, "type": dangerous_type, "note": note})


def downgrade() -> None:
    pass
