"""The lab's count of changes to what devices keep offline (app/sync_clock.py)."""
from __future__ import annotations

# tests.base first: it points the app at a throwaway database before anything
# imports the app. Importing app first would open data/biomanager.db.
from tests.base import AppTestCase, days_ago, one, row  # isort: skip


def version(table: str, row_id: int) -> int:
    return one(f"select sync_version from {table} where id=?", row_id)


class EveryChangeGetsTheNextNumber(AppTestCase):
    def test_a_new_record_and_each_change_to_it(self):
        cage = self.make_cage(self.m, purpose="Breeding")
        first = version("mouse_cages", cage)
        self.assertGreater(first, 0)
        self.autosave(self.m, f"/colony/cages/{cage}/update", {"notes": "moved to room 2"})
        second = version("mouse_cages", cage)
        self.assertGreater(second, first)
        self.assertEqual(one("select value from sync_clock where id=1"), max(
            one("select max(sync_version) from mouse_cages"), one("select coalesce(max(sync_version), 0) from mice"),
            one("select coalesce(max(sync_version), 0) from sync_deletions"),
            one("select coalesce(max(sync_version), 0) from tasks"),
            one("select coalesce(max(sync_version), 0) from litters"),
            one("select coalesce(max(sync_version), 0) from mouse_weights"),
            one("select coalesce(max(sync_version), 0) from mouse_racks"),
            one("select coalesce(max(sync_version), 0) from stock_units"),
            one("select coalesce(max(sync_version), 0) from tanks")))

    def test_saving_without_a_change_keeps_the_number(self):
        cage = self.make_cage(self.m, purpose="Breeding", notes="same")
        before = version("mouse_cages", cage)
        self.autosave(self.m, f"/colony/cages/{cage}/update", {"notes": "same"})
        self.assertEqual(version("mouse_cages", cage), before)

    def test_a_deleted_record_is_counted_too(self):
        col = self.make_colony(self.m, self.member, n_mice=1)
        mouse = col["mice"][0]
        before = one("select value from sync_clock where id=1")
        self.post(self.m, f"/colony/mice/{mouse}/delete", {})
        self.assertIsNone(one("select id from mice where id=?", mouse))
        gone = row("select table_name, sync_version from sync_deletions where record_id=? and table_name='mice'", mouse)
        self.assertIsNotNone(gone)
        self.assertGreater(gone[1], before)

    def test_a_weight_and_a_to_do(self):
        col = self.make_colony(self.m, self.member, n_mice=1, dob=days_ago(60))
        self.post(self.m, f"/colony/mice/{col['mice'][0]}/weights/create", {"weigh_date": days_ago(0), "grams": "24.1"})
        self.assertGreater(one("select sync_version from mouse_weights order by id desc limit 1"), 0)

    def test_the_audit_log_does_not_call_the_number_a_change(self):
        cage = self.make_cage(self.m, purpose="Breeding")
        self.autosave(self.m, f"/colony/cages/{cage}/update", {"notes": "checked"})
        details = one("select details from audit_log where table_name='mouse_cages' and record_id=? "
                      "and action='update' order by id desc limit 1", cage)
        self.assertNotIn("sync_version", details or "")
