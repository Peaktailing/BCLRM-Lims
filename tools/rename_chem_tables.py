"""把旧表名换成 chem_ 单数新名。

只替换「表名位置」的出现：带引号的完整表名、ForeignKey 的 "表.列"、
SQL 里的 from/join/into/update/delete from 之后的裸表名。
模块名（app/chemical_experiments.py、from .chemical_experiments import）
不动 —— 那些不是表。

用法：python tools/rename_chem_tables.py [--apply]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RENAMES = {
    "experiment_courses": "chem_course",
    "reagent_borrow_orders": "chem_borrow_order",
    "reagent_return_records": "chem_return_record",
    "reagent_allocation_orders": "chem_allocation_order",
    "reagent_demands": "chem_demand",
    "manager_change_logs": "chem_manager_change_log",
    "reagent_purchase_plans": "chem_purchase_plan",
    "reagent_purchase_orders": "chem_purchase_order",
    "chemical_experiments": "chem_experiment",
    "chemical_references": "chem_substance",
    "controlled_list": "chem_controlled_list",
}

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = {".py", ".html", ".js"}
SKIP_DIRS = {"migrations", "node_modules", ".git", "__pycache__", "data", "dist", "build"}


def patterns(old: str, new: str) -> list[tuple[str, str]]:
    """(regex, replacement) pairs, most specific first."""
    return [
        # "table.column" — a ForeignKey target
        (rf'(["\']){old}\.', rf"\g<1>{new}."),
        # "table" / 'table' — __tablename__, SYNCED_TABLES, a SQL string
        (rf'(["\']){old}(["\'])', rf"\g<1>{new}\g<2>"),
        # a bare table name after a SQL keyword
        (rf"\b(FROM|JOIN|INTO|UPDATE|TABLE|from|join|into|update|table)\s+{old}\b",
         rf"\g<1> {new}"),
        (rf"\bDELETE\s+FROM\s+{old}\b", rf"DELETE FROM {new}"),
    ]


def main() -> int:
    apply = "--apply" in sys.argv
    total = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path == Path(__file__).resolve():   # this file lists the names it replaces
            continue
        text = path.read_text(encoding="utf-8")
        before = text
        hits: list[str] = []
        for old, new in RENAMES.items():
            for regex, repl in patterns(old, new):
                text, n = re.subn(regex, repl, text)
                if n:
                    hits.append(f"{old}->{new} x{n}")
        if text != before:
            total += sum(int(h.split(" x")[-1]) for h in hits)
            print(f"{path.relative_to(ROOT)}: {', '.join(hits)}")
            if apply:
                path.write_text(text, encoding="utf-8")
    print(f"\n共 {total} 处" + ("（已写入）" if apply else "（演练，未写入）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
