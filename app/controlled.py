"""The controlled substances list, and the approval a borrow order needs.

A bottle of a controlled substance does not leave the shelf on a lab
member's own say-so. When a borrow order is made for one, the order
waits: it is created pending, and the person who asked for the bottle
cannot also be the one who lets it go — an approver is someone else
(app/access.py decides who may approve; this decides whether it must).

Matching is the way BCLRM taught it: the CAS number first (exact), then
the name, then the aliases, all compared without spaces or case, because
"acetone" and "Acetone " and "丙酮" arrive from as many catalogues as
there are bottles. A name match is only a hint — the CAS number is the
identity — so a bottle whose own CAS number is on the list is controlled
whatever it is called, and a bottle marked controlled in its own hazard
attrs stays controlled even if the list has not caught up yet.
"""
from __future__ import annotations

import re
from sqlalchemy import select

from .models import ControlledList

# The catalogue classes, in the words the Hazard field already uses
# (app/inventory.py HAZARDS), so a bottle and the list never disagree
# about what something is.
PRECURSOR = "drug precursor"                 # 易制毒
EXPLOSIVE_PRECURSOR = "explosive precursor"  # 易制爆
HIGHLY_TOXIC = "highly toxic"                # 剧毒
NARCOTIC = "narcotic or psychotropic"        # 麻醉或精神药品

_ALIAS_SPLIT = re.compile(r"[,，、;；/]")


def _normalize(value) -> str:
    """A name as matching sees it: no spaces, no case, no punctuation
    differences that come from a catalogue rather than a substance."""
    return "".join(str(value or "").split()).lower()


# What a new installation starts with: the entries a teaching lab meets
# in its first term, from the published Chinese catalogues (易制毒化学品
# 管理条例、易制爆危险化学品名录、剧毒化学品目录、麻醉药品和精神药品
# 品种目录). Every CAS number here passes chemlib.cas_is_valid. An admin
# keeps the list current as the catalogues are reissued — this is a
# starting point, not the law.
DEFAULT_CONTROLLED = [
    # (name, aliases, CAS number, class, note)
    ("丙酮", "Acetone, Dimethyl ketone, 二甲酮", "67-64-1", PRECURSOR, "易制毒第三类"),
    ("甲基乙基酮", "Butanone, MEK, 甲乙酮", "78-93-3", PRECURSOR, "易制毒第三类"),
    ("硫酸", "Sulfuric acid", "7664-93-9", PRECURSOR, "易制毒第三类"),
    ("盐酸", "Hydrochloric acid", "7647-01-0", PRECURSOR, "易制毒第三类"),
    ("高锰酸钾", "Potassium permanganate, KMnO4, PP粉", "7722-64-7", PRECURSOR, "易制毒第三类"),
    ("苯乙酸", "Phenylacetic acid", "103-82-2", PRECURSOR, "易制毒第二类"),
    ("醋酸酐", "Acetic anhydride, 乙酸酐", "108-24-7", PRECURSOR, "易制毒第二类"),
    ("三氯甲烷", "Chloroform, 氯仿", "67-66-3", PRECURSOR, "易制毒第二类"),
    ("乙醚", "Diethyl ether", "60-29-7", PRECURSOR, "易制毒第二类"),
    ("哌啶", "Piperidine, 六氢吡啶", "110-89-4", PRECURSOR, "易制毒第二类"),
    ("麻黄素", "Ephedrine, 麻黄碱", "299-42-3", PRECURSOR, "易制毒第一类"),
    ("黄樟素", "Safrole", "94-59-7", PRECURSOR, "易制毒第一类"),
    ("胡椒醛", "Piperonal, 天芥菜精", "120-57-0", PRECURSOR, "易制毒第一类"),
    ("硝酸钾", "Potassium nitrate, 火硝", "7757-79-1", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("硝酸钠", "Sodium nitrate", "7631-99-4", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("硝酸钡", "Barium nitrate", "10022-31-8", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("氯酸钾", "Potassium chlorate, 白药粉", "3811-04-9", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("高氯酸钾", "Potassium perchlorate", "7778-74-7", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("氯酸钠", "Sodium chlorate", "7775-09-9", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("高氯酸钠", "Sodium perchlorate", "7601-89-0", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("重铬酸钾", "Potassium dichromate, 红矾钾", "7778-50-9", EXPLOSIVE_PRECURSOR, "易制爆"),
    ("氰化钾", "Potassium cyanide, KCN", "151-50-8", HIGHLY_TOXIC, "剧毒"),
    ("氰化钠", "Sodium cyanide, NaCN", "143-33-9", HIGHLY_TOXIC, "剧毒"),
    ("三氧化二砷", "Arsenic trioxide, 砒霜, 白砒", "1327-53-3", HIGHLY_TOXIC, "剧毒"),
    ("五氧化二砷", "Arsenic pentoxide", "1303-28-2", HIGHLY_TOXIC, "剧毒"),
    ("氯化汞", "Mercuric chloride, 升汞", "7487-94-7", HIGHLY_TOXIC, "剧毒"),
    ("吗啡", "Morphine", "57-27-2", NARCOTIC, "麻醉药品"),
    ("咖啡因", "Caffeine", "58-08-2", NARCOTIC, "精神药品第二类"),
    ("蒂巴因", "Thebaine", "115-32-2", NARCOTIC, "麻醉药品"),
]


def match(session, cas: str = "", name: str = "") -> ControlledList | None:
    """The catalogue entry for a substance: by CAS number first, then by
    name, then by any of its aliases. None when it is not on the list."""
    cas = (cas or "").strip()
    if cas:
        hit = session.scalar(select(ControlledList).where(ControlledList.cas_number == cas))
        if hit:
            return hit
    target = _normalize(name)
    if not target:
        return None
    for entry in session.scalars(select(ControlledList).order_by(ControlledList.chemical_name)):
        names = [entry.chemical_name]
        if entry.alias:
            names.extend(part for part in _ALIAS_SPLIT.split(entry.alias) if part.strip())
        if any(_normalize(n) == target for n in names):
            return entry
    return None


def controlled_type_of(cas: str, session) -> str | None:
    """The catalogue class of a CAS number, or None when it is not listed.

    Takes (cas, session) — kept in that order because the check is almost
    always "is this CAS number controlled?", asked by a borrow order that
    has the number and the session in hand.
    """
    entry = match(session, cas=cas)
    return entry.dangerous_type if entry else None


def needs_approval(cas: str, session) -> bool:
    """True when a borrow order for this CAS number must wait for an
    approver. Not listed means not controlled, and not controlled means
    the lab's usual rules decide."""
    return controlled_type_of(cas, session) is not None


def borrow_order_state(session, *, cas: str = "", name: str = "",
                       bottle_controlled: bool = False) -> dict:
    """What a borrow order for this substance must do about approval.

    Called when the order is made, before anything is signed out. The
    three ways a bottle can be controlled — the list has its CAS number,
    the list has its name, or the bottle itself is marked controlled (its
    hazard attrs) while the list has not caught up — all end in the same
    place: the order is created pending, and the borrower may not approve
    it. A bottle that is none of those is the lab's own business.

    Returns what the caller (the borrow service, app/reagent_workflow.py)
    writes onto the order and shows the borrower:
        controlled:    whether approval is required at all
        type:          the catalogue class, for the message
        reason:        why — which of the three matched, in words
        status:        "pending" when controlled, else "" (the service
                       decides the ordinary status)
        self_approval: False — the borrower is never the approver here
    """
    entry = match(session, cas=cas, name=name)
    if entry is not None:
        how = "its CAS number is on the controlled list" if (cas or "").strip() == (entry.cas_number or "") \
            else "its name is on the controlled list"
        return {"controlled": True, "type": entry.dangerous_type, "reason": how,
                "status": "pending", "self_approval": False}
    if bottle_controlled:
        return {"controlled": True, "type": "", "reason": "the bottle is marked controlled",
                "status": "pending", "self_approval": False}
    return {"controlled": False, "type": "", "reason": "", "status": "", "self_approval": True}
